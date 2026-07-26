---
name: docx-template-authoring
description: 从用户附加的一篇已写好的 Word .docx 中提取页面、字体字号、行距、缩进、编号、表格、页眉页脚等精细排版和章节结构，结合用户需求、已确认的工作区资料及必要的网页搜索生成类似的新 DOCX，并支持自然语言连续修改、视觉验收、版本历史和回滚。用户说“照这个Word做一份类似文档”“沿用这个排版和结构”“修改刚生成的Word”或附加成品DOCX作为参考模板时使用。
triggers:
  - 文档
  - 生成文档
  - 写文档
  - Word
  - Word文档
  - DOCX
  - 导出Word
  - 文档模板
  - 沿用排版
  - 沿用格式
---

# 成品 Word 模板仿写与连续修订

面向中文普通用户：用户附加的成品 DOCX 是排版权威，用户确认是业务内容权威。复用模板的精确排版和结构、重写旧业务内容；不要求用户理解样式 ID、OOXML 或排版单位。

流程主线（每步的门槛由工具强制，报错时按 [references/recovery-playbook.md](references/recovery-playbook.md) 的对照表行动，不要盲目重试）：

```
get_active → create → analyzer(一次) → 契约 set_contract → 需求/来源确认
→ set_plan → confirm_plan → 逐章 upsert_section → docx_generate
→ docx_verify(deterministic → all) → [docx_edit 修复] → 交付 → 连续修订
```

## 每轮起点

1. 每轮先调用一次 `document_job.get_active`（不要重复调用）读取当前任务与附件。后续判断只基于 active job 和 current revision，不凭聊天记忆猜测。
2. 无任务但有唯一模板附件 → 直接 `document_job.create`（可省略 attachment_id）；多个不同模板附件 → 列出名称和 ID 请用户选择。附件列表为空时不要让用户去 /attach：工作区根目录恰有一个 .docx 时 create 会自动导入（返回 `auto_imported_from`）；多个候选或用户点名了文件时用 `document_job.create(template_path="<绝对或相对工作区根的路径>")`；确实找不到 .docx 才向用户询问文件路径。不要编造附件 ID。
3. 用户输入过短或含义不明（如单个字、单个数字）且当前没有明确的待办下一步时，先用一句话确认意图，不要直接触发工具链。

## 模板分析与查询

1. 创建任务后调用一次 `docx_template_analyzer`。分析是幂等的：重复调用只返回缓存摘要，不要用它“刷新”状态。
2. 排版细节按需用 `docx_template_query` 查询：
   - 默认返回精简视图（text+role），足够做契约分类；`limit` 保持小（≤20）。
   - 需要精确格式时查单个 `element_id` 或加 `detail=true`；输出有硬上限，被截断时缩小范围而不是加大 limit。
3. 永远不要用 `file_reader` 读 `template-spec.json`（工具会拒绝），也不要用正文预览代替模板分析。

## 模板契约

1. 将元素分类为 `preserve`（页面家具、确认保留的品牌）、`rewrite`（项目名、人名、日期、旧正文）、`reuse_structure`（章节、表格几何、图片位置）、`confirm`（Logo、公司名、免责声明、复杂对象旧内容）。合法动作只有这五个加 `delete`；没有 `confirmed`。
2. canonical 写法：`{"tables":[{"element_id":"body.tbl0000","action":"rewrite"}]}`。用户说“保留表格结构、重写内容”= `action:"rewrite"`。element_id 必须真实存在（未知 ID 会被 UNKNOWN_CONTRACT_ELEMENT 拒绝）。
3. `set_contract` 返回 `remaining_confirm_items`：非空时把这些项集中问用户一次，拿到全部决定后用一次 `set_contract` 写入；为空才有资格 `confirm_plan`。
4. 契约不承载新表格数据。重写数据随目标章节的 `upsert_section.tables` 传入：`{"target_element_id":"body.tbl0000","headers":[...],"rows":[...]}`，且列数不得超过模板列数。
5. SmartArt、图表、嵌入对象、文本框只支持保留、确认或删除；说明限制并集中询问，不得假装已编辑。

详细规则见 [references/template-contract.md](references/template-contract.md)。

## 需求、来源与计划确认

