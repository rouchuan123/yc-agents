import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.harness.path_policy import PathPolicy, PathPolicyError


class TestPathPolicy(unittest.TestCase):
    def test_allows_project_relative_path(self):
        policy = PathPolicy(project_root=".")

        result = policy.validate_write_path("outputs/test.md")

        self.assertTrue(str(result).endswith("outputs\\test.md") or str(result).endswith("outputs/test.md"))

    def test_rejects_env_file(self):
        policy = PathPolicy(project_root=".")

        with self.assertRaises(PathPolicyError):
            policy.validate_write_path(".env")

    def test_rejects_parent_directory_escape(self):
        policy = PathPolicy(project_root=".")

        with self.assertRaises(PathPolicyError):
            policy.validate_write_path("../outside.md")

    def test_rejects_absolute_path(self):
        policy = PathPolicy(project_root=".")

        with self.assertRaises(PathPolicyError):
            policy.validate_write_path("E:/outside.md")

    def test_rejects_nested_env_file(self):
        policy = PathPolicy(project_root=".")

        with self.assertRaises(PathPolicyError):
            policy.validate_write_path("config/.env")

    def test_rejects_overwrite_of_protected_file_without_explicit_allow(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "requirements.txt"
            path.write_text("old", encoding="utf-8")
            policy = PathPolicy(project_root=tmpdir)

            with self.assertRaises(PathPolicyError):
                policy.validate_write_path("requirements.txt")

    def test_allows_overwrite_of_protected_file_when_explicitly_allowed(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "requirements.txt"
            path.write_text("old", encoding="utf-8")
            policy = PathPolicy(project_root=tmpdir)

            result = policy.validate_write_path(
                "requirements.txt",
                allow_overwrite=True,
            )

            self.assertEqual(result, path.resolve())


if __name__ == "__main__":
    unittest.main()
