DEFAULT_PROVIDER = "openai_compatible"


PROVIDER_CAPABILITIES = {
    "deepseek": {
        "provider": "deepseek",
        "json_output": True,
        "tool_calling": True,
        "long_context": True,
    },
    "modelscope": {
        "provider": "modelscope",
        "json_output": True,
        "tool_calling": True,
        "long_context": True,
    },
    "openai": {
        "provider": "openai",
        "json_output": True,
        "tool_calling": True,
        "long_context": True,
    },
    "ollama": {
        "provider": "ollama",
        "json_output": True,
        "tool_calling": False,
        "long_context": False,
    },
    "vllm": {
        "provider": "vllm",
        "json_output": True,
        "tool_calling": True,
        "long_context": True,
    },
    DEFAULT_PROVIDER: {
        "provider": DEFAULT_PROVIDER,
        "json_output": True,
        "tool_calling": False,
        "long_context": False,
    },
}


def get_provider_capabilities(provider):
    normalized_provider = (provider or DEFAULT_PROVIDER).lower()
    capabilities = PROVIDER_CAPABILITIES.get(
        normalized_provider,
        PROVIDER_CAPABILITIES[DEFAULT_PROVIDER],
    )

    return dict(capabilities)