1. 集中一次询问：主题、读者、用途、必需数据、期望篇幅、联网许可、品牌与免责声明处理。不问模板已能确定的排版参数。
2. 用 `document_job.update_requirements` 保存回答；全部问清后必须显式传 `pending_questions=[]` 清空待办，否则 confirm_plan 会被 PENDING_QUESTIONS 挡住。
3. 来源边界：`document_source.discover` 只列候选；用户确认后（confirm 是整体替换，一次给全所有 ID）才能 `ingest`/`search`。联网需用户允许，实际采用的网页用 `record_web` 登记。文献综述类文档必须真实来源：每个非空章节 `fact_status=grounded` + 合法 `source_ids`，不得用 draft/assumption 编造作者、年份、题名。见 [references/source-policy.md](references/source-policy.md)。
4. `set_plan` 保存递归 `sections[].children` 提纲，每个节点都要有真实中文标题（占位标题会在生成时被 PLACEHOLDER_TITLES 拒绝）。展示一次完整计划：提纲、来源、联网计划、保留/替换项、假设、复杂对象限制。
5. 用户明确确认且 `remaining_confirm_items` 为空后调用 `confirm_plan`。确认后契约锁定：不要再碰 set_plan/set_outline/set_contract；只有用户明确改变决定时才 `unlock_contract` → 改契约 → 重新确认。

需求字段见 [references/requirement-schema.md](references/requirement-schema.md)。

## 逐章写作

1. 计划确认后按提纲逐章 `upsert_section`，一次调用带齐：`content`、`source_ids`、`fact_status`、（如有）`tables`。title 可省略——自动继承确认提纲的标题；不要传 "section-N" 这类占位标题。
2. 不要事后补账：写作时就带上来源，避免收尾时逐章 `set_provenance`。投资、营收、面积、产能等项目指标只能来自用户提供、已确认来源，或已在 `outline.assumptions` 展示确认的假设；`assumption` 章节正文必须显式出现“【假设】/暂按/测算假设”。
3. `upsert_section` 自带 `remaining`/`complete` 进度，不需要每章后再调 `get_missing`；也不要用 `get_section` 把已写正文拉回上下文（局部修订除外）。
4. 父章节和 `required:false` 章节可以只留标题不写正文；空的 required 叶子章节会阻止生成。
5. Markdown 表格语法会被转换为真实 Word 表格；不要把 `| --- |` 分隔线当正文。
6. 恢复旧任务补来源时：`get_grounding_gaps` → 对已有正文只用 `set_provenance`；不得重设提纲、不得用空 `upsert_section` 覆盖正文（工具会拒绝 EMPTY_SECTION_OVERWRITE）。

## 生成与验证

1. `docx_generate` 从模板副本生成不可变待验证版本（`delivery_ready=false`，不是交付物）。生成是确定性的：内容没变就重新生成会被 NO_CONTENT_CHANGE 拒绝——修复问题要改内容或用 docx_edit，而不是再跑一次 generate。
2. 验证两段式：先 `docx_verify(mode="deterministic")`（快、免费）；通过后再 `mode="all"`（Word 渲染 + 逐页视觉 QA + 发布门）。
3. 验证失败返回 `ok=false, error=DOCX_QA_BLOCKED`，`findings[]` 里有每条问题的 `anchor`/`page`/`suggested_action`/`category`：
   - `category="document"`：按 anchor 用 `docx_edit` 修复（最多两轮），再从 deterministic 重新验证；
   - `category="environment"`（字体、Word、视觉模型、PyMuPDF）：文档编辑修不了，向用户如实说明，不要陷入修复循环。
4. 只有 `mode="all"` 返回 `passed=true`、`delivery_ready=true` 和 `published_path` 后版本才发布到 `outputs/`。此前不得宣称完成或给出下载路径。唯一例外：确定性检查全过、阻塞全部为环境类时，征得用户明确同意后可用 `docx_verify(operation="publish", waive_environment=true)` 降级发布——豁免项记入 `delivery.waivers`，交付回复必须原样列出。

质量门槛见 [references/quality-checklist.md](references/quality-checklist.md)。

## 交付与连续修订

1. 交付回复必须包含：版本号、DOCX 路径（published_path）、使用的来源、剩余 warning（含字体等环境警告）、以及“可以继续用自然语言修改”的提示。PDF/PNG 只是内部 QA 产物，除非用户要求不作为交付物。
2. 用户说“第二章太短”“删掉负责人列”“标题改蓝色”→ 读取 active job 和 current revision，映射为 `docx_edit` 局部操作；目标多个候选时只询问目标对象。必须传当前 `base_revision`；版本冲突就重新读状态。
3. 修改生成新版本后重新走 deterministic → all 验证。回滚用 `document_job.rollback`——只切换当前版本指针，不删除历史。

操作与定位规则见 [references/revision-policy.md](references/revision-policy.md)；报错对照表见 [references/recovery-playbook.md](references/recovery-playbook.md)。
