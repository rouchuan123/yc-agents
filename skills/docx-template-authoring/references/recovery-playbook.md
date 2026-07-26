# 报错恢复对照表

工具报错是导航信号，不是重试信号。同一调用原样重发超过一次没有意义，连续重复还会触发循环防护直接终止本轮。

## 状态与门槛类

| 错误 | 含义 | 正确的下一步 |
| --- | --- | --- |
| `PENDING_QUESTIONS` | 需求待办未清空 | 向用户问清列出的问题 → `document_job.update_requirements(requirements={...}, pending_questions=[])` → 重新 confirm_plan / generate |
| `Template contract still has unresolved confirmation items: [...]` | 有 confirm 项未决 | 把列出的项集中问用户一次 → 一次 `set_contract` 写入全部决定（action 用 preserve/rewrite/delete）→ confirm_plan |
| `UNKNOWN_CONTRACT_ELEMENT` | 契约里的 element_id 在模板中不存在 | 用错误信息里列出的合法表格 ID 或 `docx_template_query` 查真实 ID，改正后重发 |
| `PLAN_NOT_CONFIRMED` | 提纲改动后未确认 | 调 `document_job.confirm_plan`；确认成功前不要重试 upsert_section |
| `CONTRACT_LOCKED` | 计划确认后试图改契约 | 只有用户明确改变决定时：`unlock_contract` → `set_contract` → `confirm_plan`；否则放弃改动 |
| `Template table still requires user confirmation: body.tblNNNN` | 某张表没有决定 | 按错误里的 JSON 样例用 `set_contract` 给该表一个 action，然后 confirm_plan 一次 |

## 写作与来源类

| 错误 | 含义 | 正确的下一步 |
| --- | --- | --- |
| `EMPTY_SECTION_OVERWRITE` | 空内容会抹掉已有正文 | 只想改来源元数据 → 用 `set_provenance`；确实要清空该章 → 先向用户确认 |
| `SOURCE_GROUNDING_REQUIRED` | 文献综述章节缺真实来源 | 先 `record_web`/确认工作区来源 → `get_grounding_gaps` → 对已有正文只用 `set_provenance`；正文为空的章节重写并带 source_ids。不要动提纲 |
| `UNSOURCED_PROJECT_METRIC` | 项目指标没有出处 | 数据来自用户/已确认来源 → 带上 source_ids 与 fact_status；是合理假设 → 写入 `outline.assumptions` 并重新确认计划，正文加【假设】标识 |
| `UNCONFIRMED_PROJECT_ASSUMPTION` | 假设数值未在提纲展示 | 把数值写进 `outline.assumptions` → `confirm_plan` → 重写该章 |

## 生成与验证类

| 错误 | 含义 | 正确的下一步 |
| --- | --- | --- |
| `Required document sections are missing: [...]` | required 叶子章节没写 | 按列出的 ID 逐章 `upsert_section` 补齐 |
| `PLACEHOLDER_TITLES` | 提纲仍是 section-N 占位标题 | 用真实中文标题重新 `set_plan`（或 upsert 时带 title），确认后再生成 |
| `TABLE_COLUMN_MISMATCH` | 表格数据列数超过模板 | 压缩数据到模板列数，或与用户确认改为 preserve |
| `Replacement data is required for template table` | rewrite 表格缺数据 | 数据放进目标章节 `upsert_section.tables`（target_element_id/headers/rows），不要放契约 |
| `NO_CONTENT_CHANGE` | 内容没变，重新生成无意义 | 修 QA 问题：改章节内容或用 `docx_edit`；环境类问题向用户说明。不要再调 generate |
| `DOCX_QA_BLOCKED`（verify 返回 ok=false） | 有 blocking finding | 读返回的 `findings[]`：`category=document` → 按 anchor 用 `docx_edit` 修复（≤2 轮）→ deterministic → all；`category=environment` → 如实告知用户，不修文档 |
| `Published document version already exists` | 输出文件名被占用 | 换一个 `output_name` 重新 generate；不要删除用户文件 |
| `Revision conflict: current is vNNN` | base_revision 过期 | `get_active` 读取最新 current_revision 后重发 docx_edit |
| `Paragraph/Table target must resolve exactly once` | 定位有歧义 | 用更长的唯一文本、`body.pNNNN`/`body.tblNNNN` 精确定位；仍有歧义就问用户选哪个 |

## 环境类（不要修文档，向用户说明）

Word ExecutionBroker 未配置、PyMuPDF 缺失、视觉模型未配置/失败、模板字体未安装——这些 finding 带 `category="environment"`。修复动作是装依赖/装字体/配模型，属于用户环境；继续 docx_edit 只会浪费轮次。说明哪一道门槛没过、需要用户做什么，然后停下。
