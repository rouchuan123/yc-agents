# YCore 演示脚本

## 演示目标

展示 YCore 作为通用 skill-driven 本地 Agent Harness，如何把中文用户请求拆成 Skill 选择、本地证据、工具调用、trace/state 和结果复核。当前演示用 `code-review` 和 `eval-writer`，但具体落地方向由 Skill 决定。

## 演示前准备

- 执行 `pip install -r requirements.txt` 安装依赖。
- 执行 `python -m pytest --basetemp .\.pytest-tmp -q` 确认测试通过。
- 准备一个普通代码仓库作为 workspace。
- 如果使用 `.venv`，先激活仓库虚拟环境；如果要验证 active workspace 自己的测试命令，使用 active workspace 的解释器。

当前可讲的真实 eval 基线是 `20260630-211458`。之前的 eval 记录已作废，只作为开发历史。

## 可复现离线 Eval Demo

不依赖真实模型凭证时，可以先运行确定性 demo：

```powershell
python scripts/demo_eval_run.py
```

输出文件：

- `outputs/eval/demo-results.json`

这个 demo 使用固定 runtime 模拟 Skill 选择和工具调用，展示 eval runner 如何记录最终输出、trace 指标和 case 结果。真实模型 demo 仍使用 `python main.py`。

## 当前真实 Eval 基线

当前有效真实 eval 输出位于：

- `outputs/eval/20260630-211458-code-review.json`
- `outputs/eval/20260630-211458-eval-writer.json`
- `outputs/eval/20260630-211458-runtime.json`
- `outputs/eval/20260630-211458-toolgateway.json`
- `outputs/eval/20260630-211458-context.json`

对应运行证据位于：

```text
E:\code\Ycore-demo\.ycore\runs\session_20260630_ea86176d\
```

演示时不要把自动指标包装成“最终通过率”。这次结果更适合讲 Agent 质量工程：真实 eval 跑通了，同时暴露出 required tool discipline、工具 schema、工具预算、verification 调用和输出结构弱匹配的问题。详细复盘见 `docs/eval-run-20260630-211458.md`。

## 场景一：code-review 项目体检

用户输入：

```text
请用 code-review 审查这个项目，重点总结架构风险和测试缺口。
```

演示重点：

1. CLI 接收中文请求。
2. `SkillRuntimeAgent` 根据技能摘要选择 `code-review`。
3. `PromptBuilder` 注入 workspace、记忆、项目指令和选中 Skill。
4. 模型从 `ycore.json` 已启用的全局工具中选择 `workspace_files`、`file_reader`、`code_search` 或 `verification_runner`。
5. `ToolGateway` 校验工具启用状态、参数和审批策略。
6. runtime 写入 `.ycore/runs/<session_id>/<run_id>/trace.json`、`state.json` 和 `final_output.md`。

## 场景二：eval-writer 设计 eval

用户输入：

```text
请用 eval-writer 为当前验证 Skill 设计 deterministic eval、真实模型 smoke eval 和人工 rubric。
```

演示重点：

1. Skill 把评估需求拆成目标、维度、case、指标、人工 rubric 和执行流程。
2. 解释 eval 不一定需要大模型参与：日常回归用 deterministic eval，手动演示再跑真实模型 smoke eval。
3. 输出保持中文，方便直接阅读和二次修改。
4. 如果用户要求保存，使用 `markdown_writer` 生成 Markdown 文件。

## 可以展示的文件

- `.ycore/runs/<session_id>/<run_id>/input.md`
- `.ycore/runs/<session_id>/<run_id>/context.json`
- `.ycore/runs/<session_id>/<run_id>/trace.json`
- `.ycore/runs/<session_id>/<run_id>/state.json`
- `.ycore/runs/<session_id>/<run_id>/final_output.md`

## 面试演示顺序

1. 先讲项目定位：通用 skill-driven 本地 Agent Harness。
2. 说明当前 eval 基线是 `20260630-211458`，旧 eval 口径已舍弃。
3. 跑离线 deterministic demo，展示 eval runner 的机械闭环。
4. 打开 `20260630-211458` 的 JSON 和 trace/state 输出，解释 Skill 选择、工具调用和失败分类。
5. 展示 ToolGateway、verification、memory/context、analytics 和可选 RAG 的设计点。
6. 说明当前 demo 只是第一批验证 Skill，后续可以换其他领域 Skill。

## 五分钟讲解稿

YCore 是一个面向中文用户的通用本地 Agent Harness。它不把某个业务流程写进全局 prompt，而是把通用运行边界做扎实：Skill 选择、工作区上下文、项目指令、全局工具开关、trace、state、eval 和 verification。具体落地方向由 Skill 决定，工具启用只由 `ycore.json` 决定。

当前我先用 `code-review` 和 `eval-writer` 做验证：前者证明 Harness 能支撑本地项目审查类 workflow，后者证明评测方案可以拆成 deterministic eval、真实模型 smoke eval 和人工 rubric。未来加入其他领域 Skill 时，复用的是同一套运行时、工具网关、trace 和 eval 框架。

当前真实 eval 基线不是完美通过，而是可复盘地暴露问题：Skill 选择、state checkpoint 和禁用工具边界比较稳定；required tool discipline、工具 schema、工具预算和输出结构检查还需要继续工程化。这比单纯展示一个好看的回答更有说服力。

## 常见追问

- 如何在 `ycore.json tools.entries` 中启用或关闭全局工具？
- 项目根 `YCORE.md` 和本地 `.ycore/YCORE.md` 谁优先？
- 工具调用失败时 runtime 如何记录和恢复？
- eval 为什么可以不依赖大模型？
- 新领域 Skill 如何接入同一套 Harness？
