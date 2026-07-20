# YCore 全局知识库

这份文档属于 YCore 的全局 RAG 知识库。无论当前激活哪个 Workspace，YCore 都会加载 `data/RAG_knowledge/` 中的 Markdown 文档。

## ToolGateway

`ToolGateway` 是工具执行的统一边界。它负责检查工具是否启用、验证调用参数、执行审批策略、限制重复调用与超时，并把工具调用和结果写入 Trace。Agent 不能绕过 ToolGateway 直接获得额外工具权限。

## Skill 与工具权限

Skill 提供领域工作流、证据要求和输出规范，但不授予工具权限。工具是否可用由 `ycore.json` 中的 `tools.entries.<tool>.enabled` 决定。Agent 只能调用当前 Workspace Context 中列出的已启用工具。

## Memory 与 RAG

Memory 用来保存用户偏好、历史会话和长期项目知识。全局 RAG 知识对所有 Workspace 可见，Workspace RAG 知识只对所属 Workspace 可见。两者都会先检索相关片段，再把片段交给模型生成答案。
