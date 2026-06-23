from pathlib import Path

from docx import Document
from pypdf import PdfReader


def _metadata(path, file_type):
    return {
        "file_name": path.name,
        "file_type": file_type,
    }


def load_markdown(path):
    path = Path(path)
    return {
        "source": str(path),
        "text": path.read_text(encoding="utf-8"),
        "metadata": _metadata(path, "markdown"),
    }


def load_docx(path):
    path = Path(path)
    document = Document(path)
    text = "\n".join(
        paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()
    )
    return {
        "source": str(path),
        "text": text,
        "metadata": _metadata(path, "docx"),
    }


def load_pdf(path):
    path = Path(path)
    reader = PdfReader(path)
    page_text = [
        text
        for page in reader.pages
        if (text := (page.extract_text() or "").strip())
    ]
    return {
        "source": str(path),
        "text": "\n".join(page_text),
        "metadata": _metadata(path, "pdf"),
    }
