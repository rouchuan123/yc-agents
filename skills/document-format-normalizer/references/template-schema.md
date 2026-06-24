# Template Rule Schema

The formatter uses a structured template rule object with these groups:

- `page`: A4/portrait and margins in centimeters.
- `styles.body`: body font, font size, line spacing, first-line indent, alignment, and paragraph spacing.
- `styles.heading_1`, `styles.heading_2`, `styles.heading_3`: heading font, size, bold flag, alignment, outline level, and page-break behavior.
- `styles.caption`: figure and table caption formatting.
- `table_of_contents`: whether to insert a TOC field and which heading levels it includes.
- `page_numbers`: whether to insert page numbers and where numbering starts.
- `tables`: named table presets for column widths, row heights, cell margins, and alignment.

The first implementation treats `report-standard` as the authoritative built-in template.
Uploaded templates may override page margins and the Normal style when those values can be read from the `.docx`.
