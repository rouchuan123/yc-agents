import hashlib
import json
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from yc_agents.core.llm_call import invoke_llm
from yc_agents.memory.compressor import estimate_tokens


ASCII_WORD = re.compile(r"[a-zA-Z0-9_./:-]+")
CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


def memory_tokens(text):
    text = str(text or "").lower()
    tokens = ASCII_WORD.findall(text)
    for run in CJK_RUN.findall(text):
        tokens.extend(run if len(run) == 1 else [run[i : i + 2] for i in range(len(run) - 1)])
    return tokens


@dataclass
class MemoryChunk:
    path: str
    scope: str
    chunk_id: str
    text: str
    start_line: int
    end_line: int
    created_at: float
    access_count: int = 0
    embedding: list | None = None


def chunk_markdown(text, max_chars=2400, overlap_chars=160):
    lines = str(text or "").splitlines()
    if not lines:
        return []
    sections = []
    current = []
    header = ""
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("## ") and current:
            sections.append((start, index, header, current))
            current = []
            start = index
            header = line.strip()
        elif line.startswith("## "):
            start = index
            header = line.strip()
        current.append(line)
    if current:
        sections.append((start, len(lines), header, current))

    chunks = []
    for section_start, section_end, header, section_lines in sections:
        paragraphs = "\n".join(section_lines).split("\n\n")
        buffer = ""
        chunk_start = section_start
        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if buffer.strip():
                    chunks.append((chunk_start, section_end, buffer.strip()))
                    buffer = ""
                step = max(1, max_chars - overlap_chars)
                for offset in range(0, len(paragraph), step):
                    piece = paragraph[offset : offset + max_chars]
                    if header and not piece.startswith(header):
                        piece = f"{header}\n{piece}"
                    chunks.append((section_start, section_end, piece.strip()))
                continue
            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if buffer and len(candidate) > max_chars:
                chunks.append((chunk_start, section_end, buffer))
                overlap = buffer[-overlap_chars:] if overlap_chars else ""
                prefix = f"{header}\n{overlap}".strip() if header else overlap
                buffer = f"{prefix}\n\n{paragraph}".strip()
                chunk_start = section_start
            else:
                buffer = candidate
        if buffer.strip():
            chunks.append((chunk_start, section_end, buffer.strip()))
    return chunks


