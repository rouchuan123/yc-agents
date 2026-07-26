import copy
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from openai import APIStatusError

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.config.ycore import YCoreConfig
from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import LLMCallError, ToolCallingUnsupportedError
from yc_agents.core.llm import ModelToolCall, ModelTurn, YCAgentsLLM
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.memory.session import SessionMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."
    schema = ToolSchema(fields=[ToolField(name="text", type="str", required=True)])

    def __init__(self):
        self.calls = []

    def run(self, text):
        self.calls.append(text)
        return {"echo": text}


class FreeformTool(BaseTool):
    name = "freeform_tool"
    description = "Tool without a schema."

    def run(self, **kwargs):
        return {"ok": True}


def _fake_tool_call(call_id, name, arguments):
    function = type("Function", (), {"name": name, "arguments": arguments})()
    return type(
        "ToolCall",
        (),
        {"id": call_id, "type": "function", "function": function},
    )()


def _fake_response(content=None, tool_calls=None, finish_reason="stop"):
    message = type(
        "Message",
        (),
        {"content": content, "tool_calls": tool_calls},
    )()
    choice = type(
        "Choice",
        (),
        {"message": message, "finish_reason": finish_reason},
    )()
    return type("Response", (), {"choices": [choice]})()


class NativeCompletions:
    def __init__(self, responses):
        self.calls = []
        self.responses = list(responses)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class NativeClient:
    def __init__(self, responses):
        self.chat = type("Chat", (), {})()
        self.chat.completions = NativeCompletions(responses)


def _provider_config():
    return ProviderConfig(
        provider="deepseek",
        model="deepseek-v4-flash",
        api_key="secret-key",
        base_url="https://api.deepseek.com",
        timeout=30,
        request_defaults={"max_tokens": 4096},
    )


OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fake_tool",
            "description": "Fake tool.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "additionalProperties": False,
                "required": ["text"],
            },
        },
    }
]


def serialize(messages):
    return json.dumps(messages, ensure_ascii=False, default=str)


def _selection(skill=None):
    return json.dumps(
        {
            "type": "skill_selection",
            "selected_skill": skill,
            "confidence": 0.9 if skill else 0.1,
            "reason": "test",
        }
    )


def _final(content="done"):
    return json.dumps({"type": "final_answer", "content": content})


def _turn(content="", calls=()):
    return ModelTurn(
        content=content,
        tool_calls=tuple(calls),
        finish_reason="tool_calls" if calls else "stop",
    )


def _call(call_id, text):
    arguments = {"text": text}
    return ModelToolCall(
        id=call_id,
        name="fake_tool",
        arguments=arguments,
        raw_arguments=json.dumps(arguments, ensure_ascii=False),
    )


def _bad_call(call_id, raw='{"text": "broken'):
    return ModelToolCall(
        id=call_id,
        name="fake_tool",
        arguments=raw,
        raw_arguments=raw,
        parse_error="arguments 不是合法 JSON：Expecting value",
    )


class NativeRecordingLLM:
    """Fake LLM：think 返回预置 ModelTurn，think_json 返回预置 JSON 文本。"""

    def __init__(self, turns=(), json_responses=()):
        self.turns = list(turns)
        self.json_responses = list(json_responses)
        self.think_calls = []
        self.think_json_calls = []

    def think(self, messages, usage_kind="primary", tools=None, tool_choice=None, **kwargs):
        self.think_calls.append(
            {
                "messages": copy.deepcopy(messages),
                "tools": copy.deepcopy(tools),
            }
        )
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn

    def think_json(self, messages, **kwargs):
        self.think_json_calls.append(copy.deepcopy(messages))
        return self.json_responses.pop(0)


class ToolsRejectingLLM(NativeRecordingLLM):
    """带 tools 参数的 think 一律拒绝，模拟不支持原生 FC 的 provider。"""

    def think(self, messages, usage_kind="primary", tools=None, tool_choice=None, **kwargs):
        if tools:
            self.think_calls.append(
                {
                    "messages": copy.deepcopy(messages),
                    "tools": copy.deepcopy(tools),
                }
            )
            raise ToolCallingUnsupportedError(
                "模型拒绝了带 tools 参数的请求（HTTP 400）。",
                status_code=400,
            )
        return super().think(
            messages,
            usage_kind=usage_kind,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )


