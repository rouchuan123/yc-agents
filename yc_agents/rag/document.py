from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    chunk_id: int
    text: str
    metadata: dict = field(default_factory=dict)
