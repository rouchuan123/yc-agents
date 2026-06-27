---
name: code-review
description: 当用户要求审查本地项目、做项目体检、总结代码结构、分析架构风险、识别安全或性能问题、评估测试缺口、检查技术栈质量或输出代码审查报告时使用。
triggers:
  - 代码审查
  - 项目审查
  - 项目体检
  - 架构总结
  - 架构风险
  - 风险分析
  - 安全审查
  - 性能审查
  - 测试缺口
  - code review
  - project audit
inputs:
  - project_files
  - workspace_context
outputs:
  - review_note
  - project_audit_report
allowed_tools:
  - workspace_files
  - file_reader
  - markdown_writer
  - git_inspector
  - code_search
  - verification_runner
examples:
  - 帮我审查这个项目
  - 总结当前仓库的架构和风险
  - 看看这个项目还缺哪些测试
  - 给这个本地仓库做一次项目体检
---

# 代码审查 Skill

这个 Skill 面向中文用户，用于做本地项目体检：阅读仓库、建立项目地图、追关键链路、识别架构/安全/性能/质量风险，并评估测试缺口。核心原则：先读项目，再追链路，最后下结论；所有重要判断都要有文件证据，不要提前总结。

## Code Agent 定位

这是 YCore 第一个具体落地的 code agent Skill。它不只是摘要仓库，而是用本地代码证据、工具 trace 和必要的 verification 输出，形成可复盘的项目审查结果。

## 模式边界

- 主要模式是本地项目体检，不是 PR diff 审查。
- 如果用户明确要求审查当前改动、staged diff、commit、分支对比或 PR 类变更，切换到变更/PR 审查模式。
- 不要把未读取的文件、未运行的命令、未确认的 CI 状态写成事实。

## 审查模式

### 项目体检模式

当用户要求审查整个项目、架构风险、测试缺口或项目健康度时使用。先用 `workspace_files` / `code_search` 建项目地图，再用 `file_reader` 深读 README、配置、入口、核心模块和测试；用 `code_search` 搜索调用链、共享工具和相关测试；必要时用 `verification_runner` 跑最小验证。

### 变更/PR 审查模式

当用户要求审查当前改动、staged diff、某个 commit、分支对比或 PR 类变更时使用。先用 `git_inspector` 确认 review scope：当前工作区用 `status` 和 `diff_worktree`，暂存区用 `diff_staged`，提交审查用 `show_commit`，分支/PR 审查用 `diff_refs`。分支/PR 审查不自动 fetch，只基于本地 refs，并在输出中说明这个限制。

确认范围后，用 `code_search` 找受影响调用链、相关测试、配置和共享工具；用 `file_reader` 深读变更文件和关键上下文；用 `verification_runner` 跑默认允许的最小验证。重型验证（如 build、ruff check）只有在用户明确要求时才运行；否则先询问。

## 工作流程

1. 先判断审查模式：项目体检模式或变更/PR 审查模式。
2. 项目体检模式用 `workspace_files` 建立项目地图；变更/PR 审查模式先用 `git_inspector` 确认 review scope。
3. 用 `file_reader` 阅读最小必要集合：README/项目说明、依赖与配置、入口文件、核心模块、关键工具或服务、现有测试。不要只读文件名就判断。
4. 用 `code_search` 搜索调用链、受影响文件、共享工具和相关测试，再用 `file_reader` 深读关键文件。
5. 识别语言、框架、包管理器、运行方式和测试方式。按需读取参考资料：只加载当前技术栈和当前风险相关的 `references/` 文件。
6. 用 `verification_runner` 跑默认允许的最小验证；重型验证必须用户明确要求。
7. 至少追一条关键链路：从 CLI/API/任务入口或变更入口开始，追到核心业务逻辑、工具/服务调用、状态或数据流、错误处理，再对照相关测试。
8. 做横向审查：架构边界、安全输入与权限、性能与可靠性、通用代码质量、常见 bug、测试覆盖。必要时读取对应横向审查指南。
9. 输出事实时标注证据：重要结论要绑定具体文件路径，能定位行号时给出行号；区分“已确认事实”“基于代码的推断”“未确认事项”。
10. 做风险分级：按 P0/P1/P2 或 高/中/低说明影响、证据、触发条件和修复方向。没有证据的猜测不要放进确定问题。
11. 检查测试缺口：说明已有测试覆盖哪些行为，缺少哪些关键路径、边界条件、错误路径、权限边界、回归风险，以及建议运行哪些验证命令。
12. 用户要求保存时，用 `markdown_writer` 写出中文审查报告。

## 按需读取参考资料

优先读项目文件；只有当技术栈或风险类型已经明确时，才按需读取参考资料。不要一次性加载全部参考文件。

### 横向审查指南

