import unittest

from yc_agents.cli.suggestions import CommandSuggestionRegistry


class TestCommandSuggestionRegistry(unittest.TestCase):
    def test_filter_returns_all_for_slash(self):
        registry = CommandSuggestionRegistry()

        suggestions = registry.filter("/")

        commands = [suggestion.command for suggestion in suggestions]
        self.assertIn("/session", commands)
        self.assertIn("/workspace", commands)
        self.assertIn("/clear", commands)

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


if __name__ == "__main__":
    unittest.main()
