import unittest

from yc_agents.cli.suggestions import CommandSuggestionRegistry


class TestCommandSuggestionRegistry(unittest.TestCase):
    def test_filter_returns_all_for_slash(self):
        registry = CommandSuggestionRegistry()

        suggestions = registry.filter("/")

        commands = [suggestion.command for suggestion in suggestions]
        self.assertEqual(
            commands,
            [
                "/session",
                "/session new",
                "/session new <title>",
                "/session session_id",
                "/session delete",
                "/session delete session_id",
                "/workspace",
                "/workspace add <path>",
                "/workspace workspace_id",
                "/workspace current",
                "/workspace delete",
                "/workspace delete <path-or-id>",
                "/status",
                "/context",
                "/stop",
                "/skills",
                "/clear",
                "/confirm",
                "/cancel",
                "/exit",
                "/quit",
            ],
        )

    def test_filter_matches_partial_command(self):
        registry = CommandSuggestionRegistry()

        suggestions = registry.filter("/se")

        self.assertEqual(suggestions[0].command, "/session")
        self.assertTrue(all(suggestion.command.startswith("/se") for suggestion in suggestions))

    def test_suggestions_include_short_descriptions(self):
        registry = CommandSuggestionRegistry()

        suggestions = registry.filter("/workspace delete")

        self.assertEqual(suggestions[0].command, "/workspace delete")
        self.assertIn("删除", suggestions[0].description)

    def test_parameterized_suggestions_have_editable_completion_text(self):
        registry = CommandSuggestionRegistry()

        suggestions = registry.filter("/workspace add")

        self.assertEqual(suggestions[0].command, "/workspace add <path>")
        self.assertEqual(suggestions[0].completion, "/workspace add ")


if __name__ == "__main__":
    unittest.main()
