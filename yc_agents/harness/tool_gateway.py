from concurrent.futures import ThreadPoolExecutor, TimeoutError

from yc_agents.harness.tool_policy import ToolExecutionPolicy, ToolLoopError
from yc_agents.harness.tool_result import ToolExecutionResult
from yc_agents.harness.tool_schema import ToolValidationError


class ToolNotAllowedError(PermissionError):
    pass


class ToolGateway:
    def __init__(
        self,
        tool_registry,
        allowed_tools=None,
        trace=None,
        approval_gate=None,
        approval_callback=None,
        policy=None,
        event_callback=None,
    ):
        self.tool_registry = tool_registry
        self.allowed_tools = set(allowed_tools or [])
        self.trace = trace
        self.approval_gate = approval_gate
        # 挂起式审批回调：gate 判定 needs_approval 时调用，返回 True 放行、
        # False 拒绝。未注入（headless）时一律按拒绝处理。
        self.approval_callback = approval_callback
        self.policy = policy or ToolExecutionPolicy()
        self.event_callback = event_callback

    def run_tool(self, name, *args, **kwargs):
        if name not in self.allowed_tools:
            self._record(
                "tool_denied",
                {
                    "tool_name": name,
                    "reason": "Tool is not allowed for this run",
                },
            )
            raise ToolNotAllowedError(f"Tool is not allowed: {name}")

        tool = self.tool_registry.get_tool(name)
        arguments = self._build_arguments(args, kwargs)

        schema = getattr(tool, "schema", None)
        if schema is not None:
            try:
                kwargs = schema.validate(kwargs)
                arguments = self._build_arguments(args, kwargs)
            except ToolValidationError as exc:
                self._record(
                    "tool_validation_failed",
                    {
                        "tool_name": name,
                        "error": str(exc),
                    },
                )
                failure_result = ToolExecutionResult.failure(
                    name,
                    "validation_error",
                    str(exc),
                ).to_dict()
                self._record_tool_result(name, failure_result)
                return failure_result

        try:
            self.policy.record_call(name, arguments)
        except ToolLoopError as exc:
            self._record(
                "tool_loop_stopped",
                {
                    "tool_name": name,
                    "error": str(exc),
                },
            )
            failure_result = ToolExecutionResult.failure(
                name,
                "loop_stopped",
                str(exc),
            ).to_dict()
            self._record_tool_result(name, failure_result)
            return failure_result

        approval = self._check_approval(name, tool, args, kwargs)

        if approval is not None and approval.get("needs_approval"):
            self._record("tool_needs_approval", approval)
            if not self._resolve_approval(approval):
                # 拒绝不再冒泡为 RunStoppedError：作为普通失败 tool_result
                # 返回，让模型改道或转而询问用户，保住整轮已有进度。
                denial_result = ToolExecutionResult.failure(
                    name,
                    "approval_denied",
                    self._denial_message(approval),
                ).to_dict()
                self._record(
                    "tool_approval_denied",
                    {
                        "tool_name": name,
                        "risk": approval.get("risk"),
                        "reason": approval.get("reason"),
                    },
                )
                self._record_tool_result(name, denial_result)
                return denial_result
            self._record(
                "tool_approved",
                {
                    "tool_name": name,
                    "risk": approval.get("risk"),
                },
            )

        result, attempts, failure = self._run_with_policy(tool, args, kwargs)

        if failure is not None:
            error_type, error_message = failure
            self._record(
                "tool_failed",
                {
                    "tool_name": name,
                    "error_type": error_type,
                    "error": error_message,
                    "attempts": attempts,
                },
            )
            failure_result = ToolExecutionResult.failure(
                name,
                error_type,
                error_message,
                attempts=attempts,
            ).to_dict()
            self._record_tool_result(name, failure_result)
            return failure_result

        self._record(
            "tool_called",
            {
                "tool_name": name,
                "result": result,
            },
        )
        self._record_tool_result(name, result)
        return result

    def _run_with_policy(self, tool, args, kwargs):
        attempts = 0
        max_attempts = self.policy.max_retries + 1

        while attempts < max_attempts:
            attempts += 1
            result, failure = self._run_once(tool, args, kwargs)
            if failure is None:
                return result, attempts, None

            if failure[0] not in {"timeout", "io_error", "execution_error"}:
                return None, attempts, failure

            if attempts >= max_attempts:
                return None, attempts, failure

            self._record(
                "tool_retry",
                {
                    "tool_name": tool.name,
                    "attempt": attempts + 1,
                    "previous_error_type": failure[0],
                    "previous_error": failure[1],
                },
            )

        return None, attempts, ("execution_error", "Tool execution failed")

    def _run_once(self, tool, args, kwargs):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(tool.run, *args, **kwargs)

        try:
            timeout_seconds = float(
                getattr(tool, "timeout_seconds", self.policy.timeout_seconds)
            )
            return future.result(timeout=timeout_seconds), None
        except TimeoutError:
            future.cancel()
            return None, ("timeout", f"Tool timed out after {timeout_seconds}s")
        except PermissionError as exc:
            return None, ("permission_error", str(exc))
        except FileNotFoundError as exc:
            return None, ("not_found", str(exc))
        except ValueError as exc:
            return None, ("invalid_operation", str(exc))
        except OSError as exc:
            return None, ("io_error", str(exc))
        except Exception as exc:
            return None, ("execution_error", str(exc))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _check_approval(self, name, tool, args, kwargs):
        if self.approval_gate is None:
            return None

        arguments = self._build_arguments(args, kwargs)
        risk = str(getattr(tool, "risk", "read") or "read")

        try:
            return self.approval_gate.check_tool_call(name, arguments, risk=risk)
        except TypeError:
            # 旧式 gate 不接受 risk 参数：退回两参数签名保持兼容。
            return self.approval_gate.check_tool_call(name, arguments)

    def _resolve_approval(self, approval):
        if self.approval_callback is None:
            return False
        try:
            return bool(self.approval_callback(approval))
        except Exception:
            # 审批回调崩溃等同于用户没有批准：宁可拒绝也不能默认放行。
            return False

    @staticmethod
    def _denial_message(approval):
        reason = str(approval.get("reason") or "该操作需要人工批准").strip()
        return f"用户拒绝了此操作：{reason}，请改用其他方式或询问用户。"

    def _build_arguments(self, args, kwargs):
        arguments = dict(kwargs)

        if args:
            arguments["_args"] = list(args)

        return arguments

    def _record(self, event_type, payload):
        event = {
            "event_type": event_type,
            "payload": payload or {},
        }
        if self.trace is None:
            if self.event_callback is not None:
                try:
                    self.event_callback(event)
                except Exception:
                    pass
            return

        self.trace.record(event_type, payload)
        if self.event_callback is not None:
            try:
                self.event_callback(event)
            except Exception:
                pass

    def _record_tool_result(self, name, result):
        self._record(
            "tool_result",
            {
                "tool_name": name,
                "result": result,
            },
        )
