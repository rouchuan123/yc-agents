import inspect


def invoke_llm(method, messages, usage_kind="primary", **kwargs):
    """Call an LLM method without breaking third-party/fake implementations."""
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(messages)

    has_var_keyword = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    supports_keyword = "usage_kind" in signature.parameters or has_var_keyword
    if supports_keyword:
        extra = {
            key: value
            for key, value in kwargs.items()
            if has_var_keyword or key in signature.parameters
        }
        return method(messages, usage_kind=usage_kind, **extra)
    return method(messages)
