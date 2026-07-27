from abc import ABC, abstractmethod


class WrongToolError(ValueError):
    """The requested operation is safe but must be performed by another tool."""


class BaseTool(ABC):
    name = ""
    description = ""
    schema = None
    # 风险声明：审批门按它决定是否需要人工批准。
    # - read：只读工具（默认），任何审批模式下都免审。
    # - write：会写盘/落文件的工具，write_and_execute 模式下需要批准。
    # - execute：会执行外部命令/子进程的工具，execute 与
    #   write_and_execute 模式下都需要批准。
    risk = "read"

    @abstractmethod
    def run(self, *args, **kwargs):
        raise NotImplementedError