class LongTermMemory:
    def __init__(
        self,
        workspace_dir,
        *,
        global_dir=None,
        embedding_provider=None,
        min_score=0.2,
        session_half_life_days=30,
        dream_config=None,
        llm=None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.global_dir = Path(global_dir or Path.home() / ".ycore" / "memory")
        self.memory_dir = self.workspace_dir / ".ycore" / "memory"
        self.sessions_dir = self.memory_dir / "sessions"
        self.db_path = self.memory_dir / "index.sqlite"
        self.embedding_provider = embedding_provider
        self.min_score = float(min_score)
        self.session_half_life_days = float(session_half_life_days)
        self.dream_config = dict(dream_config or {})
        self.llm = llm
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    @property
    def global_memory_path(self):
        return self.global_dir / "MEMORY.md"

    @property
    def workspace_memory_path(self):
        return self.memory_dir / "MEMORY.md"

    def session_log_path(self, session_id):
        return self.sessions_dir / f"{session_id}.md"

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _db(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize_db(self):
        with self._db() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_files (
                    path TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    modified_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    embedding TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_path ON memory_chunks(path);
                """
            )

    def _source_files(self):
        sources = []
        if self.global_memory_path.exists():
            sources.append((self.global_memory_path, "global"))
        if self.workspace_memory_path.exists():
            sources.append((self.workspace_memory_path, "workspace"))
        if self.sessions_dir.exists():
            sources.extend((path, "session") for path in sorted(self.sessions_dir.glob("*.md")))
        return sources

    def sync(self):
        sources = self._source_files()
        current_paths = {str(path.resolve()) for path, _scope in sources}
        with self._db() as connection:
            indexed_paths = {
                row["path"] for row in connection.execute("SELECT path FROM memory_files")
            }
            for stale in indexed_paths - current_paths:
                connection.execute("DELETE FROM memory_chunks WHERE path = ?", (stale,))
                connection.execute("DELETE FROM memory_files WHERE path = ?", (stale,))
            for path, scope in sources:
                resolved = str(path.resolve())
                content = path.read_text(encoding="utf-8")
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                row = connection.execute(
                    "SELECT content_hash FROM memory_files WHERE path = ?", (resolved,)
                ).fetchone()
                if row is not None and row["content_hash"] == digest:
                    continue
                self._reindex_file(connection, path, resolved, scope, content, digest)

    def _reindex_file(self, connection, path, resolved, scope, content, digest):
        connection.execute("DELETE FROM memory_chunks WHERE path = ?", (resolved,))
        raw_chunks = chunk_markdown(content)
        embeddings = [None] * len(raw_chunks)
        if self.embedding_provider is not None and raw_chunks:
            try:
                embeddings = self.embedding_provider.embed([item[2] for item in raw_chunks])
            except Exception:
                embeddings = [None] * len(raw_chunks)
        embeddings = list(embeddings or [])[: len(raw_chunks)]
        embeddings.extend([None] * (len(raw_chunks) - len(embeddings)))
        created_at = path.stat().st_mtime
        for index, ((start, end, text), embedding) in enumerate(zip(raw_chunks, embeddings)):
            chunk_id = hashlib.sha256(f"{resolved}:{index}:{text}".encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO memory_chunks
                    (chunk_id, path, scope, text, start_line, end_line, created_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    resolved,
                    scope,
                    text,
                    start + 1,
                    end,
                    created_at,
                    json.dumps(embedding) if embedding is not None else None,
                ),
            )
        connection.execute(
            """
            INSERT INTO memory_files(path, scope, content_hash, modified_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                scope=excluded.scope,
                content_hash=excluded.content_hash,
                modified_at=excluded.modified_at
            """,
            (resolved, scope, digest, created_at),
        )

    def search(self, query, top_k=6, token_budget=4000, exclude_session_id=None):
        if not str(query or "").strip():
            return []
        self.sync()
        with self._db() as connection:
            rows = connection.execute("SELECT * FROM memory_chunks").fetchall()
        chunks = [self._row_to_chunk(row) for row in rows]
        if exclude_session_id:
            excluded = str(self.session_log_path(exclude_session_id).resolve())
            chunks = [chunk for chunk in chunks if chunk.path != excluded]
        if not chunks:
            return []

        keyword_scores = self._keyword_scores(query, chunks)
        vector_scores = self._vector_scores(query, chunks)
        now = time.time()
        ranked = []
        for index, chunk in enumerate(chunks):
            base = keyword_scores[index]
            if vector_scores is not None:
                base = 0.5 * base + 0.5 * vector_scores[index]
            if base <= 0:
                continue
            score = base * self._scope_weight(chunk.scope)
            score *= self._decay(chunk, now)
            score *= 1 + min(0.1, math.log1p(chunk.access_count) * 0.02)
            if score >= self.min_score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = self._mmr_select(ranked, top_k)

        results = []
        used_tokens = 0
        for score, chunk in selected:
            chunk_tokens = estimate_tokens(chunk.text)
            if results and used_tokens + chunk_tokens > token_budget:
                continue
            text = chunk.text
            if not results and chunk_tokens > token_budget:
                text = text[: max(1, token_budget * 4)]
                chunk_tokens = estimate_tokens(text)
            used_tokens += chunk_tokens
            results.append(
                {
                    "scope": chunk.scope,
                    "source": chunk.path,
                    "chunk_id": chunk.chunk_id,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "score": round(min(1.0, score), 4),
                    "text": text,
                }
            )
        self._record_access([item["chunk_id"] for item in results])
        return results

    def write_session_log(self, session_id, messages, summary=""):
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# Session {session_id}", ""]
        if str(summary or "").strip():
            lines.extend(["## Summary", "", str(summary).strip(), ""])
        lines.extend(["## Conversation", ""])
        for message in messages or []:
            role = str(message.get("role") or "unknown")
            content = str(message.get("content") or "").strip()
            if content:
                lines.extend([f"### {role.title()}", "", content, ""])
        path = self.session_log_path(session_id)
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return path

    def maybe_dream(self, current_session_id=None):
        if not self.dream_config.get("enabled") or self.llm is None:
            return False
        state_path = self.memory_dir / ".dream.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError, json.JSONDecodeError):
            state = {}
        last_run = float(state.get("last_run", 0))
        min_hours = float(self.dream_config.get("minHours", 24))
        if time.time() - last_run < min_hours * 3600:
            return False
        logs = [
            path for path in sorted(self.sessions_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
            if path.stem != current_session_id and path.stat().st_mtime > last_run
        ]
        if len(logs) < int(self.dream_config.get("minSessions", 5)):
            return False
        budget = int(self.dream_config.get("maxInputTokens", 32_000))
        contents = []
        used = 0
        for path in reversed(logs):
            content = path.read_text(encoding="utf-8")
            tokens = estimate_tokens(content)
            if contents and used + tokens > budget:
                continue
            contents.append(content[: max(1, (budget - used) * 4)])
            used += tokens
            if used >= budget:
                break
        messages = [
            {
                "role": "system",
                "content": (
                    "Consolidate session logs into durable project memory. Preserve "
                    "decisions, architecture, preferences, and problem/solution pairs. "
                    "Discard greetings and transient tool noise. Return Markdown with ## headings."
                ),
            },
            {"role": "user", "content": "\n\n---\n\n".join(contents)},
        ]
        try:
            result = str(invoke_llm(self.llm.think, messages, usage_kind="auxiliary") or "").strip()
        except Exception:
            return False
        if not result:
            return False
        self.workspace_memory_path.write_text(result + "\n", encoding="utf-8")
        state_path.write_text(
            json.dumps(
                {"last_run": time.time(), "updated_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.sync()
        return True

    def _keyword_scores(self, query, chunks):
        corpus = [memory_tokens(chunk.text) or [""] for chunk in chunks]
        query_tokens = memory_tokens(query)
        if not query_tokens:
            return [0.0] * len(chunks)
        raw = BM25Okapi(corpus).get_scores(query_tokens)
        normalized = self._normalize(raw)
        query_set = set(query_tokens)
        overlap = [
            len(query_set & set(tokens)) / len(query_set)
            for tokens in corpus
        ]
        return [max(bm25, lexical) for bm25, lexical in zip(normalized, overlap)]

    def _vector_scores(self, query, chunks):
        if self.embedding_provider is None or not any(chunk.embedding for chunk in chunks):
            return None
        try:
            query_vector = np.array(self.embedding_provider.embed([query])[0], dtype=float)
        except Exception:
            return None
        scores = []
        query_norm = np.linalg.norm(query_vector)
        for chunk in chunks:
            if not chunk.embedding or query_norm == 0:
                scores.append(0.0)
                continue
            vector = np.array(chunk.embedding, dtype=float)
            norm = np.linalg.norm(vector)
            scores.append(0.0 if norm == 0 else float(np.dot(query_vector, vector) / (query_norm * norm)))
        return self._normalize(scores)

    @staticmethod
    def _normalize(values):
        values = [float(value) for value in values]
        if not values:
            return []
        low, high = min(values), max(values)
        if high <= low:
            return [1.0 if value > 0 else 0.0 for value in values]
        return [(value - low) / (high - low) for value in values]

    def _decay(self, chunk, now):
        if chunk.scope in {"global", "workspace"} or self.session_half_life_days <= 0:
            return 1.0
        age_days = max(0.0, (now - chunk.created_at) / 86400)
        return math.exp(-math.log(2) * age_days / self.session_half_life_days)

    @staticmethod
    def _scope_weight(scope):
        return {"workspace": 1.1, "global": 1.05, "session": 1.0}.get(scope, 1.0)

    def _mmr_select(self, ranked, top_k, diversity=0.7):
        selected = []
        candidates = list(ranked)
        while candidates and len(selected) < max(1, int(top_k)):
            best_index = 0
            best_value = float("-inf")
            for index, (score, chunk) in enumerate(candidates):
                redundancy = max(
                    (self._text_similarity(chunk.text, chosen.text) for _s, chosen in selected),
                    default=0.0,
                )
                value = diversity * score - (1 - diversity) * redundancy
                if value > best_value:
                    best_index, best_value = index, value
            selected.append(candidates.pop(best_index))
        return selected

    @staticmethod
    def _text_similarity(left, right):
        a, b = set(memory_tokens(left)), set(memory_tokens(right))
        return len(a & b) / len(a | b) if a and b else 0.0

    def _record_access(self, chunk_ids):
        if not chunk_ids:
            return
        with self._db() as connection:
            connection.executemany(
                "UPDATE memory_chunks SET access_count = access_count + 1 WHERE chunk_id = ?",
                [(chunk_id,) for chunk_id in chunk_ids],
            )

    @staticmethod
    def _row_to_chunk(row):
        embedding = json.loads(row["embedding"]) if row["embedding"] else None
        return MemoryChunk(
            path=row["path"],
            scope=row["scope"],
            chunk_id=row["chunk_id"],
            text=row["text"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            created_at=row["created_at"],
            access_count=row["access_count"],
            embedding=embedding,
        )
