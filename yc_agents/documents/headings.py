import re


def numbered_heading_level(text):
    value = str(text or "").strip()
    if re.match(
        r"^(?:第[一二三四五六七八九十百0-9]+[章节篇部](?:\s|[、：:])|"
        r"[一二三四五六七八九十百]+、)",
        value,
    ):
        return 1
    numeric = re.match(r"^(\d+(?:\.\d+){0,3})[、.\s]", value)
    if numeric:
        return numeric.group(1).count(".") + 1
    return None


def styled_heading_level(paragraph):
    text = paragraph.text.strip()
    style_name = (paragraph.style.name or "").lower()
    if not text:
        return None
    if style_name.startswith("toc") or style_name.startswith("目录"):
        return None
    style_match = re.search(r"(?:heading|标题)\s*([1-9])", style_name)
    if style_match:
        return int(style_match.group(1))
    outline_level = paragraph._p.xpath("./w:pPr/w:outlineLvl/@w:val")
    if outline_level:
        try:
            return int(outline_level[0]) + 1
        except (TypeError, ValueError):
            pass
    return None


def structural_heading_level(paragraph):
    text = paragraph.text.strip()
    style_name = (paragraph.style.name or "").lower()
    if not text or style_name.startswith("toc") or style_name.startswith("目录"):
        return None
    if paragraph._p.xpath(".//w:instrText | .//w:fldChar"):
        return None

    styled = styled_heading_level(paragraph)
    numbered = numbered_heading_level(text)
    if numbered is not None and (
        styled is not None
        or style_name in {"title", "subtitle", "题名", "副标题"}
    ):
        return numbered

    if styled is None:
        return None
    if _looks_like_prose(text):
        return None
    return styled


def is_structural_heading(paragraph):
    return structural_heading_level(paragraph) is not None


def _looks_like_prose(text):
    value = str(text or "").strip()
    if len(value) > 120:
        return True
    sentence_marks = sum(value.count(mark) for mark in "。！？；.!?;")
    return len(value) > 80 and sentence_marks >= 2
