---
name: demo-skill
description: A minimal example skill used as a template for future skills.
allowed_tools:
  - markdown_writer
---

# 示例 Skill

## 什么时候使用

当你需要参考一个最小 Skill 包格式，或者准备创建新的 Skill 包时，可以参考这个示例。

## 工作流程

1. 先判断用户请求是否适合这个 Skill。
2. 阅读 YAML front matter，确认 Skill 名称、描述和允许使用的工具。
3. 阅读 Markdown 正文，理解任务步骤、约束和完成标准。
4. 按照工作流程完成任务，并返回清晰的结果。

## 约束

- 一个 Skill 只聚焦一种相对明确的任务。
- 任务方法论写在 `SKILL.md` 正文里。
- Runtime 逻辑、工具执行逻辑、权限判断逻辑不要写进 Skill。
- 示例 Skill 只作为模板，不默认参与正式运行。

## 完成检查项

- Skill 有明确使用场景。
- 工作流程清楚。
- 约束条件明确。
- `allowed_tools` 已在 YAML front matter 中声明。