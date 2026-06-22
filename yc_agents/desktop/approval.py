import uuid
from pathlib import Path

from yc_agents.desktop.events import DesktopEvent
from yc_agents.harness.permissions import HumanApprovalGate


class UIApprovalGate:
    def __init__(self, project_root, project_id, session_id, controller, emit):
        self.project_root = Path(project_root)
        self.project_id = project_id
        self.session_id = session_id
        self.controller = controller
        self.emit = emit
        self.base_gate = HumanApprovalGate(project_root)

    def check_tool_call(self, tool_name, arguments=None):
        decision = self.base_gate.check_tool_call(tool_name, arguments)
        if not decision.get("needs_approval"):
            return decision

        approval_id = f"approval_{uuid.uuid4().hex[:12]}"
        self.emit(
            DesktopEvent(
                type="approval_required",
                project_id=self.project_id,
                session_id=self.session_id,
                run_id=self.controller.run_id,
                payload={
                    "approval_id": approval_id,
                    "title": "需要确认工具调用",
                    "summary": decision.get("reason", ""),
                    "tool_name": tool_name,
                    "arguments": arguments or {},
                },
            ).to_dict()
        )
        ui_decision = self.controller.wait_for_approval(approval_id)
        return {
            **decision,
            "decision": ui_decision,
            "allowed": ui_decision in {"allow_once", "allow_for_project"},
            "needs_approval": False,
        }
