# 需求字段与追问规则

## 必要字段

- `topic`：新文档主题。
- `title`：封面或首页标题；未单独提供时可由 topic 形成明确标题。
- `audience`：主要读者或接收方。
- `purpose`：文档用于评审、汇报、申请、销售、执行或存档。
- `must_include`：必须出现的章节、事实、数据和表格。
- `source_scope`：用户确认的附件与工作区资料。
- `web_allowed`：资料不足时是否允许联网。
- `brand_decision`：模板公司名称、Logo、页眉页脚如何处理。
- `disclaimer_decision`：旧免责声明保留、替换或删除。

## 可选字段

- 期望篇幅、语气、交付日期、图片、数据截止时间、引用格式和保密要求。

## 追问方式

- 合并为一次普通语言问题，最多列出当前真正缺失的内容。
- 不询问已经能从模板确定的排版参数。
- 冲突信息指出具体冲突，等待用户选择，不自行覆盖。
- 用户允许"按合理假设生成"时，在 requirements 中保存假设并在提纲确认时展示。
- 项目投资、营收、面积、建设期和产能等数字若是合理假设，必须逐项写入 `outline.assumptions`；每次修改假设或提纲后都要重新确认。

## pending_questions 的生命周期

- 模板分析会写入默认待办问题；它们会阻塞 `confirm_plan` 和 `docx_generate`（PENDING_QUESTIONS）。
- 保存回答时必须显式清空：`document_job.update_requirements(requirements={...}, pending_questions=[])`。
- 不传 `pending_questions` 表示"保持不变"，不会自动清空；仍有未答问题时传剩余问题列表。
- 重复调用 `docx_template_analyzer` 不会重置已清空的待办（分析是幂等的）。
