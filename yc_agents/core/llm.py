from openai import OpenAI #创建 API 客户端

from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import LLMCallError


class YCAgentsLLM:
    def __init__(self, config=None, client=None):
        self.config = config or ProviderConfig.from_env()
        self.model = self.config.model
        self.api_key = self.config.api_key
        self.base_url = self.config.base_url
        self.provider = self.config.provider

        self.client = client or self._create_client()

    def _create_client(self):
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.config.timeout,
        )


    def _request_kwargs(self, kwargs):
        merged = dict(getattr(self.config, "request_defaults", {}) or {})
        merged.update(kwargs)
        return merged


    def think(self, messages, **kwargs):   
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **self._request_kwargs(kwargs),
            )
        except Exception as exc:
            raise LLMCallError(
                f"模型调用失败 provider={self.provider} model={self.model}: {exc.__class__.__name__}"
            ) from exc

        return response.choices[0].message.content

    def stream_think(self, messages, **kwargs):
        try:
            request_kwargs = self._request_kwargs(kwargs)
            request_kwargs["stream"] = True
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **request_kwargs,
            )
        except Exception as exc:
            raise LLMCallError(
                f"妯″瀷璋冪敤澶辫触 provider={self.provider} model={self.model}: {exc.__class__.__name__}"
            ) from exc

        for chunk in response:
            choices = getattr(chunk, "choices", None) or []

            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)

            if content:
                yield content
    
    
