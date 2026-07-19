import inspect


def invoke_llm(method, messages, usage_kind="primary"):
    """Call an LLM method without breaking third-party/fake implementations."""
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(messages)

    supports_keyword = "usage_kind" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if supports_keyword:
        return method(messages, usage_kind=usage_kind)
    return method(messages)
