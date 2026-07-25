# 成品模板语义契约

为每个有业务意义的元素记录：`element_id`、`role`、`action`、`confidence`、`reason` 和可选 `replacement_requirement`。

## 动作

- `preserve`：页面设置、确认保留的品牌装饰、固定页眉页脚。
- `rewrite`：标题、项目名、人名、日期、数字和旧正文。
- `reuse_structure`：标题层级、章节块、表格几何、题注和图片布局模式。
- `confirm`：Logo、公司名、免责声明、合规文字、客户信息和复杂对象中的旧内容。

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

用户说“保留结构，重写内容”表示保留该表格的几何和样式、替换业务数据，对应 `action: rewrite`。不要传 `confirm[].decision`，不要把 `confirmed` 当动作；合法动作只有 `preserve`、`rewrite`、`reuse_structure`、`confirm` 和 `delete`。

契约不承载新表格正文。对 `action: rewrite` 的表格，使用 `document_content.upsert_section` 将数据写入对应章节：

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
