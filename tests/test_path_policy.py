import unittest

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


if __name__ == "__main__":
    unittest.main()