| 场景 | 参考文件 |
| --- | --- |
| 架构边界、SOLID、分层、反模式、耦合内聚 | `references/architecture-review-guide.md` |
| 安全、认证授权、输入校验、注入、敏感数据 | `references/security-review-guide.md` |
| 性能、复杂度、N+1、缓存、前端指标、数据库优化 | `references/performance-review-guide.md` |
| 通用质量、复用、参数膨胀、抽象泄漏、TOCTOU、冗余状态 | `references/code-quality-universal.md` |
| 常见 bug 和跨语言易错点 | `references/common-bugs-checklist.md` |
| 审查沟通原则和严重级别参考 | `references/code-review-best-practices.md` |

### 语言与框架指南

| 技术栈 | 参考文件 |
| --- | --- |
| Python | `references/python.md` |
| Django / DRF | `references/django.md` |
| FastAPI | `references/fastapi.md` |
| TypeScript | `references/typescript.md` |
| React | `references/react.md` |
| Vue 3 | `references/vue.md` |
| Angular | `references/angular.md` |
| Svelte / SvelteKit | `references/svelte.md` |
| CSS / Less / Sass | `references/css-less-sass.md` |
| Node / NestJS | `references/nestjs.md` |
| Go | `references/go.md` |
| Rust | `references/rust.md` |
| Java | `references/java.md` |
| Kotlin / Android | `references/kotlin.md` |
| Swift / SwiftUI | `references/swift.md` |
| PHP | `references/php.md` |
| C# / .NET | `references/csharp.md` |
| C | `references/c.md` |
| C++ | `references/cpp.md` |
| Qt | `references/qt.md` |
| Zig | `references/zig.md` |

### 资产

| 用途 | 文件 |
| --- | --- |
| 快速体检清单 | `assets/project-audit-checklist.md` |
| 项目体检报告模板 | `assets/project-audit-report-template.md` |

## 工具边界

- `git_inspector` 只用于只读 Git 证据：status、diff、show、log、blame、本地 refs 对比；不自动 fetch，不 commit，不 push，不 reset。
- `code_search` 只用于搜索和小片段上下文，不替代 `file_reader` 做完整文件读取。
- `verification_runner` 只运行白名单验证命令。默认验证包括 Python/Java/Node/TypeScript 常见 test、lint、typecheck；重型验证（build、ruff check）必须用户明确要求。
- 不要用这些工具安装依赖、联网、部署、迁移数据库、删除文件或改变 Git 历史。

## 输出要求

- 默认用中文回答。
- 先给高信号结论，再给证据和建议；不要用泛泛的“整体不错”“建议加强测试”代替具体分析。
- 发现的问题按严重级别排序。每条问题至少包含影响、证据、触发条件和修复方向。
- 不要编造文件、测试结果、命令输出或项目事实；没读到就说明没读到，没运行就说明没运行。
- 如果信息不足，优先请求工具读取，而不是凭印象下判断；关键文件未读时，不要提前总结。
- 建议要可执行，例如指出应补的测试、应拆的模块、应验证的命令或应读取的参考文件。
- 审查不是摘要。必须解释代码如何运行、风险为什么成立、测试为什么不足。

## 深度检查清单

| 检查项 | 必须回答的问题 |
| --- | --- |
| 已读取文件清单 | 读了哪些文件？每个文件用于确认什么？ |
| 项目地图 | 入口、配置、核心模块、工具/服务、测试、脚本分别在哪里？ |
| 技术栈识别 | 项目使用哪些语言、框架、包管理器、测试框架？是否按需读取参考资料？ |
| 关键链路 | 一个主要请求、命令或任务如何从入口流到核心逻辑并返回结果？ |
| 证据 | 每个主要结论对应哪个文件或代码现象？ |
| 风险分级 | 问题影响多大、是否可复现、优先级是什么？ |
| 横向风险 | 架构、安全、性能、通用质量、常见 bug 是否有具体风险？ |
| 测试缺口 | 现有测试覆盖什么，还缺哪些行为、边界、权限和失败路径？ |
| 未确认事项 | 哪些判断因为文件、运行结果或上下文不足还不能确认？ |

## 推荐结构：项目体检模式

```markdown
## 高信号结论

## 已读取文件清单

## 项目地图

## 技术栈与按需参考资料

## 关键链路

## 发现的问题

按 P0/P1/P2 或 高/中/低分级；每条包含影响、证据、触发条件、修复方向和置信度。

## 横向风险

## 测试缺口

## 建议下一步

## 未确认事项
```

## 推荐结构：变更/PR 审查模式

```markdown
## Review Scope

说明审查的是当前工作区、staged diff、commit 还是本地 base...head。若是分支/PR 审查，说明不自动 fetch、只基于本地 refs。

## Findings

按 P0/P1/P2 或 blocking/important/nit 排序；每条包含影响、证据、触发条件、建议修复和置信度。

## Verification

列出 `verification_runner` 实际运行的命令、结果和未运行原因。重型验证未获明确授权时写明未运行。

## Unconfirmed Items

列出未读取文件、未运行命令、未同步远程 refs 或需要用户补充的信息。
```
