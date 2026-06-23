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
        policy=None,
    ):
        self.tool_registry = tool_registry
        self.allowed_tools = set(allowed_tools or [])
        self.trace = trace
        self.approval_gate = approval_gate
        self.policy = policy or ToolExecutionPolicy()

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
                return ToolExecutionResult.failure(
                    name,
                    "validation_error",
                    str(exc),
                ).to_dict()

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
            return ToolExecutionResult.failure(
                name,
                "loop_stopped",
                str(exc),
            ).to_dict()

        approval = self._check_approval(name, args, kwargs)

        if approval is not None and approval.get("needs_approval"):
            self._record("tool_needs_approval", approval)
            return approval

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
            return ToolExecutionResult.failure(
                name,
                error_type,
                error_message,
                attempts=attempts,
            ).to_dict()

        self._record(
            "tool_called",
            {
                "tool_name": name,
                "result": result,
            },
        )
        return result

    def _run_with_policy(self, tool, args, kwargs):
        attempts = 0
        max_attempts = self.policy.max_retries + 1

        while attempts < max_attempts:
            attempts += 1
            result, failure = self._run_once(tool, args, kwargs)
            if failure is None:
                return result, attempts, None

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
            return future.result(timeout=self.policy.timeout_seconds), None
        except TimeoutError:
            future.cancel()
            return None, ("timeout", f"Tool timed out after {self.policy.timeout_seconds}s")
        except Exception as exc:
            return None, ("execution_error", str(exc))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _check_approval(self, name, args, kwargs):
        if self.approval_gate is None:
            return None

        arguments = self._build_arguments(args, kwargs)

        return self.approval_gate.check_tool_call(name, arguments)

    def _build_arguments(self, args, kwargs):
        arguments = dict(kwargs)

        if args:
            arguments["_args"] = list(args)

        return arguments

    def _record(self, event_type, payload):
        if self.trace is None:
            return

        self.trace.record(event_type, payload)
