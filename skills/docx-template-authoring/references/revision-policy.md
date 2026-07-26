# 连续修订与版本规则

- 每次修改都基于 current revision 并生成下一不可变版本；`operations` 不能为空（空编辑会被拒绝，不会铸造相同版本）。
- 支持的操作（别名会被规范化，如 insert_paragraph→insert、replace→replace_text）：
  - `replace_text {old_text, new_text, expected_replacements}`：expected_replacements 是**出现次数**（同段两处算 2），数目不符时不做任何修改并报错；
  - `replace_section {target, content, title?}`：target 是唯一标题文本；
  - `insert {target, content}` / `delete {target, type?}` / `move {target, before}`；
  - `update_table {target, rows}`：rows 是含表头的全量行；
  - `delete_table_column {target, column}`：column 是索引或表头文字；
  - `set_style {target, style{style_id, alignment, line_spacing_pt, first_line_indent_pt, font_name, font_size_pt, bold}}`：只改用户明确指出的对象和属性，不做全局格式归一化；
  - `replace_image {target:"image-N", image_path}`：需要用户明确提供新图片；复杂图表不能伪装成普通图片自动重建。
- 目标定位：表格用 `body.tblNNNN`（零基）或唯一单元格文字，越界会报出可用 ID 列表；段落用唯一文本或 `body.pNNNN`；删除表格时可显式传 `type:"table"`。两个候选同时匹配时先询问用户。
- 必须传当前 `base_revision`；版本冲突后重新读取状态，不能覆盖较新版本。
- 修改生成新版本后强制重新验证：先 deterministic 再 all。
- 失败的编辑不会留下残留版本目录；重试前先解决报错本身。
- rollback 只改变 current revision 指针；历史文件、QA 和来源记录保持不变。
