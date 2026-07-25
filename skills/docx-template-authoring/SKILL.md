---
name: docx-template-authoring
description: 从用户附加的一篇已写好的 Word .docx 中提取页面、字体字号、行距、缩进、编号、表格、页眉页脚等精细排版和章节结构，结合用户需求、已确认的工作区资料及必要的网页搜索生成类似的新 DOCX，并支持自然语言连续修改、视觉验收、版本历史和回滚。用户说“照这个Word做一份类似文档”“沿用这个排版和结构”“修改刚生成的Word”或附加成品DOCX作为参考模板时使用。
---

# 成品 Word 模板仿写与连续修订

面向中文普通用户，将用户附加的成品 DOCX 视为设计权威。复用其精确排版和结构，重写旧业务内容；不要要求用户理解样式 ID、OOXML、内容控件或排版单位。

## 每轮起点

1. 调用 `document_job` 的 `get_active` 读取当前文档任务及当前 Session 附件。
2. 如果没有任务但返回了一个模板附件，立即调用 `document_job.create`；唯一模板可省略 `attachment_id`。不要再次要求用户 `/attach`。
3. 如果返回多个不同模板，列出附件名称和 ID，只询问选择哪一个。只有附件列表确实为空时，才请用户执行 `/attach template "<path>"`；不要编造附件 ID。
4. 创建任务后调用 `docx_template_analyzer`。不要用 `file_reader` 的正文预览代替模板分析。
5. 后续轮次始终基于 active job 和 current revision，不依赖聊天记忆猜测当前文档。

## 模板蒸馏

1. 使用分析器输出的最终生效格式，不凭渲染截图猜字体、字号、行距或缩进。
2. 用 `docx_template_query` 按需查询正文、标题、表格或具体 element；不要把完整 `template-spec.json` 放进上下文。
3. 将模板元素归类为：
   - `preserve`：页面家具、确认保留的 Logo、装饰和固定声明；
   - `rewrite`：项目名称、人员、日期、数字和旧正文；
   - `reuse_structure`：章节、表格和图片位置模式；
   - `confirm`：Logo、公司名、免责声明及复杂对象中的旧业务内容。
4. 用 `document_job` 的 `set_contract` 保存分类和置信度。
   - 唯一 canonical 写法是 `{"tables":[{"element_id":"body.tbl0000","action":"rewrite"}]}`。
   - 用户说“保留表格结构、重写内容”时使用 `tables[].action="rewrite"`；不要写成 `confirm[].decision`，也不要使用不存在的动作 `confirmed`。
5. 发现 SmartArt、嵌入对象、复杂图表或文本框旧内容时，说明限制并集中询问保留、删除或图片替换；不得假装已编辑。

详细分类规则见 [references/template-contract.md](references/template-contract.md)。

## 需求与确认门槛

1. 集中询问新文档主题、读者、用途、必需数据、期望长度、联网许可、品牌信息和免责声明处理方式。
2. 使用 `document_job.update_requirements` 保存回答和仍缺的问题。
3. 不向用户询问从模板已能确定的字体、行距、缩进、页边距或表格样式。
4. 调用 `document_source.discover` 只列候选资料；用户确认前不得调用 `ingest` 或 `search`。
5. 用户确认来源后调用 `confirm`、`ingest`，再按章节调用 `search`。
6. 只有用户允许且确认资料不足、过时或确需外部信息时才调用 `web_search`；用 `document_source.record_web` 保存实际使用的网页来源。
   - 文献综述、研究综述和系统综述属于必须检索并落来源的文档类型。不得用 `fact_status=draft/assumption` 编造作者、年份、论文名、系统名或编号引用；每章使用 `fact_status=grounded` 和实际来源 ID。
   - 恢复旧任务时先调用 `document_content.get_grounding_gaps`。已有正文只用 `set_provenance` 更新 `source_ids`/`fact_status`；不得调用 `set_outline`，也不得用空的 `upsert_section` 覆盖正文。叶子章节正文为空时仍视为缺失，必须重新写入。
