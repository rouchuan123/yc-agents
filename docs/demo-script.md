# YCore 演示脚本

## 演示目标

展示 YCore 作为通用 skill-driven 本地 Agent Harness，如何通过 `docx-template-authoring` 支撑一个真实、可交付、可验证的 Word 文档工作流。具体业务能力由 Skill 决定，底层 Runtime 继续负责工具治理、Workspace Context、Trace/State、Eval 与 Verification。

## 演示前准备

- 安装项目依赖并确认 `ycore` 可以启动。
- 配置 `DEEPSEEK_API_KEY` 和 `MIMO_API_KEY`。
- Windows 环境安装 Microsoft Word，确保文档可以渲染为 PDF。
- 准备一个成品 `.docx` 模板和必要的参考资料。
- 执行 `python -m pytest --basetemp .\.pytest-tmp -q` 确认测试通过。

## 场景一：生成并验证 Word 文档

在演示工作区启动：

```powershell
ycore
```

添加模板和参考资料：

```text
/attach template E:\documents\文献综述模板.docx
/attach reference E:\documents\参考资料.pdf
```

用户输入：

```text
请使用这个模板生成一篇《Agent 在日常生活中的应用》文献综述。
面向普通读者，保留模板的标题层级和表格结构，
使用我提供的参考资料，并允许补充公开网络来源。
```

演示重点：

1. `SkillRuntimeAgent` 选择 `docx-template-authoring`。
2. 文档工具分析标题、正文、表格、字体、页眉页脚和页面结构。
3. Agent 集中确认需求、模板语义契约和资料来源。
4. DeepSeek 负责内容生成、推理和工具流程。
5. `docx_generate` 生成不可变待验证版本，此时还不是交付物。
6. `docx_verify(mode="deterministic")` 完成结构和内容检查。
7. `docx_verify(mode="all")` 渲染 PDF/PNG，并由 MiMo 逐页执行视觉 QA。
8. 只有通过发布安全门后，DOCX 才写入 Workspace 的 `outputs/`。

## 场景二：连续修订

在成功交付后的新一轮输入：

```text
把第二章再扩充一些，并将第一个表格的最后一列删除。
```

演示重点：

1. 读取当前 DocumentJob 和 current revision。
2. 使用 `docx_edit` 执行局部修改，不覆盖旧版本。
3. 创建新的不可变版本。
4. 新版本重新经过 deterministic QA 和 MiMo 视觉 QA。
5. `/document history` 可以查看版本历史，`/document rollback <version>` 可以切换当前版本。

## 场景三：展示 Harness 证据

可以展示：

- `.ycore/runs/<session_id>/<run_id>/input.md`
- `.ycore/runs/<session_id>/<run_id>/context.json`
- `.ycore/runs/<session_id>/<run_id>/trace.json`
- `.ycore/runs/<session_id>/<run_id>/state.json`
- `.ycore/runs/<session_id>/<run_id>/final_output.md`
- `.ycore/document-jobs/<job_id>/revisions/`
- `.ycore/document-jobs/<job_id>/qa/`
- `.ycore/document-jobs/<job_id>/vision-cache.json`

这些文件用于说明 YCore 不只是输出一段文本，还能保存需求、来源、工具调用、版本、QA 结果和发布状态。

## 场景四：展示可扩展性

可以简短运行 `code-review`：

```text
请用 code-review 审查当前项目，重点总结架构风险和测试缺口。
```

这里的重点不是再次完整演示代码审查，而是说明两个不同领域的 Skill 复用了相同的 Skill 选择、ToolGateway、Trace、State、Eval 和 Verification 基座。

## 五分钟讲解稿

YCore 是一个面向中文用户的通用本地 Agent Harness。它不把业务流程写死在全局 Prompt 或 Runtime 中，而是提供 Skill 选择、Workspace Context、工具边界、Trace、State、Eval 和 Verification 等通用能力。

当前重点落地点是 `docx-template-authoring`。这个 Skill 从成品 Word 模板出发，完成模板分析、需求与来源确认、内容生成、不可变 DOCX 版本、自然语言连续修订，以及确定性检查和 MiMo 逐页视觉 QA。只有验证通过或用户明确同意环境豁免后，文档才会正式发布。

文档能力证明这套 Harness 可以支撑有状态、有工具、有版本、有质量门槛的真实业务流程。后续增加其他领域 Skill 时，可以继续复用同一套 Runtime 和治理能力。

## 常见追问

- 为什么文档流程放在 Skill 中，而不是写进全局 Prompt？
- DeepSeek 和 MiMo 分别负责什么？
- MiMo 超时、限流或服务端错误时如何重试？
- 为什么字体缺失只产生 warning？
- 如何保证失败版本不会被误当成交付物？
- 如何增加新的领域 Skill 并复用同一套 Harness？
