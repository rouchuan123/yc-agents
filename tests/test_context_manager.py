import unittest

from yc_agents.harness.context_manager import ContextManager
from yc_agents.skills.definition import SkillDefinition


def make_skill():
    return SkillDefinition(
        name="code-review",
        description="Project architecture review",
        allowed_tools=["workspace_files", "file_reader"],
        body="Complete skill body",
        path="skills/code-review",
    )


class TestContextManager(unittest.TestCase):
    def test_build_skill_selection_context(self):
        result = ContextManager().build_skill_selection_context(
            "review this project",
            [make_skill()],
        )

        self.assertEqual(result["task"], "skill_selection")
        self.assertEqual(result["user_input"], "review this project")
        self.assertEqual(
            result["skills"],
            [
                {
                    "name": "code-review",
                    "description": "Project architecture review",
                    "triggers": [],
                    "inputs": [],
                    "outputs": [],
                    "allowed_tools": ["workspace_files", "file_reader"],
                }
            ],
        )

    def test_build_skill_selection_context_includes_memory_and_workspace(self):
        memory = {
            "session": [{"role": "user", "content": "previous question"}],
            "summary": "Already discussed project structure",
            "profile": {"preferred_output": "concise"},
        }

        result = ContextManager().build_skill_selection_context(
            "continue",
            [make_skill()],
            memory_context=memory,
            workspace_context={"path": r"E:\project"},
        )

        self.assertEqual(result["memory"], memory)
        self.assertEqual(result["recent_messages"], memory["session"])
        self.assertEqual(result["workspace"]["path"], r"E:\project")

    def test_build_memory_context_compresses_session_when_threshold_reached(self):
        class FakeCompressor:
            def __init__(self):
                self.received_messages = None

            def compress_and_save(self, messages):
                self.received_messages = messages
                return "compressed summary"

        messages = [
            {"role": "user", "content": "question 1"},
            {"role": "assistant", "content": "answer 1"},
            {"role": "user", "content": "question 2"},
        ]
        compressor = FakeCompressor()

        result = ContextManager().build_memory_context(
            session=messages,
            summary="old summary",
            memory_compressor=compressor,
            compression_threshold=3,
        )

        self.assertEqual(result["summary"], "compressed summary")
        self.assertEqual(compressor.received_messages, messages)

    def test_build_skill_execution_context_includes_selected_skill_and_rag(self):
        rag_results = [{"source": "notes.md", "text": "architecture"}]

        result = ContextManager().build_skill_execution_context(
            user_input="summarize architecture",
            selected_skill=make_skill(),
            selection={"selected_skill": "code-review"},
            memory_context={"session": [], "summary": "", "profile": {}},
            rag_results=rag_results,
        )

        self.assertEqual(result["task"], "skill_execution")
        self.assertEqual(result["selected_skill"]["name"], "code-review")
        self.assertEqual(result["rag_results"], rag_results)


if __name__ == "__main__":
    unittest.main()
