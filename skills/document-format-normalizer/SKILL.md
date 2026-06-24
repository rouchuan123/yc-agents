---
name: document-format-normalizer
description: Use when the user wants to normalize, reformat, or rebuild a Word .docx draft according to a required Word template or built-in document format standard.
allowed_tools:
  - workspace_files
  - file_reader
  - docx_reader
  - docx_format_normalizer
---

# Document Format Normalizer Skill

Use this skill when the user provides or references a Word draft that needs formatting according to a template.

## Required Inputs

- Source `.docx` draft path.
- Target template name or target template `.docx` path.
- Optional output name.

If the user does not provide a template, use `report-standard`.

## Workflow

1. Confirm the source `.docx` path is known. If not, ask the user for it.
2. If the user asks what files are available, call `workspace_files`.
3. If the source path is known, call `docx_format_normalizer` with:
   - `source_file`
   - `template_name`, defaulting to `report-standard`
   - `template_file`, only when the user provides an uploaded template path
   - `output_name`, defaulting to `normalized`
4. Explain the generated `.docx` path and audit report path.
5. Summarize any warnings from the audit report.

## Boundaries

- Preserve editable paragraphs, headings, tables, captions, and images whenever possible.
- Rebuild page setup, heading styles, body style, table of contents, page numbers, and headers or footers from template rules.
- Report unsupported objects such as comments, tracked changes, charts, embedded Excel objects, macros, SmartArt, floating text boxes, and complex shapes.
- Do not claim unsupported objects were perfectly preserved.
- Do not overwrite the source document.

## Completion Check

- The final response includes the normalized `.docx` path.
- The final response includes the audit report path.
- Any warnings are clearly marked as requiring manual review.
