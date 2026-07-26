import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.workspaces import WorkspaceStore
from yc_agents.memory.session import SessionMemory


def age_session(session, hours):
    metadata_path = session.path / "session.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    stale_time = datetime.now() - timedelta(hours=hours)
    metadata["updated_at"] = stale_time.isoformat(timespec="seconds")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")


def write_jsonl_messages(path, messages):
    lines = [json.dumps(message, ensure_ascii=False) for message in messages]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestCLISessionStore(unittest.TestCase):
    def _workspace(self, root, name):
        path = root / name
        path.mkdir()
        return WorkspaceStore(ycore_root=root, startup_dir=path).add_workspace(path)

    def test_ensure_current_session_creates_default_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)

            session = store.ensure_current_session()

            self.assertEqual(session.title, "新会话 1")
            self.assertTrue(session.messages_path.exists())
            self.assertEqual(context.current_session_path.read_text(encoding="utf-8"), session.id)

    def test_session_new_with_title_switches_current(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)

            session = store.create_session("代码审查")

            self.assertEqual(session.title, "代码审查")
            self.assertEqual(store.ensure_current_session().id, session.id)
            metadata = json.loads((session.path / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["title"], "代码审查")

    def test_sessions_are_isolated_by_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first_context = self._workspace(root, "first")
            second_context = self._workspace(root, "second")
            first = CLISessionStore(first_context)
            second = CLISessionStore(second_context)

            first_session = first.create_session("代码审查")
            second_session = second.create_session("架构复盘")

            first_session.messages_path.write_text(
                json.dumps([{"role": "user", "content": "A"}]),
                encoding="utf-8",
            )
            second_session.messages_path.write_text(
                json.dumps([{"role": "user", "content": "B"}]),
                encoding="utf-8",
            )

            self.assertNotEqual(first_session.path, second_session.path)
            self.assertEqual(first.load_transcript(), [("You", "A")])
            self.assertEqual(second.load_transcript(), [("You", "B")])

    def test_switch_session_reloads_current_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            first = store.create_session("A")
            second = store.create_session("B")

            switched = store.switch_session(first.id)

            self.assertEqual(switched.id, first.id)
            self.assertEqual(store.ensure_current_session().id, first.id)
            self.assertEqual(store.switch_session(second.id).id, second.id)

    def test_delete_session_removes_session_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            first = store.create_session("A")
            second = store.create_session("B")
            run_dir = first.runs_path / "run_001"
            run_dir.mkdir(parents=True)

            next_session = store.delete_session(first.id)

            self.assertEqual(next_session.id, second.id)
            self.assertFalse(first.path.exists())
            self.assertFalse(first.runs_path.exists())

    def test_delete_only_session_creates_replacement(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            first = store.create_session("Only")

            replacement = store.delete_session(first.id)

            self.assertNotEqual(replacement.id, first.id)
            self.assertEqual(replacement.title, "新会话 1")
            self.assertTrue(replacement.path.exists())
            self.assertEqual(store.ensure_current_session().id, replacement.id)

    def test_load_transcript_limits_recent_messages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            session = store.create_session("History")
            messages = [
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "older"},
                {"role": "user", "content": "new"},
                {"role": "assistant", "content": "newer"},
            ]
            session.messages_path.write_text(json.dumps(messages), encoding="utf-8")

            self.assertEqual(
                store.load_transcript(limit=2),
                [("You", "new"), ("Assistant", "newer")],
            )

    def test_load_transcript_preserves_assistant_process_entries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            session = store.create_session("History")
            messages = [
                {"role": "user", "content": "分析项目"},
                {
                    "role": "assistant",
                    "content": "最终分析",
                    "process_entries": [
                        {"type": "assistant_step", "content": "我先看文件。"},
                        {
                            "type": "tool_result",
                            "tool_name": "workspace_files",
                            "summary": "找到 7 个文件。",
                        },
                    ],
                },
            ]
            session.messages_path.write_text(json.dumps(messages), encoding="utf-8")

            self.assertEqual(
                store.load_transcript(),
                [
                    ("You", "分析项目"),
                    (
                        "Assistant",
                        {
                            "content": "最终分析",
                            "process_entries": [
                                {"type": "assistant_step", "content": "我先看文件。"},
                                {
                                    "type": "tool_result",
                                    "tool_name": "workspace_files",
                                    "summary": "找到 7 个文件。",
                                },
                            ],
                            "process_collapsed": True,
                        },
                    ),
                ],
            )


class TestSessionFreshness(unittest.TestCase):
    def _store(self, root):
        context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
        return CLISessionStore(context)

    def test_stale_session_rotates_to_new_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            old = store.create_session("旧会话")
            write_jsonl_messages(old.messages_path, [{"role": "user", "content": "旧消息"}])
            age_session(old, hours=48)

            fresh = store.ensure_current_session(freshness_hours=12)

            self.assertNotEqual(fresh.id, old.id)
            self.assertEqual(store.ensure_current_session().id, fresh.id)
            self.assertTrue(old.path.exists())

    def test_fresh_session_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            session = store.create_session("活跃会话")
            write_jsonl_messages(session.messages_path, [{"role": "user", "content": "刚聊过"}])

            self.assertEqual(
                store.ensure_current_session(freshness_hours=12).id,
                session.id,
            )

    def test_freshness_disabled_reuses_stale_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            old = store.create_session("旧会话")
            write_jsonl_messages(old.messages_path, [{"role": "user", "content": "旧消息"}])
            age_session(old, hours=48)

            self.assertEqual(store.ensure_current_session().id, old.id)
            self.assertEqual(store.ensure_current_session(freshness_hours=0).id, old.id)
            self.assertEqual(store.ensure_current_session(freshness_hours=None).id, old.id)

    def test_stale_empty_session_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            old = store.create_session("空会话")
            age_session(old, hours=48)

            self.assertEqual(store.ensure_current_session(freshness_hours=12).id, old.id)

    def test_stale_most_recent_listed_session_rotates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            old = store.create_session("旧会话")
            write_jsonl_messages(old.messages_path, [{"role": "user", "content": "旧消息"}])
            age_session(old, hours=48)
            store.current_session_path.write_text("", encoding="utf-8")

            fresh = store.ensure_current_session(freshness_hours=12)

            self.assertNotEqual(fresh.id, old.id)

    def test_switch_session_ignores_freshness(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            old = store.create_session("旧会话")
            write_jsonl_messages(old.messages_path, [{"role": "user", "content": "旧消息"}])
            age_session(old, hours=48)
            store.create_session("新会话")

            self.assertEqual(store.switch_session(old.id).id, old.id)


class TestSessionMessagesStorage(unittest.TestCase):
    def _store(self, root):
        context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
        return CLISessionStore(context)

    def test_new_session_uses_jsonl_messages_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))

            session = store.create_session("JSONL")

            self.assertEqual(session.messages_path.name, "messages.jsonl")
            self.assertTrue(session.messages_path.exists())

    def test_load_transcript_reads_jsonl_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            session = store.create_session("JSONL")
            write_jsonl_messages(
                session.messages_path,
                [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "好的"},
                ],
            )

            self.assertEqual(
                store.load_transcript(),
                [("You", "你好"), ("Assistant", "好的")],
            )

    def test_legacy_messages_json_stays_readable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = self._store(Path(tmp_dir))
            session = store.create_session("旧格式")
            session.messages_path.unlink()
            (session.path / "messages.json").write_text(
                json.dumps([{"role": "user", "content": "历史消息"}], ensure_ascii=False),
                encoding="utf-8",
            )

            reloaded = store.get_session(session.id)

            self.assertFalse((session.path / "messages.jsonl").exists())
            self.assertEqual(reloaded.messages_path.name, "messages.jsonl")
            self.assertEqual(store.load_transcript(), [("You", "历史消息")])