7. 生成前用 `document_job.set_plan` 保存并展示一次：文档提纲、确认来源、联网计划、保留项、替换项、假设和复杂对象限制。
8. 用户明确确认且所有 `confirm` 项已有选择后，调用 `document_job.confirm_plan`。未确认不得写章节或生成 DOCX。
9. 提纲统一使用递归 `sections[].children`；不要把二级、三级章节摊平成同级。输入中的顶层 `chapters` 会被兼容转换，但工具保存的是 canonical `sections`，每个节点都有 `level` 和 `parent_id`。
10. 每次 `set_plan` 或 `set_outline` 都会撤销此前确认。看到 `requires_plan_confirmation=true` 时，下一步必须调用 `document_job.confirm_plan`；遇到 `PLAN_NOT_CONFIRMED` 后不得重复 `upsert_section`。
11. `confirm_plan` 后模板契约会锁定。不要再次改写契约；只有用户明确改变保留/删除/重写决定时，才先调用 `unlock_contract`，再更新契约并重新确认计划。

需求字段见 [references/requirement-schema.md](references/requirement-schema.md)，来源边界见 [references/source-policy.md](references/source-policy.md)。

## 内容与生成

1. 计划确认后按提纲逐章生成，使用 `document_content.upsert_section` 保存；长文不得挤在单次最终回答中。
   - `upsert_section` 只回传章节摘要。每写若干章调用 `get_missing` 检查进度，继续依据已确认提纲和 missing ID 写作；除非局部修订需要，不要调用 `get_section` 把已写全文重新带回上下文。
2. 每章记录 `source_ids` 和 `fact_status`。投资额、营收、面积、建设期、产能等项目指标只能是用户明确提供、经已确认来源支撑，或已在提纲假设中展示并确认；通用市场报告不能支撑某一家公司的项目指标，不得补造。
   - `fact_status=assumption` 的章节必须在正文显示“【假设】”、暂按或测算假设等醒目标识，不能只保存在内部状态。
3. 调用 `document_content.get_missing`；required 章节齐全后才能调用 `docx_generate`。
   - 契约中的 `tables[].action` 只决定表格是保留、重写或删除。重写数据必须随目标章节的 `upsert_section.tables` 传入，格式为 `{"target_element_id":"body.tbl0000","headers":[...],"rows":[...]}`；不要把新任务的数据放在契约 `replacement_data` 中。
4. `docx_generate` 必须从模板副本开始并生成不可变待验证版本。它返回的 `delivery_ready=false` 不是交付物，且此时 `outputs/` 中不应出现该版本。不要调用 `workspace_write` 修改 DOCX 或模板原件。
5. 生成后立即调用 `docx_verify(mode="all")`。
6. 章节中的 Markdown 表格必须转换为真实 Word 表格，不得把竖线和分隔线作为正文插入。
7. 验证存在 blocking finding 或工具返回 `DOCX_QA_BLOCKED` 时不得宣称完成、不得给出可下载路径；根据可靠文字锚点调用 `docx_edit` 修复，最多两轮，然后重新验证。
8. 只有 `docx_verify(mode="all")` 返回 `passed=true`、`delivery_ready=true` 和 `published_path` 后，版本才会发布到 `outputs/`。
9. 视觉模型无结果、Word 渲染不可用或字体缺失时，明确说明未通过对应门槛。

质量门槛见 [references/quality-checklist.md](references/quality-checklist.md)。

## 连续修订

1. 用户说“第二章太短”“删掉负责人列”“封面标题改蓝色”时，先读取 active job 和 current revision。
2. 将自然语言映射为 `docx_edit` 的局部操作；目标有多个候选时只询问目标对象。
3. 必须传当前 `base_revision`；版本冲突后重新读取状态，不能覆盖较新版本。
4. 修改生成新版本后再次调用 `docx_verify`。不要直接覆盖历史版本或模板。
5. 用户要求回滚时使用 `document_job.rollback`；回滚只切换当前版本，不删除历史。

操作与歧义规则见 [references/revision-policy.md](references/revision-policy.md)。

## 完成标准

仅当以下条件全部成立时交付：

- 模板哈希未改变；
- required 章节齐全且来源边界已遵守；
- 当前版本的 `docx_verify` 没有 blocking finding；
- 当前 revision 同时满足 `qa_passed=true` 和 `delivery_ready=true`；
- 最终 DOCX 存在于 `outputs/<job-slug>/` 且非空；
- 最终回复给出版本、DOCX 路径、已使用来源、剩余 warning 和可继续修改的提示；
- PDF 和 PNG 仅作为内部 QA 产物，除非用户明确要求，否则不作为交付物。
