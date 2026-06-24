# YCore 演示脚本

## 演示目标

展示 YCore 作为 CLI Agent 运行时，如何把“Word 文档格式调整”拆成技能选择、工具调用、状态追踪和结果审计，而不是只生成一段口头建议。

## 演示前准备

- 执行 `pip install -r requirements.txt` 安装依赖。
- 执行 `python -m pytest -q` 确认测试通过。
- 准备一份格式混乱的 `messy-demo.docx`，放在当前 workspace。

## 场景：Word 文档格式调整

用户输入：

```text
使用 document-format-normalizer 处理 messy-demo.docx，按 report-standard 模板调整格式，输出名为 demo-normalized。
```

演示重点：

1. CLI 接收用户请求。
2. `SkillRuntimeAgent` 选择 `document-format-normalizer`。
3. 模型发起 `docx_format_normalizer` 工具调用。
4. 工具在 workspace 内读取源 `.docx`。
5. DOCX pipeline 生成 `.ycore/docx-format/demo-normalized.docx`。
6. 同时生成 `.ycore/docx-format/demo-normalized.audit.md` 和 `.audit.json`。
7. 最终回复说明输出路径，并标出需要人工复核的 warning。

## 可以展示的文件

- `.ycore/docx-format/demo-normalized.docx`
- `.ycore/docx-format/demo-normalized.audit.md`
- `.ycore/docx-format/demo-normalized.audit.json`
- `.ycore/runs/<session_id>/<run_id>/trace.json`
- `.ycore/runs/<session_id>/<run_id>/state.json`
- `.ycore/runs/<session_id>/<run_id>/final_output.md`

## 五分钟讲解稿

YCore 当前的首个落地点是 Word 文档格式调整。用户把一份格式混乱的 `.docx` 草稿交给 CLI，Agent 先根据技能说明选择 `document-format-normalizer`，再通过 `ToolGateway` 调用确定性的 DOCX 工具。工具负责分析文档结构、套用内置模板、生成新 Word 文件，并输出审计报告。这样可以展示 Agent 不只是聊天，而是在一个可追踪、可验证、可恢复的运行时里完成真实文件处理任务。

## 常见追问

- 为什么不用模型直接输出排版建议？
- 工具如何保证不覆盖源文件？
- 上传模板能支持到什么程度？
- 复杂 Word 对象无法重建时怎么处理？
- 如何通过 trace 和 audit report 复核一次运行？
