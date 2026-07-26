import time

from yc_agents.core.exceptions import LLMCallError, TruncatedOutputError


class ModelRouter:
    """按 agents.defaults.model.fallbacks 顺序持有多个已构造的 LLM 实例，
    对上层透明代理 think / think_json 等接口。

    路由语义：
    - 活跃模型抛出 retryable 的 LLMCallError 时，先在同一模型上退避重试
      retries_per_model 次；仍失败才切换到下一个 fallback，并记录一条
      切换事件（consume_switch_events 供运行时写入 trace）。
    - 整条链全部耗尽才抛出最后异常，异常消息带完整调用轨迹；同时把
      活跃指针拨回主模型，让上层的 provider 恢复预算有机会重走整条链。
    - TruncatedOutputError 原样透传：截断应走运行时的提额重试，不是
      模型故障，切换 fallback 解决不了输出上限问题。
    - 非 retryable 错误（含 ToolCallingUnsupportedError）原样透传：由
      运行时既有的 native_fc_fallback 逻辑降级 json-protocol 接管。

    切换成功后保持粘性：后续调用直接走 fallback，不再反复敲打故障的
    主模型。所有链成员共享主模型的 usage_ledger，按各自真实模型记账。
    """

    def __init__(self, llms, *, retries_per_model=1, backoff_seconds=1.0, sleep=None):
        chain = [llm for llm in (llms or []) if llm is not None]
        if not chain:
            raise ValueError(
                "ModelRouter 需要至少一个 LLM 实例（主模型）。"
                "请先构造主模型，再按 fallbacks 顺序追加备选模型。"
            )
        self.llms = chain
        self.retries_per_model = max(0, int(retries_per_model))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self._sleep = sleep or time.sleep
        self.active_index = 0
        self.switch_events = []
        self._pending_switch_events = []

    # ------------------------------------------------------------------
    # 属性透明代理：外部读取 model/config/client 时始终看到当前活跃模型，
    # usage_ledger 固定指向主模型的共享账本。
    # ------------------------------------------------------------------

    @property
    def active_llm(self):
        return self.llms[self.active_index]

    @property
    def model(self):
        return getattr(self.active_llm, "model", None)

    @property
    def provider(self):
        return getattr(self.active_llm, "provider", None)

    @property
    def config(self):
        return getattr(self.active_llm, "config", None)

    @property
    def client(self):
        return getattr(self.active_llm, "client", None)

    @property
    def usage_ledger(self):
        return getattr(self.llms[0], "usage_ledger", None)

    @property
    def last_primary_messages(self):
        return getattr(self.active_llm, "last_primary_messages", [])

    def set_usage_path(self, file_path):
        ledger = self.usage_ledger
        if ledger is not None:
            ledger.set_file_path(file_path)
        return ledger

    def set_call_overrides(self, **overrides):
        """提额等临时覆盖要落在整条链上：切换 fallback 后覆盖仍然生效。"""
        for llm in self.llms:
            set_overrides = getattr(llm, "set_call_overrides", None)
            if callable(set_overrides):
                set_overrides(**overrides)

    def clear_call_overrides(self):
        for llm in self.llms:
            clear_overrides = getattr(llm, "clear_call_overrides", None)
            if callable(clear_overrides):
                clear_overrides()

    def consume_switch_events(self):
        """取走尚未上报的切换事件（运行时写 trace 用）；全量历史仍保留在
        switch_events 供诊断。"""
        drained = list(self._pending_switch_events)
        self._pending_switch_events = []
        return drained

    # ------------------------------------------------------------------
    # 调用代理
    # ------------------------------------------------------------------

    def think(self, messages, **kwargs):
        return self._route("think", messages, **kwargs)

    def think_json(self, messages, **kwargs):
        return self._route("think_json", messages, **kwargs)

    def stream_think(self, messages, **kwargs):
        # 流式响应中途失败无法安全切换模型（内容已经吐给调用方），
        # 因此流式接口只代理到当前活跃模型，不做链路容灾。
        return self.active_llm.stream_think(messages, **kwargs)

    def stream_think_json(self, messages, **kwargs):
        return self.active_llm.stream_think_json(messages, **kwargs)

    def _route(self, method_name, messages, **kwargs):
        trail = []
        last_error = None
        for index in range(self.active_index, len(self.llms)):
            self.active_index = index
            llm = self.llms[index]
            model_name = str(getattr(llm, "model", f"llm[{index}]"))
            attempts = self.retries_per_model + 1
            for attempt in range(1, attempts + 1):
                try:
                    return getattr(llm, method_name)(messages, **kwargs)
                except TruncatedOutputError:
                    raise
                except LLMCallError as exc:
                    if not exc.retryable:
                        raise
                    last_error = exc
                    if attempt < attempts and self.backoff_seconds:
                        self._sleep(self.backoff_seconds * attempt)
            trail.append(
                f"{model_name}: {last_error.cause_type or last_error.__class__.__name__}"
                f" ×{attempts}"
            )
            next_index = index + 1
            if next_index < len(self.llms):
                self._record_switch(llm, self.llms[next_index], last_error, attempts)

        # 整条链全部耗尽：拨回主模型让下一次调用重走整条链，然后抛出
        # 带完整轨迹的教学式异常。
        self.active_index = 0
        raise LLMCallError(
            (
                "模型链路全部耗尽：主模型与全部 fallback 均调用失败"
                f"（调用轨迹：{' → '.join(trail)}）。"
                "请检查各 provider 的网络与配额，"
                "或调整 agents.defaults.model.fallbacks 配置后重试。"
            ),
            retryable=True,
            status_code=getattr(last_error, "status_code", None),
            cause_type=getattr(last_error, "cause_type", None),
        ) from last_error

    def _record_switch(self, from_llm, to_llm, error, attempts):
        event = {
            "from_model": str(getattr(from_llm, "model", "")),
            "to_model": str(getattr(to_llm, "model", "")),
            "attempts": attempts,
            "error_type": getattr(error, "cause_type", None)
            or error.__class__.__name__,
            "error": str(error)[:300],
        }
        self.switch_events.append(event)
        self._pending_switch_events.append(event)
