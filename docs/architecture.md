# YCore 架构

## 定位

YCore 当前是一个 CLI 优先的本地 Agent 运行时。首个落地点是 Word 文档格式调整：用户给出 `.docx` 草稿，Agent 选择 `document-format-normalizer` 技能，再通过确定性 Python 工具生成规范化文档和审计报告。

## 运行链路

```text
用户输入
  -> CLI
  -> YCAgentRuntime
  -> SkillRuntimeAgent
  -> document-format-normalizer
  -> ToolGateway
  -> docx_format_normalizer
  -> yc_agents.docx_format pipeline
  -> normalized .docx + audit report
```

## Runtime 边界

`YCAgentRuntime` 负责编排一次运行：

- 写入 run 输入和上下文快照。
- 调用 Agent。
- 解析模型返回的 JSON 协议。
- 通过 `ToolGateway` 执行工具。
- 写入最终输出、verification、trace 和 state checkpoint。

## Agent 边界

`SkillRuntimeAgent` 负责：

- 加载 `skills` 目录下的技能。
- 先用技能摘要进行候选技能发现。
- 在技能被选中后再加载完整 `SKILL.md` 正文。
- 将 workspace、记忆、RAG 上下文和技能说明组织成模型提示。

当前发布态只保留一个技能：`document-format-normalizer`。

## Skill 边界

`SkillLoader` 从 `skills` 目录读取：

- `SKILL.md`
- `references/`
- `scripts/`
- `assets/`

`document-format-normalizer` 的职责是告诉模型什么时候调用 Word 格式调整工具、需要哪些输入、如何解释输出和 warning。它不直接承诺复杂 Word 对象的完美保真。

## Tool 边界

`ToolGateway` 负责工具权限、参数 schema 校验、审批策略、追踪和失败返回。

`docx_format_normalizer` 是当前核心业务工具，负责：

- 限制文件路径在当前 workspace 内。
- 调用 DOCX pipeline。
- 返回生成 `.docx`、`.audit.md` 和 `.audit.json` 的相对路径。

## DOCX Pipeline

`yc_agents/docx_format` 是确定性 Word 处理包：

- `analyzer.py`：读取源 `.docx`，提取标题、正文、表格、题注、图片和不支持对象。
- `template.py`：加载内置 `report-standard` 模板，或从上传模板提取部分规则。
- `formatter.py`：生成新的规范化 `.docx`。
- `auditor.py`：检查输出文档是否符合模板关键规则。
- `pipeline.py`：串联 analyze -> template -> format -> audit。

## 记忆、追踪和状态

YCore 保留会话记忆、摘要记忆和用户画像记忆。每次运行会在当前 workspace 的 `.ycore/runs/` 下留下可复核产物，包括输入、输出、trace 和 state checkpoint。

## 当前限制

- 只保留 CLI 端。
- 只发布 `document-format-normalizer` 技能。
- `report-standard` 是第一版主要稳定模板。
- 上传模板解析是有限能力，只读取页边距和 Normal 样式等可稳定字段。
- 批注、修订痕迹、SmartArt、复杂图表、嵌入对象、宏和复杂浮动布局只做 warning，不承诺完美重建。
