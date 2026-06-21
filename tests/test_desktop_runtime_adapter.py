import unittest

from yc_agents.desktop.run_controller import RunController


class TestRunController(unittest.TestCase):
    def test_redirect_messages_are_queued(self):
        controller = RunController("run_001")

        controller.redirect("focus on outline")

        self.assertEqual(controller.pop_redirects(), ["focus on outline"])
        self.assertEqual(controller.pop_redirects(), [])

    def test_cancel_marks_controller_cancelled(self):
        controller = RunController("run_001")

        controller.cancel()

        self.assertTrue(controller.cancelled)

    def test_pause_and_resume(self):
        controller = RunController("run_001")

        controller.pause()
        self.assertTrue(controller.paused)

        controller.resume()
        self.assertFalse(controller.paused)

    def test_approval_decisions_are_recorded(self):
        controller = RunController("run_001")

        controller.record_approval("approval_001", "allow_once")

        self.assertEqual(controller.approvals["approval_001"], "allow_once")


if __name__ == "__main__":
    unittest.main()
