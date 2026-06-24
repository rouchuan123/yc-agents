---
name: document-format-normalizer
description: 当用户需要整理、重排或规范化 Word .docx 文档格式时使用，例如按学校/企业模板调整报告、论文、开题材料、制度文件或项目文档格式。
allowed_tools:
  - workspace_files
  - file_reader
  - docx_reader
  - docx_format_normalizer
---

# Word 文档格式调整 Skill

这个技能面向中文用户，用来把一份格式混乱或不符合要求的 Word 文档，整理成指定模板或内置标准格式，并输出可检查的审计报告。

## 适用场景

- 用户有一份 `.docx` 草稿，需要按模板统一标题、正文、表格、页边距、目录和页码。
- 用户说“帮我调整 Word 格式”“按模板排版”“把报告格式统一一下”“整理成规范文档”。
- 用户没有提供模板，但希望先用项目内置的通用报告格式做演示或初稿整理。

## 需要的信息

- 源 Word 文件路径，必须是 `.docx`。
- 目标模板：可以是内置模板名，也可以是用户提供的 `.docx` 模板文件。
- 输出文件名，可选；未提供时使用 `normalized`。

如果用户没有提供模板，默认使用 `report-standard`。

## 工作流程

1. 先确认源 `.docx` 文件路径。如果用户没给路径，询问用户或使用 `workspace_files` 查看工作区文件。
2. 如果用户需要先看原文内容，可用 `docx_reader` 或 `file_reader` 读取文档信息。
3. 文件路径明确后，调用 `docx_format_normalizer`：
   - `source_file`：源文档路径。
   - `template_name`：默认 `report-standard`。
   - `template_file`：只有用户提供上传模板时才填写。
   - `output_name`：用户指定的输出名，默认 `normalized`。
4. 返回生成的 `.docx` 文件路径和审计报告路径。
5. 如果审计报告中有 warning，要明确告诉用户哪些内容需要人工复核。

## 能处理的内容

- 正文段落、标题、表格、题注和可提取图片。
- 页面设置、页边距、正文样式、标题样式、目录字段、页脚页码。
- 内置 `report-standard` 模板。
- 上传模板的部分可读取规则，例如页边距和 Normal 样式。

## 边界说明

- 不覆盖原文件，只生成新文件。
- 不承诺完美保留批注、修订痕迹、SmartArt、复杂图表、嵌入 Excel、宏、浮动文本框和复杂形状。
- 对不能稳定重建的对象，只在审计报告中标记，提醒用户人工复核。
- 这个技能负责文档格式调整，不负责替用户改写论文内容或判断学术质量。

## 完成标准

- 最终回复包含规范化后的 `.docx` 路径。
- 最终回复包含 `.audit.md` 或 `.audit.json` 审计报告路径。
- 对所有 warning 明确标注“需要人工复核”。
