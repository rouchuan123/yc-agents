from pathlib import Path


# 审批模式 → 需要人工批准的风险等级。工具用 BaseTool.risk 声明自己的
# 风险（read/write/execute），模式命中声明时 gateway 才会走审批回调。
APPROVAL_MODE_GATED_RISKS = {
    "off": frozenset(),
    "execute": frozenset({"execute"}),
    "write_and_execute": frozenset({"write", "execute"}),
}


class HumanApprovalGate:
    """风险声明驱动的审批门。

    旧实现按硬编码工具名集合判定（与实际注册工具零交集，从不触发）；
    现在改为读取工具的 risk 类属性，配合 ycore.json 的
    tools.approval.mode 决定是否需要人工批准。默认 'off' 保持免审直通，
    不改变既有用户体验。写路径保护由 path_policy 与各写盘工具自身的
    路径校验负责，审批门不再承担文件级检查。
    """

    def __init__(self, project_root=".", mode="off"):
        self.project_root = Path(project_root).resolve()
        normalized = str(mode or "off").strip().lower()
        if normalized not in APPROVAL_MODE_GATED_RISKS:
            supported = "、".join(sorted(APPROVAL_MODE_GATED_RISKS))
            raise ValueError(
                f"未知的审批模式：{mode}。tools.approval.mode 只支持 {supported}。"
                "off 表示全部免审直通；execute 只审执行类（execute 风险）工具；"
                "write_and_execute 同时审写盘类（write 风险）与执行类工具。"
            )
        self.mode = normalized
        self.gated_risks = APPROVAL_MODE_GATED_RISKS[normalized]

    def check_tool_call(self, tool_name, arguments=None, risk="read"):
        arguments = arguments or {}
        risk = str(risk or "read").strip().lower()

        if risk in self.gated_risks:
            return self._needs_approval(
                action="tool_call",
                reason=(
                    f"工具 {tool_name} 声明了 {risk} 风险，"
                    f"当前审批模式（{self.mode}）要求先获得人工批准"
                ),
                tool_name=tool_name,
                risk=risk,
                arguments=arguments,
            )

        return self._allowed(
            action="tool_call",
            reason=f"Tool call is allowed: {tool_name}",
            tool_name=tool_name,
            risk=risk,
            arguments=arguments,
        )

    def _allowed(self, **payload):
        return {
            "allowed": True,
            "needs_approval": False,
            **payload,
        }

    def _needs_approval(self, **payload):
        return {
            "allowed": False,
            "needs_approval": True,
            **payload,
        }
