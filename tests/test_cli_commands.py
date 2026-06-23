import unittest

from yc_agents.cli.commands import parse_cli_input


class TestCLICommands(unittest.TestCase):
    def test_empty_input_is_ignored(self):
        command = parse_cli_input("   ")

        self.assertEqual(command.action, "ignore")
        self.assertEqual(command.content, "")

    def test_regular_text_is_message(self):
        command = parse_cli_input("hello agent")

        self.assertEqual(command.action, "message")
        self.assertEqual(command.content, "hello agent")

    def test_exit_commands(self):
        self.assertEqual(parse_cli_input("/exit").action, "exit")
        self.assertEqual(parse_cli_input("/quit").action, "exit")

    def test_status_command(self):
        command = parse_cli_input("/status")

        self.assertEqual(command.action, "status")
        self.assertEqual(command.content, "")

    def test_clear_command(self):
        command = parse_cli_input("/clear")

        self.assertEqual(command.action, "clear")

    def test_unknown_slash_command(self):
        command = parse_cli_input("/model deepseek")

        self.assertEqual(command.action, "unknown")
        self.assertEqual(command.content, "/model deepseek")

    def test_slash_inside_message_is_not_command(self):
        command = parse_cli_input("please read /status docs")

        self.assertEqual(command.action, "message")
        self.assertEqual(command.content, "please read /status docs")


if __name__ == "__main__":
    unittest.main()
