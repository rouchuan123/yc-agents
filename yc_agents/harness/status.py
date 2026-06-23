from enum import Enum


class RunStatus(Enum):
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING_TOOL = "executing_tool"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
