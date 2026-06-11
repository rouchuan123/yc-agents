class DocumentChunker:
    def __init__(self, chunk_size=500, overlap=50):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        if overlap < 0:
            raise ValueError("overlap must be non-negative")

        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text):
        if not text or not text.strip():
            return []

        clean_text = text.strip()
        chunks = []
        start = 0

        while start < len(clean_text):
            end = start + self.chunk_size
            chunk = clean_text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            start = end - self.overlap

        return chunks