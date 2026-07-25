# 连续修订与版本规则

- 每次修改都基于 current revision 并生成下一不可变版本。
- `replace_text` 必须设置精确预期替换数。
- `replace_section` 需要唯一标题或 element locator。
- 表格操作优先使用表题、表头或 element ID；两个候选同时匹配时先询问。
- `set_style` 只修改用户明确指出的对象和属性，不做全局格式归一化。
- `replace_image` 需要用户明确提供新图片；复杂图表不能伪装成普通图片自动重建。
- 修改后强制重新渲染和验证。
- rollback 只改变 current revision 指针；历史文件、QA 和来源记录保持不变。
