import json
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import (
    LLMCallError,
    ToolCallingUnsupportedError,
    TruncatedOutputError,
)
from yc_agents.core.usage import TokenUsage, UsageLedger


@dataclass(frozen=True)
class ModelToolCall:
    """原生 function calling 的单个工具调用。arguments 解析成功时是 dict；
    解析失败时保留 provider 原串并在 parse_error 记录原因，绝不悄悄丢弃。"""

    id: str
    name: str
    arguments: object
    raw_arguments: str
    parse_error: str | None = None

    @property
    def arguments_valid(self):
        return self.parse_error is None and isinstance(self.arguments, dict)


@dataclass(frozen=True)
class ModelTurn:
    """一次模型回合的结构化结果：content、结构化 tool_calls 与 finish_reason。
    只有 think 收到 tools 参数时才返回；无 tools 的调用仍返回 str，
    既有调用方零感知。"""

    content: str
    tool_calls: tuple = ()
    finish_reason: str | None = None


class YCAgentsLLM:
    def __init__(self, config=None, client=None, usage_ledger=None):
        self.config = config or ProviderConfig.from_env()
        self.model = self.config.model
        self.api_key = self.config.api_key
        self.base_url = self.config.base_url
        self.provider = self.config.provider
        self.usage_ledger = usage_ledger or UsageLedger()
        self.last_primary_messages = []
        self.call_overrides = {}

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
        return self._apply_call_overrides(merged)

    def set_call_overrides(self, **overrides):
        """Temporary request overrides (e.g. a bigger max_tokens for a truncation
        retry). They beat per-call kwargs and defaults until cleared."""
        self.call_overrides = dict(overrides)

    def clear_call_overrides(self):
        self.call_overrides = {}

    def _apply_call_overrides(self, merged):
        if not self.call_overrides:
            return merged
        overrides = dict(self.call_overrides)
        # 有些 provider 请求默认用 max_completion_tokens 表示输出上限；
        # 提额覆盖要落在同一个键上，避免同时发送两个上限参数被拒绝。
        if (
            "max_tokens" in overrides
            and "max_tokens" not in merged
            and "max_completion_tokens" in merged
        ):
            overrides["max_completion_tokens"] = overrides.pop("max_tokens")
        merged.update(overrides)
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

    def think(self, messages, usage_kind="primary", tools=None, tool_choice=None, **kwargs):
        request_kwargs = self._request_kwargs(kwargs)
        if tools is not None:
            request_kwargs["tools"] = list(tools)
            if tool_choice is not None:
                request_kwargs["tool_choice"] = tool_choice
        try:
            response = self._create_completion(messages, request_kwargs)
        except Exception as exc:
            self._raise_call_error(exc, tools_requested=tools is not None)

        message = response.choices[0].message
        content = message.content
        self._record_response_usage(response, messages, content, usage_kind)
        self._raise_if_truncated(response, content, request_kwargs)
        if tools is None:
            return content
        return self._build_model_turn(response, message)

    def _build_model_turn(self, response, message):
        tool_calls = []
        for index, raw_call in enumerate(getattr(message, "tool_calls", None) or []):
            function = getattr(raw_call, "function", None)
            raw_arguments = str(getattr(function, "arguments", "") or "")
            arguments, parse_error = self._parse_tool_arguments(raw_arguments)
            tool_calls.append(
                ModelToolCall(
                    id=str(getattr(raw_call, "id", "") or f"tool_call_{index}"),
                    name=str(getattr(function, "name", "") or ""),
                    arguments=arguments if parse_error is None else raw_arguments,
                    raw_arguments=raw_arguments,
                    parse_error=parse_error,
                )
            )
        choices = getattr(response, "choices", None) or []
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        return ModelTurn(
            content=str(message.content or ""),
            tool_calls=tuple(tool_calls),
            finish_reason=finish_reason,
        )

    @staticmethod
    def _parse_tool_arguments(raw_arguments):
        text = raw_arguments.strip()
        if not text:
            return {}, None
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            return None, f"arguments 不是合法 JSON：{exc}"
        if not isinstance(parsed, dict):
            return None, (
                f"arguments 必须是 JSON 对象，实际收到 {type(parsed).__name__}"
            )
        return parsed, None

    def think_json(self, messages, usage_kind="primary", **kwargs):
        request_kwargs = self._request_kwargs(kwargs, json_mode=True)
        try:
            response = self._create_completion(messages, request_kwargs)
        except Exception as exc:
            self._raise_call_error(exc)

        content = response.choices[0].message.content
        self._record_response_usage(response, messages, content, usage_kind)
        self._raise_if_truncated(response, content, request_kwargs)
        return content

    def _raise_if_truncated(self, response, content, request_kwargs):
        choices = getattr(response, "choices", None) or []
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        if finish_reason != "length":
            return
        max_tokens = request_kwargs.get("max_tokens") or request_kwargs.get(
            "max_completion_tokens"
        )
        raise TruncatedOutputError(
            (
                "模型输出被截断（finish_reason=length，本次输出上限 "
                f"max_tokens={max_tokens}）。这不是 JSON 协议错误："
                "请提高本次调用的 max_tokens 后重试同一请求，"
                "不要把截断文本送去做协议修复。"
            ),
            partial_text=str(content or ""),
            max_tokens=max_tokens,
        )

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

    def _raise_call_error(self, exc, tools_requested=False):
        status_code = getattr(exc, "status_code", None)
        if (
            tools_requested
            and isinstance(exc, APIStatusError)
            and not isinstance(exc, RateLimitError)
            and isinstance(status_code, int)
            and 400 <= status_code < 500
        ):
            # provider 对带 tools 的请求返回 4xx，最常见原因是模型不支持
            # 原生 function calling：这类错误重试同一请求没有意义。
            raise ToolCallingUnsupportedError(
                (
                    "模型拒绝了带 tools 参数的请求 "
                    f"provider={self.provider} model={self.model}"
                    f"（HTTP {status_code}）。该模型可能不支持原生 function calling："
                    "本轮应降级为 json-protocol 文本协议继续；若持续发生，"
                    "请移除该 model entry 的 toolCalling 标记，"
                    "或把 runtime.toolCalling 设回 'json-protocol'。"
                ),
                status_code=status_code,
            ) from exc
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
    
    
