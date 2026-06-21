import os
from dataclasses import dataclass, field

from yc_agents.core.provider import get_provider_capabilities


@dataclass
class ProviderConfig:
    provider: str
    model: str
    api_key: str
    base_url: str
    timeout: int = 60
    capabilities: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.capabilities:
            self.capabilities = get_provider_capabilities(self.provider)

    @classmethod
    def from_env(cls, env=None):
        source = env or os.environ
        model = source.get("LLM_MODEL_ID")
        api_key = source.get("LLM_API_KEY")
        base_url = source.get("LLM_BASE_URL")
        provider = source.get("LLM_PROVIDER", "auto").lower()
        timeout = cls._parse_timeout(source.get("LLM_TIMEOUT", "60"))

        if not model:
            raise ValueError("缺少 LLM_MODEL_ID")

        if not api_key:
            raise ValueError("缺少 LLM_API_KEY")

        if not base_url:
            raise ValueError("缺少 LLM_BASE_URL")

        if provider == "auto":
            provider = cls.detect_provider(base_url)

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            capabilities=get_provider_capabilities(provider),
        )

    @staticmethod
    def _parse_timeout(value):
        try:
            timeout = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("LLM_TIMEOUT 必须是正整数") from exc

        if timeout <= 0:
            raise ValueError("LLM_TIMEOUT 必须是正整数")

        return timeout

    @staticmethod
    def detect_provider(base_url):
        normalized_url = base_url.lower()

        provider_keywords = {
            "deepseek": "deepseek",
            "modelscope": "modelscope",
            "openai": "openai",
            "ollama": "ollama",
            "11434": "ollama",
            "vllm": "vllm",
        }

        for keyword, provider in provider_keywords.items():
            if keyword in normalized_url:
                return provider

        return "openai_compatible"

    def to_safe_dict(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "has_api_key": bool(self.api_key),
            "capabilities": dict(self.capabilities),
        }