def _build_native_runtime(tmp_dir, llm):
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)
    agent = SkillRuntimeAgent(
        llm,
        skills_dir=Path(tmp_dir) / "skills",
        session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
        context_limit=100_000,
        tool_calling="native",
        native_tools=registry.to_openai_schema(),
    )
    runtime = YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=registry,
        allowed_tools=["fake_tool"],
        output_root=Path(tmp_dir) / "runs",
        tool_calling="native",
    )
    return agent, tool, runtime


class TestOpenAIToolSchemaExport(unittest.TestCase):
    def test_tool_schema_to_openai_schema_maps_types_and_required(self):
        schema = ToolSchema(
            fields=[
                ToolField(name="path", type="str", required=True),
                ToolField(name="limit", type="int", required=False, default=10),
                ToolField(name="overwrite", type="bool", required=False, default=False),
                ToolField(name="ratio", type="float", required=False),
                ToolField(name="options", type="dict", required=False),
                ToolField(name="names", type="list", required=False),
            ]
        )

        parameters = schema.to_openai_schema()

        self.assertEqual(parameters["type"], "object")
        self.assertEqual(parameters["required"], ["path"])
        self.assertFalse(parameters["additionalProperties"])
        properties = parameters["properties"]
        self.assertEqual(properties["path"], {"type": "string"})
        self.assertEqual(properties["limit"], {"type": "integer", "default": 10})
        self.assertEqual(properties["overwrite"], {"type": "boolean", "default": False})
        self.assertEqual(properties["ratio"], {"type": "number"})
        self.assertEqual(properties["options"], {"type": "object"})
        self.assertEqual(properties["names"], {"type": "array"})

    def test_registry_to_openai_schema_builds_function_entries(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(FreeformTool())

        tools = registry.to_openai_schema()

        by_name = {item["function"]["name"]: item for item in tools}
        self.assertEqual(set(by_name), {"fake_tool", "freeform_tool"})
        self.assertTrue(all(item["type"] == "function" for item in tools))
        echo = by_name["fake_tool"]["function"]
        self.assertEqual(echo["description"], "Fake tool.")
        self.assertEqual(echo["parameters"]["properties"]["text"], {"type": "string"})
        self.assertEqual(echo["parameters"]["required"], ["text"])
        freeform = by_name["freeform_tool"]["function"]
        self.assertEqual(freeform["parameters"], {"type": "object", "properties": {}})


class TestThinkNativeToolPassthrough(unittest.TestCase):
    def test_think_without_tools_still_returns_plain_string(self):
        client = NativeClient([_fake_response(content="ok")])
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        result = llm.think([{"role": "user", "content": "hi"}])

        self.assertIsInstance(result, str)
        self.assertEqual(result, "ok")
        self.assertNotIn("tools", client.chat.completions.calls[0])

    def test_think_passes_tools_and_returns_model_turn(self):
        client = NativeClient(
            [
                _fake_response(
                    content="我先查看文件。",
                    tool_calls=[
                        _fake_tool_call("call-1", "fake_tool", '{"text": "s1"}')
                    ],
                    finish_reason="tool_calls",
                )
            ]
        )
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        turn = llm.think(
            [{"role": "user", "content": "hi"}],
            tools=OPENAI_TOOLS,
            tool_choice="auto",
        )

        request = client.chat.completions.calls[0]
        self.assertEqual(request["tools"], OPENAI_TOOLS)
        self.assertEqual(request["tool_choice"], "auto")
        self.assertIsInstance(turn, ModelTurn)
        self.assertEqual(turn.content, "我先查看文件。")
        self.assertEqual(turn.finish_reason, "tool_calls")
        self.assertEqual(len(turn.tool_calls), 1)
        tool_call = turn.tool_calls[0]
        self.assertEqual(tool_call.id, "call-1")
        self.assertEqual(tool_call.name, "fake_tool")
        self.assertEqual(tool_call.arguments, {"text": "s1"})
        self.assertEqual(tool_call.raw_arguments, '{"text": "s1"}')
        self.assertIsNone(tool_call.parse_error)
        self.assertTrue(tool_call.arguments_valid)

    def test_think_with_tools_and_no_calls_returns_content_only_turn(self):
        client = NativeClient([_fake_response(content="最终答案。")])
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        turn = llm.think([{"role": "user", "content": "hi"}], tools=OPENAI_TOOLS)

        self.assertIsInstance(turn, ModelTurn)
        self.assertEqual(turn.content, "最终答案。")
        self.assertEqual(turn.tool_calls, ())
        self.assertEqual(turn.finish_reason, "stop")

    def test_bad_arguments_keep_raw_string_and_mark_parse_error(self):
        raw = '{"text": "s1"'
        client = NativeClient(
            [
                _fake_response(
                    tool_calls=[_fake_tool_call("call-1", "fake_tool", raw)],
                    finish_reason="tool_calls",
                )
            ]
        )
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        turn = llm.think([{"role": "user", "content": "hi"}], tools=OPENAI_TOOLS)

        tool_call = turn.tool_calls[0]
        self.assertEqual(tool_call.arguments, raw)
        self.assertEqual(tool_call.raw_arguments, raw)
        self.assertTrue(tool_call.parse_error)
        self.assertFalse(tool_call.arguments_valid)

    def test_non_object_arguments_are_marked_invalid(self):
        client = NativeClient(
            [
                _fake_response(
                    tool_calls=[_fake_tool_call("call-1", "fake_tool", '["not", "dict"]')],
                    finish_reason="tool_calls",
                )
            ]
        )
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        turn = llm.think([{"role": "user", "content": "hi"}], tools=OPENAI_TOOLS)

        tool_call = turn.tool_calls[0]
        self.assertFalse(tool_call.arguments_valid)
        self.assertIn("JSON 对象", tool_call.parse_error)

    def test_provider_4xx_with_tools_raises_tool_calling_unsupported(self):
        request = httpx.Request(
            "POST", "https://api.deepseek.com/chat/completions"
        )
        error = APIStatusError(
            "tools is not supported",
            response=httpx.Response(400, request=request),
            body=None,
        )
        client = NativeClient([error])
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        with self.assertRaises(ToolCallingUnsupportedError) as context:
            llm.think([{"role": "user", "content": "hi"}], tools=OPENAI_TOOLS)

        self.assertFalse(context.exception.retryable)
        self.assertEqual(context.exception.cause_type, "ToolCallingUnsupported")
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("json-protocol", str(context.exception))

    def test_provider_4xx_without_tools_stays_generic_llm_call_error(self):
        request = httpx.Request(
            "POST", "https://api.deepseek.com/chat/completions"
        )
        error = APIStatusError(
            "bad request",
            response=httpx.Response(400, request=request),
            body=None,
        )
        client = NativeClient([error])
        llm = YCAgentsLLM(config=_provider_config(), client=client)

        with self.assertRaises(LLMCallError) as context:
            llm.think([{"role": "user", "content": "hi"}])

        self.assertNotIsInstance(context.exception, ToolCallingUnsupportedError)


class TestNativeToolLoop(unittest.TestCase):
    def test_native_loop_executes_tool_and_returns_plain_content(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = NativeRecordingLLM(
                turns=[
                    _turn(content="我先查看文件。", calls=[_call("call-1", "s1")]),
                    _turn(content="全部完成。"),
                ],
                json_responses=[_selection(None)],
            )
            agent, tool, runtime = _build_native_runtime(tmp_dir, llm)

            response = runtime.run("do the task")

            self.assertEqual(response, "全部完成。")
            self.assertEqual(tool.calls, ["s1"])
            # tools 数组透传给 think
            self.assertEqual(
                llm.think_calls[0]["tools"][0]["function"]["name"],
                "fake_tool",
            )
            # 第二次调用严格扩展前缀：追加 assistant(tool_calls) + role:'tool'
            first = llm.think_calls[0]["messages"]
            second = llm.think_calls[1]["messages"]
            self.assertEqual(serialize(first), serialize(second[: len(first)]))
            appended = second[len(first):]
            self.assertEqual(
                [message["role"] for message in appended],
                ["assistant", "tool"],
            )
            self.assertEqual(appended[0]["content"], "我先查看文件。")
            self.assertEqual(
                appended[0]["tool_calls"],
                [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "fake_tool",
                            "arguments": '{"text": "s1"}',
                        },
                    }
                ],
            )
            self.assertEqual(appended[1]["tool_call_id"], "call-1")
            self.assertEqual(json.loads(appended[1]["content"]), {"echo": "s1"})
            # 精简协议：系统提示不再教 JSON 工具调用格式
            system_text = first[0]["content"]
            self.assertNotIn('{"type":"tool_call"', system_text)
            self.assertNotIn("Runtime JSON protocol", system_text)
            # 全程没有 JSON 协议抽取/修复
            event_types = [
                event["event_type"] for event in runtime.last_trace_events
            ]
            self.assertNotIn("invalid_model_json", event_types)
            self.assertIn("tool_call_requested", event_types)
            # 步进记录照常落盘，供断点续跑
            run_dir = next((Path(tmp_dir) / "runs").iterdir())
            steps = [
                json.loads(line)
                for line in (run_dir / "state-steps.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["tool_call"]["tool_name"], "fake_tool")
            self.assertEqual(steps[0]["tool_result"], {"echo": "s1"})

    def test_native_loop_handles_multiple_tool_calls_in_one_turn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = NativeRecordingLLM(
                turns=[
                    _turn(calls=[_call("c1", "a"), _call("c2", "b")]),
                    _turn(content="双工具完成。"),
                ],
                json_responses=[_selection(None)],
            )
            agent, tool, runtime = _build_native_runtime(tmp_dir, llm)

            response = runtime.run("do the task")

            self.assertEqual(response, "双工具完成。")
            self.assertEqual(tool.calls, ["a", "b"])
            second = llm.think_calls[1]["messages"]
            first = llm.think_calls[0]["messages"]
            appended = second[len(first):]
            self.assertEqual(
                [message["role"] for message in appended],
                ["assistant", "tool", "tool"],
            )
            self.assertEqual(
                [message["tool_call_id"] for message in appended[1:]],
                ["c1", "c2"],
            )

    def test_native_bad_arguments_feed_back_as_tool_result(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = NativeRecordingLLM(
                turns=[
                    _turn(calls=[_bad_call("call-1")]),
                    _turn(calls=[_call("call-2", "good")]),
                    _turn(content="修复后完成。"),
                ],
                json_responses=[_selection(None)],
            )
            agent, tool, runtime = _build_native_runtime(tmp_dir, llm)

            response = runtime.run("do the task")

            self.assertEqual(response, "修复后完成。")
            # 坏参数不会真正执行工具，只有修正后的那次会
            self.assertEqual(tool.calls, ["good"])
            # 错误作为 role:'tool' 结果反馈给模型
            second = llm.think_calls[1]["messages"]
            tool_message = second[-1]
            self.assertEqual(tool_message["role"], "tool")
            payload = json.loads(tool_message["content"])
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_type"], "invalid_tool_arguments")
            # 走 tool_feedback 恢复，而不是 JSON 协议修复
            event_types = [
                event["event_type"] for event in runtime.last_trace_events
            ]
            self.assertNotIn("invalid_model_json", event_types)
            recovery_attempts = [
                event["payload"]
                for event in runtime.last_trace_events
                if event["event_type"] == "recovery_attempt"
            ]
            self.assertTrue(recovery_attempts)
            self.assertEqual(recovery_attempts[0]["kind"], "tool_feedback")
            self.assertEqual(
                recovery_attempts[0]["error_type"], "invalid_tool_arguments"
            )

    def test_native_falls_back_to_json_protocol_when_provider_rejects_tools(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = ToolsRejectingLLM(
                json_responses=[
                    _selection(None),
                    _selection(None),
                    _final("degraded done"),
                ],
            )
            agent, tool, runtime = _build_native_runtime(tmp_dir, llm)

            response = runtime.run("do the task")

            self.assertEqual(response, "degraded done")
            event_types = [
                event["event_type"] for event in runtime.last_trace_events
            ]
            self.assertIn("native_fc_fallback", event_types)
            # 降级只影响本轮：轮结束后重新尝试原生 FC
            self.assertTrue(agent.native_turn_active())


class TestNativeToolCallingConfig(unittest.TestCase):
    def _write_config(self, root, tool_calling_flag):
        model_entry = {"id": "deepseek-v4-flash"}
        if tool_calling_flag:
            model_entry["toolCalling"] = True
        config = {
            "agents": {
                "defaults": {"model": {"primary": "deepseek/deepseek-v4-flash"}}
            },
            "models": {
                "providers": {
                    "deepseek": {
                        "baseUrl": "https://api.deepseek.com",
                        "api": "openai-completions",
                        "apiKeyEnv": "DEEPSEEK_API_KEY",
                        "models": [model_entry],
                    }
                }
            },
            "runtime": {"modelTimeoutSeconds": 60},
        }
        path = root / "global-ycore.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_resolve_model_provider_exposes_tool_calling_flag(self):
        import os
        from unittest.mock import patch

        for flag, expected in [(True, True), (False, False)]:
            with self.subTest(flag=flag):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    config_path = self._write_config(root, flag)
                    with patch.dict(
                        os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False
                    ):
                        settings = YCoreConfig.load(
                            root, global_path=config_path
                        ).resolve_model_provider()

                    self.assertEqual(settings.tool_calling, expected)

    def test_repo_ycore_json_enables_native_fc_for_deepseek_only(self):
        data = json.loads(Path("ycore.json").read_text(encoding="utf-8"))

        self.assertEqual(data["runtime"]["toolCalling"], "native")
        deepseek_model = data["models"]["providers"]["deepseek"]["models"][0]
        self.assertTrue(deepseek_model.get("toolCalling"))
        mimo_model = data["models"]["providers"]["xiaomi"]["models"][0]
        self.assertFalse(mimo_model.get("toolCalling", False))


class TestPromptBuilderNativeSections(unittest.TestCase):
    def test_native_plain_answer_prompt_drops_json_tool_teaching(self):
        builder = PromptBuilder()

        native = builder.plain_answer_messages("hi", {}, {}, native_tools=True)
        legacy = builder.plain_answer_messages("hi", {}, {})

        native_text = native[0]["content"]
        legacy_text = legacy[0]["content"]
        # json-protocol 模式文本保持不变
        self.assertIn("Runtime JSON protocol:", legacy_text)
        self.assertIn('{"type":"tool_call"', legacy_text)
        # native 模式不再教 JSON 工具调用格式
        self.assertNotIn("Runtime JSON protocol:", native_text)
        self.assertNotIn('tool_call example: {"type":"tool_call"', native_text)
        self.assertIn("plain text", native_text)
        # 行为约束仍然保留
        self.assertIn("workspace.available_tools", native_text)
        self.assertIn("Never repeat a successful tool call", native_text)

    def test_native_skill_execution_prompt_keeps_workflow_rules(self):
        builder = PromptBuilder()

        native = builder.skill_execution_messages(
            {"user_input": "review"}, native_tools=True
        )
        legacy = builder.skill_execution_messages({"user_input": "review"})

        native_text = native[0]["content"]
        legacy_text = legacy[0]["content"]
        self.assertIn("Skill execution protocol:", native_text)
        self.assertNotIn("Runtime JSON protocol:", native_text)
        self.assertIn("Runtime JSON protocol:", legacy_text)

    def test_native_retry_prompt_avoids_json_tool_teaching(self):
        builder = PromptBuilder()

        native = builder.retry_skill_execution_messages(
            "hi", {"user_input": "hi"}, native_tools=True
        )

        native_text = native[0]["content"]
        self.assertIn("Skill retry protocol:", native_text)
        self.assertNotIn("Runtime JSON protocol:", native_text)


if __name__ == "__main__":
    unittest.main()
