from abc import ABC, abstractmethod


class BaseTool(ABC):
    name = ""
    description = ""
    schema = None

    @abstractmethod
    def run(self, *args, **kwargs):
        raise NotImplementedError
