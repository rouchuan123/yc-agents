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

    def test_stop_command(self):
        command = parse_cli_input("/stop")

        self.assertEqual(command.action, "stop")
        self.assertEqual(command.content, "")

    def test_skills_command(self):
        command = parse_cli_input("/skills")

        self.assertEqual(command.action, "skills")
        self.assertEqual(command.content, "")

    def test_clear_command(self):
        command = parse_cli_input("/clear")

        self.assertEqual(command.action, "clear")

    def test_confirm_and_cancel_commands(self):
        self.assertEqual(parse_cli_input("/confirm").action, "confirm")
        self.assertEqual(parse_cli_input("/cancel").action, "cancel")

    def test_session_list_command(self):
        command = parse_cli_input("/session")

        self.assertEqual(command.action, "session_list")

    def test_session_new_command(self):
        command = parse_cli_input("/session new")

        self.assertEqual(command.action, "session_new")
        self.assertEqual(command.content, "")

    def test_session_new_with_title(self):
        command = parse_cli_input("/session new 代码审查")

        self.assertEqual(command.action, "session_new")
        self.assertEqual(command.content, "代码审查")

    def test_session_delete_command(self):
        command = parse_cli_input("/session delete session_abc")

        self.assertEqual(command.action, "session_delete")
        self.assertEqual(command.content, "session_abc")

    def test_session_switch_command(self):
        command = parse_cli_input("/session session_abc")

        self.assertEqual(command.action, "session_switch")
        self.assertEqual(command.content, "session_abc")

    def test_workspace_list_command(self):
        command = parse_cli_input("/workspace")

        self.assertEqual(command.action, "workspace_list")

    def test_workspace_add_command(self):
        command = parse_cli_input(r"/workspace add E:\code-project")

        self.assertEqual(command.action, "workspace_add")
        self.assertEqual(command.content, r"E:\code-project")

    def test_workspace_current_command(self):
        command = parse_cli_input("/workspace current")

        self.assertEqual(command.action, "workspace_current")

    def test_workspace_delete_command(self):
        command = parse_cli_input(r"/workspace delete E:\code-project")

        self.assertEqual(command.action, "workspace_delete")
        self.assertEqual(command.content, r"E:\code-project")

    def test_workspace_switch_command(self):
        command = parse_cli_input("/workspace workspace_abc")

        self.assertEqual(command.action, "workspace_switch")
        self.assertEqual(command.content, "workspace_abc")

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
