from copy import deepcopy
from pathlib import Path

from docx import Document

from yc_agents.docx_format.models import TemplateRules


REPORT_STANDARD = {
    "name": "report-standard",
    "page": {
        "size": "A4",
        "orientation": "portrait",
        "margins_cm": {
            "top": 2.54,
            "bottom": 2.54,
            "left": 3.18,
            "right": 3.18,
        },
        "header_distance_cm": 1.50,
        "footer_distance_cm": 1.75,
    },
    "styles": {
        "body": {
            "east_asia_font": "SimSun",
            "latin_font": "Times New Roman",
            "font_size_pt": 12,
            "line_spacing_pt": 24,
            "first_line_indent_pt": 24,
            "alignment": "justify",
            "space_before_pt": 0,
            "space_after_pt": 0,
        },
        "heading_1": {
            "east_asia_font": "SimHei",
            "font_size_pt": 22,
            "bold": True,
            "alignment": "center",
            "outline_level": 1,
            "page_break_before": True,
        },
        "heading_2": {
            "east_asia_font": "SimHei",
            "font_size_pt": 16,
            "bold": True,
            "alignment": "left",
            "outline_level": 2,
        },
        "heading_3": {
            "east_asia_font": "SimSun",
            "font_size_pt": 16,
            "bold": True,
            "alignment": "left",
            "outline_level": 3,
        },
        "caption": {
            "east_asia_font": "SimSun",
            "font_size_pt": 12,
            "alignment": "center",
            "space_before_pt": 6,
            "space_after_pt": 6,
        },
    },
    "table_of_contents": {
        "enabled": True,
        "levels": "1-3",
        "field_code": 'TOC \\\\o "1-3" \\\\h \\\\u',
    },
    "page_numbers": {
        "enabled": True,
        "start_section": "content",
        "start": 1,
        "format": "decimal",
        "position": "footer_center",
    },
    "tables": {
        "default": {
            "font_size_pt": 10.5,
            "alignment": "center",
            "vertical_alignment": "center",
        }
    },
    "captions": {
        "table_prefix": "Table",
        "figure_prefix": "Figure",
    },
    "headers": {},
    "footers": {},
}


def load_builtin_template(name):
    if name != "report-standard":
        raise ValueError(f"Unknown built-in template: {name}")

    data = deepcopy(REPORT_STANDARD)
    return TemplateRules(
        name=data["name"],
        page=data["page"],
        styles=data["styles"],
        table_of_contents=data["table_of_contents"],
        page_numbers=data["page_numbers"],
        tables=data["tables"],
        captions=data["captions"],
        headers=data["headers"],
        footers=data["footers"],
    )


def extract_template_rules(template_path, fallback_name="report-standard"):
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(f"Template DOCX not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx template, got: {path}")

    rules = load_builtin_template(fallback_name)
    document = Document(path)
    section = document.sections[0]
    page = deepcopy(rules.page)
    page["margins_cm"] = {
        "top": round(section.top_margin.cm, 2),
        "bottom": round(section.bottom_margin.cm, 2),
        "left": round(section.left_margin.cm, 2),
        "right": round(section.right_margin.cm, 2),
    }

    styles = deepcopy(rules.styles)
    normal = document.styles["Normal"]
    if normal.font.size is not None:
        styles["body"]["font_size_pt"] = round(normal.font.size.pt, 2)
    if normal.font.name:
        styles["body"]["east_asia_font"] = normal.font.name

    return TemplateRules(
        name=f"uploaded:{path.name}",
        page=page,
        styles=styles,
        table_of_contents=rules.table_of_contents,
        page_numbers=rules.page_numbers,
        tables=rules.tables,
        captions=rules.captions,
        headers=rules.headers,
        footers=rules.footers,
    )
