import copy
import json
import unittest
import tempfile
from pathlib import Path

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.core.exceptions import LLMCallError
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.state import StateStore
from yc_agents.memory.session import SessionMemory
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry


MEMORY_MARKER = "UNIQUE-MEMORY-SNAPSHOT-MARKER-4127"
SKILL_BODY_LINE = "Summarize the project structure, architecture, risks, and test gaps."


class RecordingLLM:
    """Fake LLM，逐次深拷贝外发消息列表，用于逐字节前缀断言。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.sent_responses = []

    def think_json(self, messages, **kwargs):
        self.calls.append(copy.deepcopy(messages))
        response = self.responses.pop(0)
        self.sent_responses.append(response)
        return response

    def think(self, messages, **kwargs):
        return self.think_json(messages, **kwargs)


class EchoTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."

    def run(self, text):
        return {"echo": text}


def _selection(skill=None):
    return json.dumps(
        {
            "type": "skill_selection",
            "selected_skill": skill,
            "confidence": 0.9 if skill else 0.1,
            "reason": "test",
        }
    )


def _tool_call(text):
    return json.dumps(
        {
            "type": "tool_call",
            "tool_name": "fake_tool",
            "arguments": {"text": text},
            "reason": "test",
        }
    )


def _final(content="done"):
    return json.dumps({"type": "final_answer", "content": content})


def _observation(text, tool_result):
    return {
        "tool_call": {
            "type": "tool_call",
            "tool_name": "fake_tool",
            "arguments": {"text": text},
            "reason": "test",
        },
        "tool_result": tool_result,
    }


def write_skill(skills_dir, name="code-review"):
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                "description: Use when the user wants a project code review.",
                "allowed_tools:",
                "  - fake_tool",
                "---",
                "",
                "# Code Review Skill",
                "",
                SKILL_BODY_LINE,
            ]
        ),
        encoding="utf-8",
    )


def seeded_session_memory(path):
    seeded = SessionMemory(file_path=path)
    seeded.add_message("user", MEMORY_MARKER)
    seeded.save()
    return SessionMemory(file_path=path)


def serialize(messages):
    return json.dumps(messages, ensure_ascii=False)


class TurnMessageTestCase(unittest.TestCase):
    def assert_strict_prefix_extension(self, earlier, later):
        self.assertGreater(len(later), len(earlier))
        self.assertEqual(serialize(earlier), serialize(later[: len(earlier)]))


class TestTurnMessagePrefixStability(TurnMessageTestCase):
    def test_each_tool_step_extends_previous_messages_as_strict_prefix(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = RecordingLLM(
                [
                    _selection(None),
                    _tool_call("s1"),
                    _tool_call("s2"),
                    _tool_call("s3"),
                    _final(),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
                context_limit=100_000,
            )
            registry = ToolRegistry()
            registry.register(EchoTool())
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["fake_tool"],
                output_root=Path(tmp_dir) / "runs",
            )

            response = runtime.run("do the task")

            self.assertEqual(response, "done")
            # calls[0] 是技能选择；calls[1..4] 是同一轮的追加式消息列表。
            turn_calls = llm.calls[1:]
            self.assertEqual(len(turn_calls), 4)
            self.assertEqual(
                [message["role"] for message in turn_calls[0]],
                ["system", "user"],
            )
            for earlier, later in zip(turn_calls, turn_calls[1:]):
                self.assert_strict_prefix_extension(earlier, later)
                appended = later[len(earlier):]
                self.assertEqual(
                    [message["role"] for message in appended],
                    ["assistant", "user"],
                )
                # assistant 消息还原模型上一步的原始输出。
                self.assertEqual(appended[0]["content"], earlier_response(llm, earlier))
                delta = json.loads(appended[1]["content"])
                self.assertEqual(set(delta), {"observation"})
                self.assertIn("tool_call", delta["observation"])
                self.assertIn("tool_result", delta["observation"])
                self.assertNotIn("execution_history", delta["observation"])


def earlier_response(llm, earlier_messages):
    """定位 earlier_messages 那次调用返回的原始输出。"""
    for index, call in enumerate(llm.calls):
        if serialize(call) == serialize(earlier_messages):
            return llm.sent_responses[index]
    raise AssertionError("earlier call not found")


class TestSingleInjectionPerTurn(TurnMessageTestCase):
    def test_memory_snapshot_and_skill_body_appear_once_in_whole_turn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            write_skill(skills_dir)
            llm = RecordingLLM(
                [
                    _selection("code-review"),
                    _tool_call("s1"),
                    _tool_call("s2"),
                    _final(),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=seeded_session_memory(root / "session.json"),
                context_limit=100_000,
            )
            registry = ToolRegistry()
            registry.register(EchoTool())
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["fake_tool"],
                output_root=root / "runs",
            )

            runtime.run("review this project")

            final_turn_messages = llm.calls[-1]
            joined = serialize(final_turn_messages)
            self.assertEqual(joined.count(MEMORY_MARKER), 1)
            self.assertEqual(joined.count(SKILL_BODY_LINE), 1)


class TestTurnMessageFolding(TurnMessageTestCase):
    def test_fold_replaces_old_exchanges_with_single_summary_then_stays_stable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = RecordingLLM(
                [
                    _selection(None),
                    _tool_call("s1"),
                    _tool_call("s2"),
                    _tool_call("s3"),
                    _tool_call("s4"),
                    _final(),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
                context_limit=20_000,
            )
            big_one = "x" * 20_000
            big_two = "y" * 20_000

            agent.run("do the task")
            agent.run_with_observation(
                "do the task", _observation("s1", {"ok": True, "text": big_one})
            )
            agent.run_with_observation(
                "do the task", _observation("s2", {"ok": True, "text": big_two})
            )
            agent.run_with_observation(
                "do the task", _observation("s3", {"echo": "tiny"})
            )
            agent.run_with_observation(
                "do the task", _observation("s4", {"echo": "tiny"})
            )

            # calls: 0 选择，1 轮首，2 obs1，3 obs2（触发折叠），4 obs3，5 obs4。
            before_fold = llm.calls[2]
            after_fold = llm.calls[3]
            self.assertEqual(len(before_fold), 4)
            self.assertEqual(len(after_fold), 5)
            self.assertIn(big_one, serialize(before_fold))
            # 折叠后：最老的交换对被单条 summary 消息替换，原始大结果消失。
            self.assertNotIn(big_one, serialize(after_fold))
            summary_message = after_fold[2]
            self.assertEqual(summary_message["role"], "user")
            summary_payload = json.loads(summary_message["content"])
            self.assertIn("folded_history_summary", summary_payload)
            entries = summary_payload["folded_history_summary"]["entries"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["tool_name"], "fake_tool")
            # 紧凑条目只保留调用身份与结果摘要，不携带原始结果体。
            self.assertEqual(
                set(entries[0]), {"tool_name", "arguments", "ok", "summary"}
            )
            # 折叠后的新前缀继续稳定：后续步骤只做尾部追加。
            self.assert_strict_prefix_extension(after_fold, llm.calls[4])
            self.assert_strict_prefix_extension(llm.calls[4], llm.calls[5])


class TestResumeRebuildsTurnMessages(TurnMessageTestCase):
    def _stopped_state_with_steps(self, tmp_path):
        state_path = Path(tmp_path) / "state.json"
        store = StateStore(state_path)
        store.save_checkpoint(
            "run_started", "running", {"user_input": "write the report"}
        )
        store.append_step(
            {
                "index": 0,
                "tool_call": {
                    "tool_name": "fake_tool",
                    "arguments": {"text": "list files"},
                    "reason": "inspect",
                },
                "tool_result": {"echo": "list files"},
                "artifacts": [],
            }
        )
        store.append_step(
            {
                "index": 1,
                "tool_call": {
                    "tool_name": "fake_tool",
                    "arguments": {"text": "read outline"},
                    "reason": "continue",
                },
                "tool_result": {"echo": "read outline"},
                "artifacts": [],
            }
        )
        store.save_checkpoint("run_finished", "failed", {"error": "provider flapping"})
        return state_path

    def test_resume_rebuilds_messages_then_appends_without_reinjecting_context(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state_path = self._stopped_state_with_steps(root)
            llm = RecordingLLM([_tool_call("next step"), _final("resumed done")])
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=root / "skills",
                session_memory=seeded_session_memory(root / "session.json"),
                context_limit=100_000,
            )
            registry = ToolRegistry()
            registry.register(EchoTool())
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["fake_tool"],
                output_root=root / "resumed-runs",
            )

            response = runtime.resume_from_state(state_path)

            self.assertEqual(response, "resumed done")
            # 重建后的首次调用：稳定前缀 + 两个已完成步骤的交换对。
            first_call = llm.calls[0]
            self.assertEqual(
                [message["role"] for message in first_call],
                ["system", "user", "assistant", "user", "assistant", "user"],
            )
            first_delta = json.loads(first_call[3]["content"])
            self.assertEqual(
                first_delta["observation"]["tool_result"], {"echo": "list files"}
            )
            self.assertNotIn("execution_history", first_delta["observation"])
            second_delta = json.loads(first_call[5]["content"])
            self.assertEqual(
                second_delta["observation"]["tool_result"], {"echo": "read outline"}
            )
            # 继续追加：新工具步严格扩展重建后的前缀。
            self.assert_strict_prefix_extension(first_call, llm.calls[1])
            appended = llm.calls[1][len(first_call):]
            self.assertEqual(
                [message["role"] for message in appended], ["assistant", "user"]
            )
            appended_delta = json.loads(appended[1]["content"])
            self.assertEqual(
                appended_delta["observation"]["tool_result"], {"echo": "next step"}
            )
            # 记忆快照只注入一次，技能正文不重复注入。
            joined = serialize(llm.calls[1])
            self.assertEqual(joined.count(MEMORY_MARKER), 1)
            self.assertNotIn(SKILL_BODY_LINE, joined)


class FlakyRecordingLLM(RecordingLLM):
    """指定调用序号抛出可重试 provider 错误，其余照常返回。"""

    def __init__(self, responses, fail_on_call_indexes):
        super().__init__(responses)
        self.fail_on = set(fail_on_call_indexes)

    def think_json(self, messages, **kwargs):
        index = len(self.calls)
        self.calls.append(copy.deepcopy(messages))
        if index in self.fail_on:
            raise LLMCallError(
                "temporary provider failure",
                retryable=True,
                status_code=503,
                cause_type="ServiceUnavailable",
            )
        response = self.responses.pop(0)
        self.sent_responses.append(response)
        return response


class TestObservationRetryDoesNotDuplicateSteps(TurnMessageTestCase):
    def test_provider_retry_resends_same_messages_without_duplicate_pair(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = FlakyRecordingLLM(
                [
                    _selection(None),
                    _tool_call("s1"),
                    _tool_call("s2"),
                    _final(),
                ],
                fail_on_call_indexes={2},
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
                context_limit=100_000,
            )
            observation = _observation("s1", {"echo": "one"})

            agent.run("do the task")
            with self.assertRaises(LLMCallError):
                agent.run_with_observation("do the task", observation)
            # 运行时的 provider 恢复会用同一个观察重调一次：不允许追加
            # 重复的交换对，消息列表必须与失败那次逐字节相同。
            agent.run_with_observation("do the task", observation)
            agent.run_with_observation(
                "do the task", _observation("s2", {"echo": "two"})
            )

            self.assertEqual(serialize(llm.calls[2]), serialize(llm.calls[3]))
            self.assert_strict_prefix_extension(llm.calls[3], llm.calls[4])
            self.assertEqual(len(llm.calls[4]) - len(llm.calls[3]), 2)


class TestBudgetNoticeAppend(TurnMessageTestCase):
    def test_soft_budget_notice_appends_one_time_user_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = RecordingLLM(
                [
                    _selection(None),
                    _tool_call("s1"),
                    _tool_call("s2"),
                    _final(),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
                context_limit=100_000,
            )
            notice = "系统提示：本次运行 token 预算将尽，请收敛到最少步骤完成任务。"

            agent.run("do the task")
            first = _observation("s1", {"echo": "one"})
            first["budget_notice"] = notice
            agent.run_with_observation("do the task", first)
            agent.run_with_observation(
                "do the task", _observation("s2", {"echo": "two"})
            )

            with_notice = llm.calls[2]
            self.assertEqual(with_notice[-1]["role"], "user")
            self.assertEqual(with_notice[-1]["content"], notice)
            delta_payload = json.loads(with_notice[-2]["content"])
            self.assertNotIn("budget_notice", delta_payload["observation"])
            # 一次性：后续步骤不再重复提示，前缀仍然稳定。
            self.assert_strict_prefix_extension(with_notice, llm.calls[3])
            self.assertEqual(serialize(llm.calls[3]).count("预算将尽"), 1)


if __name__ == "__main__":
    unittest.main()
