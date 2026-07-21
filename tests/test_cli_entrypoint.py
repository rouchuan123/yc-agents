import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yc_agents.cli.main import build_parser, initialize_user_environment


class TestCLIEntryPoint(unittest.TestCase):
    def test_parser_supports_help_and_version_without_starting_runtime(self):
        with self.assertRaises(SystemExit) as help_exit:
            build_parser().parse_args(["--help"])
        with self.assertRaises(SystemExit) as version_exit:
            build_parser().parse_args(["--version"])

        self.assertEqual(help_exit.exception.code, 0)
        self.assertEqual(version_exit.exception.code, 0)

    def test_environment_uses_system_then_user_then_development_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            home = root / "home"
            source = root / "source"
            home.mkdir()
            source.mkdir()
            (source / ".env").write_text(
                'DEEPSEEK_API_KEY="development"\nTAVILY_API_KEY="development"\n',
                encoding="utf-8",
            )
            (home / ".env").write_text(
                'DEEPSEEK_API_KEY="user"\nMIMO_API_KEY="user"\n',
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "system"},
                clear=True,
            ), patch(
                "yc_agents.cli.main.ycore_home",
                return_value=home,
            ), patch(
                "yc_agents.cli.main.source_checkout_root",
                return_value=source,
            ):
                initialize_user_environment()
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "system")
                self.assertEqual(os.environ["TAVILY_API_KEY"], "development")
                self.assertEqual(os.environ["MIMO_API_KEY"], "user")

    def test_first_run_creates_user_env_from_template(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            home = root / "home"
            template = root / ".env.example"
            template.write_text('DEEPSEEK_API_KEY=""\n', encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True), patch(
                "yc_agents.cli.main.ycore_home",
                return_value=home,
            ), patch(
                "yc_agents.cli.main.source_checkout_root",
                return_value=None,
            ), patch(
                "yc_agents.cli.main.env_template_path",
                return_value=template,
            ):
                initialized_home = initialize_user_environment()

            self.assertEqual(initialized_home, home)
            self.assertEqual(
                (home / ".env").read_text(encoding="utf-8"),
                'DEEPSEEK_API_KEY=""\n',
            )


if __name__ == "__main__":
    unittest.main()
