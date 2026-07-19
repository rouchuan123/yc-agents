from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import LLMCallError
from yc_agents.core.usage import TokenUsage, UsageLedger


class YCAgentsLLM:
    def __init__(self, config=None, client=None, usage_ledger=None):
        self.config = config or ProviderConfig.from_env()
        self.model = self.config.model
        self.api_key = self.config.api_key
        self.base_url = self.config.base_url
        self.provider = self.config.provider
        self.usage_ledger = usage_ledger or UsageLedger()
        self.last_primary_messages = []

        self.client = client or self._create_client()

    def _create_client(self):
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.config.timeout,
        )


    def _request_kwargs(self, kwargs, json_mode=False):
        merged = dict(getattr(self.config, "request_defaults", {}) or {})
        if json_mode:
            merged.update(getattr(self.config, "json_request_defaults", {}) or {})
        merged.update(kwargs)
        return merged

    def _create_completion(self, messages, request_kwargs):
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **request_kwargs,
        )


    def set_usage_path(self, file_path):
        self.usage_ledger.set_file_path(file_path)
        return self.usage_ledger

    def think(self, messages, usage_kind="primary", **kwargs):
        try:
            response = self._create_completion(
                messages,
                self._request_kwargs(kwargs),
            )
        except Exception as exc:
            self._raise_call_error(exc)

        content = response.choices[0].message.content
        self._record_response_usage(response, messages, content, usage_kind)
        return content

    def think_json(self, messages, usage_kind="primary", **kwargs):
        try:
            response = self._create_completion(
                messages,
                self._request_kwargs(kwargs, json_mode=True),
            )
        except Exception as exc:
            self._raise_call_error(exc)

        content = response.choices[0].message.content
        self._record_response_usage(response, messages, content, usage_kind)
        return content

    def stream_think(self, messages, usage_kind="primary", **kwargs):
        try:
            request_kwargs = self._request_kwargs(kwargs)
            request_kwargs["stream"] = True
            request_kwargs.setdefault("stream_options", {"include_usage": True})
            response = self._create_stream_with_usage_fallback(messages, request_kwargs)
        except Exception as exc:
            self._raise_call_error(exc)

        yield from self._stream_content(response, messages, usage_kind)

    def stream_think_json(self, messages, usage_kind="primary", **kwargs):
        try:
            request_kwargs = self._request_kwargs(kwargs, json_mode=True)
            request_kwargs["stream"] = True
            request_kwargs.setdefault("stream_options", {"include_usage": True})
            response = self._create_stream_with_usage_fallback(messages, request_kwargs)
        except Exception as exc:
            self._raise_call_error(exc)

        yield from self._stream_content(response, messages, usage_kind)

    def _create_stream_with_usage_fallback(self, messages, request_kwargs):
        try:
            return self._create_completion(messages, request_kwargs)
        except APIStatusError as exc:
            message = f"{exc} {getattr(exc, 'body', '')}".lower()
            status_code = getattr(exc, "status_code", None)
            unsupported = status_code in {400, 422} and (
                "stream_options" in message or "include_usage" in message
            )
            if not unsupported:
                raise
            fallback = dict(request_kwargs)
            fallback.pop("stream_options", None)
            return self._create_completion(messages, fallback)

    def _stream_content(self, response, messages, usage_kind):
        output = []
        provider_usage = None
        for chunk in response:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                provider_usage = chunk_usage
            choices = getattr(chunk, "choices", None) or []

            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)

            if content:
                output.append(content)
                yield content

        self._record_usage(provider_usage, messages, "".join(output), usage_kind)

    def _record_response_usage(self, response, messages, content, usage_kind):
        self._record_usage(getattr(response, "usage", None), messages, content, usage_kind)

    def _record_usage(self, provider_usage, messages, content, usage_kind):
        usage = TokenUsage.from_provider(provider_usage)
        source = "provider"
        if usage is None:
            usage = TokenUsage.estimated(messages, content)
            source = "estimated"
        if usage_kind != "auxiliary":
            self.last_primary_messages = list(messages or [])
        self.usage_ledger.record(
            usage,
            model=self.model,
            call_kind=usage_kind,
            source=source,
        )

    def _raise_call_error(self, exc):
        status_code = getattr(exc, "status_code", None)
        retryable = isinstance(
            exc,
            (APIConnectionError, APITimeoutError, RateLimitError),
        ) or (
            isinstance(exc, APIStatusError)
            and isinstance(status_code, int)
            and status_code >= 500
        )
        raise LLMCallError(
            (
                "模型调用失败 "
                f"provider={self.provider} model={self.model}: "
                f"{exc.__class__.__name__}"
            ),
            retryable=retryable,
            status_code=status_code,
            cause_type=exc.__class__.__name__,
        ) from exc
    
    
