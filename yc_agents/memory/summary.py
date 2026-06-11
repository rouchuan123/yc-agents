from pathlib import Path


class SummaryMemory:
    def __init__(self, file_path="data/memory/summary.md"):
        self.file_path = Path(file_path)
        self.summary = ""

    def load(self):
        if not self.file_path.exists():
            self.summary = ""
            return self.summary
        self.summary = self.file_path.read_text(encoding="utf-8")
        return self.summary

    def save(self, content):
        self.summary = content
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(self.summary, encoding="utf-8")
        return self.file_path

    def get_summary(self): 
        return self.summary