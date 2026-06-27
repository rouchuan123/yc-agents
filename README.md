# YCore

`YCore` 是一个面向 code agent 的本地 Agent Harness，面向中文用户，用 CLI 把 Skill 选择、工具边界、trace/state、eval 和 verification 串成可复盘的工程闭环。

它不是聊天壳，也不是把某个场景写死进全局 prompt。YCore 的全局运行时只负责受控执行：选择合适的 Skill、注入工作区上下文、通过 ToolGateway 调用工具、记录过程证据，并把结果交给 eval 与 verification 检查。

## 项目定位

当前第一条具体落地线是 `code-review`：让 agent 读取本地仓库、建立项目地图、追关键链路、识别架构风险和测试缺口。`eval-writer` 用来为 code agent 设计 deterministic eval、真实模型 smoke eval 和人工 rubric。

当前仓库默认发布两个示例业务 Skill：`code-review` 和 `eval-writer`。它们是 YCore code-agent 定位的首批落地能力，后续可以继续扩展 bugfix、代码修改和功能实现 agent。

## CLI 主线

运行：

```powershell
python main.py
```

CLI 顶部会显示当前工作区、模型、估算上下文占用、Git 分支和 session 编号。常用命令：

- `/session`：查看或切换当前 workspace 的会话。
- `/session new <title>`：创建新会话。
- `/workspace`：查看或切换工作区。
- `/workspace add <path>`：添加一个已有目录作为工作区。
- `/status`：查看当前状态。
- `/stop`：停止当前正在处理的任务。
- `/skills`：查看当前可用技能。
- `/clear`：清空当前屏幕内容，不删除 session 记忆。

## 默认 Skill

- `code-review`：项目体检和变更审查，重点是代码证据、调用链、风险分级、测试缺口和最小验证。
- `eval-writer`：为 code agent、工具边界、trace/state、verification 和输出质量设计评测方案。

具体工作流放在 Skill 中，不写入全局 prompt。

## 默认工具

代码代理主线优先使用本地证据：

- `workspace_files`：列出当前工作区可读文件。
- `file_reader`：读取代码、配置、Markdown、PDF 和 `.docx` 需求或规格文档。
- `code_search`：搜索符号、调用点、配置项和测试覆盖。
- `git_inspector`：只读查看 status、diff、commit、本地 refs 和 blame。
- `verification_runner`：运行白名单内的最小验证命令。
- `markdown_writer`：在用户要求保存时写入 Markdown 输出。

`rag_search` 只作为可选上下文检索，不是 code-review 的主路径。`web_search` 仅用于用户明确需要外部或最新信息的场景。

## 核心能力

- 从 `SKILL.md` 加载技能，并把技能作为可维护资产。
- 通过 `SkillRuntimeAgent` 做技能候选发现、选择和执行。
- 通过 `PromptBuilder` 集中组装运行时协议、项目指令和模式协议。
- 支持工作区根目录 `YCORE.md` 与本地 `.ycore/YCORE.md` 两层项目指令。
- 通过 `ToolGateway` 管理工具权限、参数校验、审批边界和追踪记录。
- 在当前 workspace 的 `.ycore/runs/` 下写入输入、输出、trace 和 state checkpoint。
- 用 eval runner 与 VerificationGate 把“模型说完成”转成可检查证据。

## 架构

```mermaid
flowchart LR
    User["用户请求"] --> CLI["YCore CLI"]
    CLI --> Runtime["YCAgentRuntime"]
    Runtime --> Agent["SkillRuntimeAgent"]
    Agent --> Selector["Skill 选择"]
    Selector --> Skill["选中的 Skill"]
    Runtime --> Gateway["ToolGateway"]
    Gateway --> Tools["代码证据工具"]
    Runtime --> Trace["Trace + State + Outputs"]
    Trace --> Eval["Eval + Verification"]
```

更多边界说明见 [docs/architecture.md](docs/architecture.md)。

## 快速开始

| 任务 | 命令 |
| --- | --- |
| 创建虚拟环境 | `python -m venv .venv` |
| 安装依赖 | `pip install -r requirements.txt` |
| 运行 CLI | `python main.py` |
| 运行测试 | `python -m pytest -q` |
| 运行本地检查 | `powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1` |
| 运行离线 eval demo | `python scripts/demo_eval_run.py` |

## 项目结构

- `main.py`：CLI 入口和运行时装配。
- `yc_agents/agents`：Agent 编排逻辑。
- `yc_agents/cli`：终端交互界面、session 和 workspace 命令。
- `yc_agents/eval`：评测 case、runner、metrics 和 report。
- `yc_agents/harness`：运行时、权限、追踪、状态、verification 和工具网关。
- `yc_agents/prompts`：集中 prompt 组装和项目指令加载。
- `yc_agents/rag`：可选的本地上下文检索基础设施。
- `yc_agents/skills`：技能定义、加载、发现和注册表。
- `yc_agents/tools`：具体工具实现和工具注册表。
- `eval/cases`：code agent deterministic eval cases。
- `skills`：面向用户发布的 Skill。
- `tests`：Python 单元测试。

## 当前边界

- 当前只保留 CLI 端。
- 默认发布 `code-review` 和 `eval-writer` 两个 code-agent 落地 Skill。
- 保留通用 `.docx` 文件读取能力，方便读取需求或规格文档。
- 不提供 Word 排版、格式修正或文档样式处理能力。
- RAG 是可选 context infrastructure，不是主产品故事。