class TestSessionMemoryJsonl(unittest.TestCase):
    def test_jsonl_save_writes_one_message_per_line(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "messages.jsonl"
            memory = SessionMemory(file_path=path)
            memory.load()
            memory.add_message("user", "你好")
            memory.add_message("assistant", "好的")
            memory.save()

            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), {"role": "user", "content": "你好"})
            self.assertEqual(json.loads(lines[1]), {"role": "assistant", "content": "好的"})

    def test_load_supports_tail_window(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "messages.jsonl"
            write_jsonl_messages(
                path,
                [{"role": "user", "content": f"第{index}条"} for index in range(5)],
            )
            memory = SessionMemory(file_path=path)

            self.assertEqual(len(memory.load(tail=2)), 2)
            self.assertEqual(memory.messages[-1]["content"], "第4条")
            self.assertEqual(len(memory.load()), 5)

    def test_tail_load_then_save_keeps_full_history(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "messages.jsonl"
            write_jsonl_messages(
                path,
                [{"role": "user", "content": f"第{index}条"} for index in range(4)],
            )
            memory = SessionMemory(file_path=path)
            memory.load(tail=1)
            memory.add_message("assistant", "第五条")
            memory.save()

            records = SessionMemory(file_path=path).load()
            self.assertEqual(len(records), 5)
            self.assertEqual(records[0]["content"], "第0条")
            self.assertEqual(records[-1]["content"], "第五条")

    def test_legacy_array_file_migrates_on_first_save(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            legacy = Path(tmp_dir) / "messages.json"
            legacy.write_text(
                json.dumps([{"role": "user", "content": "旧数据"}], ensure_ascii=False),
                encoding="utf-8",
            )
            memory = SessionMemory(file_path=Path(tmp_dir) / "messages.jsonl")

            self.assertEqual(memory.load(), [{"role": "user", "content": "旧数据"}])

            memory.add_message("assistant", "新回复")
            memory.save()

            self.assertFalse(legacy.exists())
            records = SessionMemory(file_path=Path(tmp_dir) / "messages.jsonl").load()
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["content"], "旧数据")

    def test_json_suffix_keeps_array_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "session.json"
            memory = SessionMemory(file_path=path)
            memory.add_message("user", "hello")
            memory.save()

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved, [{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
