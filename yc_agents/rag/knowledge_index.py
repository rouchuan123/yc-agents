import json
from pathlib import Path

from yc_agents.rag.chunker import DocumentChunker
from yc_agents.rag.document import DocumentChunk
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.loaders import load_markdown


CACHE_VERSION = 1


class RAGKnowledgeIndex:
    def __init__(
        self,
        root_dir,
        knowledge_dir,
        *,
        scope,
        chunk_size=1200,
        chunk_overlap=150,
        keyword_index=None,
        create=False,
        cache_path=None,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.knowledge_dir = self._resolve_knowledge_dir(knowledge_dir)
        self.scope = str(scope)
        self.chunker = DocumentChunker(
            chunk_size=int(chunk_size),
            overlap=int(chunk_overlap),
        )
        self.keyword_index = keyword_index or KeywordIndex()
        self.create = bool(create)
        # 分块缓存按 (文件路径, mtime, size, 分块配置) 命中；workspace 库
        # 落在工作区 .ycore/cache 下，全局库落在全局配置根的 .ycore/cache。
        self.cache_path = (
            Path(cache_path)
            if cache_path is not None
            else self.root_dir / ".ycore" / "cache" / "rag-index.json"
        )

    def build(self):
        if self.create:
            self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        files = self._source_files()
        errors = []
        cache_entries = self._load_cache_entries()
        cache_dirty = False
        seen_keys = set()

        for path in files:
            relative_source = path.relative_to(self.root_dir).as_posix()
            cited_source = f"{self.scope}:{relative_source}"
            seen_keys.add(cited_source)

            chunks = self._cached_chunks(
                cache_entries.get(cited_source),
                path,
                cited_source,
            )
            if chunks is None:
                try:
                    document = load_markdown(path)
                except (OSError, UnicodeError) as exc:
                    errors.append({"source": cited_source, "error": str(exc)})
                    continue

                metadata = dict(document.get("metadata") or {})
                metadata.update(
                    {
                        "scope": self.scope,
                        "source_path": relative_source,
                    }
                )
                chunks = self.chunker.chunk_text(
                    document.get("text", ""),
                    source=cited_source,
                    metadata=metadata,
                )
                entry = self._cache_entry(path, chunks)
                if entry is not None:
                    cache_entries[cited_source] = entry
                    cache_dirty = True
            self.keyword_index.add_chunks(cited_source, chunks)

        # 清理本 scope 下已删除文件的缓存条目，避免缓存无限膨胀。
        prefix = f"{self.scope}:"
        stale_keys = [
            key
            for key in cache_entries
            if key.startswith(prefix) and key not in seen_keys
        ]
        for key in stale_keys:
            del cache_entries[key]
            cache_dirty = True
        if cache_dirty:
            self._write_cache_entries(cache_entries)

        return {
            "scope": self.scope,
            "directory": self.knowledge_dir.relative_to(self.root_dir).as_posix(),
            "documents": len(files),
            "chunks": sum(
                1
                for item in self.keyword_index.items
                if item.get("metadata", {}).get("scope") == self.scope
            ),
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # 分块缓存：纯加速层。任何读取/解析失败都静默回退到全量重建，
    # 绝不影响索引正确性。
    # ------------------------------------------------------------------

    def _load_cache_entries(self):
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return {}
        entries = payload.get("entries")
        return dict(entries) if isinstance(entries, dict) else {}

    def _write_cache_entries(self, entries):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {"version": CACHE_VERSION, "entries": entries},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            # 缓存写不进去（只读目录等）只损失加速效果，不影响本次索引。
            pass

    def _cached_chunks(self, entry, path, cited_source):
        if not isinstance(entry, dict):
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        if (
            entry.get("mtime_ns") != stat.st_mtime_ns
            or entry.get("size") != stat.st_size
            or entry.get("chunk_size") != self.chunker.chunk_size
            or entry.get("chunk_overlap") != self.chunker.overlap
        ):
            return None
        try:
            return [
                DocumentChunk(
                    source=cited_source,
                    chunk_id=int(chunk["chunk_id"]),
                    text=str(chunk["text"]),
                    metadata=dict(chunk["metadata"]),
                )
                for chunk in entry["chunks"]
            ]
        except (KeyError, TypeError, ValueError):
            return None

    def _cache_entry(self, path, chunks):
        try:
            stat = path.stat()
        except OSError:
            return None
        return {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "chunk_size": self.chunker.chunk_size,
            "chunk_overlap": self.chunker.overlap,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": dict(chunk.metadata),
                }
                for chunk in chunks
            ],
        }

    def _resolve_knowledge_dir(self, knowledge_dir):
        relative_dir = Path(str(knowledge_dir or ""))
        if not str(knowledge_dir or "").strip():
            raise ValueError("RAG knowledge directory is required")
        if relative_dir.is_absolute() or ".." in relative_dir.parts:
            raise ValueError(
                f"RAG knowledge directory must stay inside its root: {knowledge_dir}"
            )

        resolved = (self.root_dir / relative_dir).resolve()
        if not resolved.is_relative_to(self.root_dir):
            raise ValueError(
                f"RAG knowledge directory resolved outside its root: {knowledge_dir}"
            )
        return resolved

    def _source_files(self):
        if not self.knowledge_dir.exists():
            return []

        files = []
        for candidate in self.knowledge_dir.rglob("*.md"):
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self.knowledge_dir):
                raise ValueError(
                    f"RAG source resolved outside the knowledge directory: {candidate}"
                )
            files.append(resolved)

        return sorted(files, key=lambda path: path.as_posix().lower())
