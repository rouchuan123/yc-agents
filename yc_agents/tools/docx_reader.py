from pathlib import Path

from docx import Document

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxReaderTool(BaseTool):
    name = "docx_reader"
    description = "Read text from a docx file."
    schema = ToolSchema(fields=[ToolField(name="file_path", type="str", required=True)])

    def read(self, file_path):
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Docx file not found: {path}")

        if path.suffix.lower() != ".docx":
            raise ValueError(f"Expected a .docx file, got: {path}")

        document = Document(path)
        paragraphs = []

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                paragraphs.append(text)

        return "\n".join(paragraphs)

    def run(self, file_path):
        return self.read(file_path)
