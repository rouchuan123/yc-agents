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


class TruncatedOutputError(LLMCallError):
    """Output hit max_tokens (finish_reason=length); retry with a bigger budget,
    never feed the partial text into JSON protocol repair."""

    def __init__(self, message, *, partial_text="", max_tokens=None):
        super().__init__(
            message,
            retryable=True,
            cause_type="TruncatedOutput",
        )
        self.partial_text = partial_text
        self.max_tokens = max_tokens


class ToolCallingUnsupportedError(LLMCallError):
    """Provider rejected a request that carried the tools parameter: native
    function calling is unavailable on this model. Callers should downgrade
    the current turn to the json-protocol text loop instead of retrying the
    same request."""

    def __init__(self, message, *, status_code=None):
        super().__init__(
            message,
            retryable=False,
            status_code=status_code,
            cause_type="ToolCallingUnsupported",
        )
