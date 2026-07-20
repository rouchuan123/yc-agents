from pathlib import Path

from yc_agents.rag.chunker import DocumentChunker
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.loaders import load_markdown


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

    def build(self):
        if self.create:
            self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        files = self._source_files()
        errors = []

        for path in files:
            relative_source = path.relative_to(self.root_dir).as_posix()
            cited_source = f"{self.scope}:{relative_source}"
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
            self.keyword_index.add_chunks(cited_source, chunks)

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
