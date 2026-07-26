# 成品模板语义契约

为每个有业务意义的元素记录：`element_id`、`role`、`action`、`confidence`、`reason` 和可选 `replacement_requirement`。

## 动作

- `preserve`：页面设置、确认保留的品牌装饰、固定页眉页脚。
- `rewrite`：标题、项目名、人名、日期、数字和旧正文。
- `reuse_structure`：标题层级、章节块、表格几何、题注和图片布局模式。
- `confirm`：Logo、公司名、免责声明、合规文字、客户信息和复杂对象中的旧内容。
- `delete`：用户明确不要的元素。

合法动作只有以上五个；`confirmed` 不是动作，`confirm[].decision` 是被兼容的旧格式，不要主动使用。

## 默认置信度

- 页面与最终生效格式由解析器确定，不需要语义置信度。
- 明显项目变量可高置信度 rewrite。
- Logo、公司名和免责声明不得高置信度自动处理，必须进入集中确认。
- SmartArt、图表、嵌入对象和文本框只允许 preserve、confirm 或删除；首版不重建其内部结构。

模板规格是排版权威；用户确认是业务内容权威。二者冲突时，用户明确要求优先，并在契约中记录偏离。

## Tool 参数格式

`document_job.set_contract` 只使用 canonical collection 和 `action`：

```json
{
  "tables": [
    {"element_id": "body.tbl0000", "action": "rewrite"}
  ]
}
```

- 用户说"保留结构，重写内容"表示保留该表格的几何和样式、替换业务数据，对应 `action: rewrite`。
- `element_id` 必须真实存在于模板 spec（`body.tbl0000` 这类零基 ID 由分析器给出）；不存在会报 `UNKNOWN_CONTRACT_ELEMENT` 并列出合法表格 ID。
- set_contract 按 element_id 合并，返回 `contract_changed` 与 `remaining_confirm_items`：
  - `contract_changed=false` 时不要重复提交同样的契约；
  - `remaining_confirm_items` 非空 → 集中问用户一次，把全部决定用一次 set_contract 写入；为空 → 才调用 `confirm_plan`。
- confirm_plan 之后契约锁定（CONTRACT_LOCKED）；只有用户明确改变决定时才 `unlock_contract`。

## 表格数据的归属

契约不承载新表格正文。对 `action: rewrite` 的表格，用 `document_content.upsert_section` 把数据写入对应章节：

```json
{
  "tables": [
    {
      "target_element_id": "body.tbl0000",
      "headers": ["列一", "列二"],
      "rows": [["值一", "值二"]]
    }
  ]
}
```

- 每行（含 headers）的列数不得超过模板列数，否则生成前即报 `TABLE_COLUMN_MISMATCH`。
- 少于模板列数时，未覆盖的列会保留模板旧内容——确认这是用户想要的，否则补齐整行。
