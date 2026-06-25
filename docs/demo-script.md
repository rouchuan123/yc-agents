# YCore 演示脚本

## 演示目标

展示 YCore 作为 CLI Agent runtime，如何把中文用户请求拆成 Skill 选择、工具调用、状态追踪和结果复核，而不是只生成一段口头回复。

## 演示前准备

- 执行 `pip install -r requirements.txt` 安装依赖。
- 执行 `python -m pytest -q` 确认测试通过。
- 准备一个普通项目目录作为 workspace。

## 场景一：项目审查

用户输入：

```text
请用 code-review 审查这个项目，重点总结架构、风险和测试缺口。
```

演示重点：

1. CLI 接收中文请求。
2. `SkillRuntimeAgent` 根据技能摘要选择 `code-review`。
3. `PromptBuilder` 注入 workspace、记忆、项目指令和选中 Skill。
4. 模型按 allowed tools 发起 `workspace_files` 和 `file_reader` 调用。
5. `ToolGateway` 校验工具权限和参数。
6. runtime 写入 `.ycore/runs/<session_id>/<run_id>/trace.json`、`state.json` 和 `final_output.md`。

## 场景二：Eval 方案

用户输入：

```text
请用 eval-writer 为这个 Agent 设计一组 eval case、指标和测试数据。
```

演示重点：

1. Skill 把模糊评估需求拆成目标、维度、用例、指标和执行流程。
2. 输出保持中文，方便中文用户直接阅读和二次修改。
3. 如果用户要求保存，使用 `markdown_writer` 生成 Markdown 文件。

## 可以展示的文件

- `.ycore/runs/<session_id>/<run_id>/input.md`
- `.ycore/runs/<session_id>/<run_id>/context.json`
- `.ycore/runs/<session_id>/<run_id>/trace.json`
- `.ycore/runs/<session_id>/<run_id>/state.json`
- `.ycore/runs/<session_id>/<run_id>/final_output.md`

## 五分钟讲解稿

YCore 是一个面向中文用户的本地 CLI Agent runtime。它不把某个业务场景写进全局 prompt，而是把通用运行边界做扎实：Skill 选择、工作区上下文、项目指令、工具权限、trace、state 和输出复核。

具体能力由 Skill 提供。当前默认发布 `code-review` 和 `eval-writer` 两个示例业务 Skill，用来展示项目审查和评估方案生成这两类常见中文用户需求。

## 常见追问

- Skill 如何声明 allowed tools？
- 项目根 `YCORE.md` 和本地 `.ycore/YCORE.md` 谁优先？
- 工具调用失败时 runtime 如何记录和恢复？
- 没有合适 Skill 时 Agent 如何普通回答？
- trace 和 state 如何复核一次运行？
