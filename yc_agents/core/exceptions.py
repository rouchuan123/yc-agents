class YCAgentsError(Exception):
    pass


class LLMCallError(YCAgentsError):
    def __init__(
        self,
        message,
        *,
        retryable=False,
        status_code=None,
        cause_type=None,
    ):
        super().__init__(message)
        self.retryable = bool(retryable)
        self.status_code = status_code
        self.cause_type = cause_type
