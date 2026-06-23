import unittest

from yc_agents.harness.enhanced_demo import build_enhanced_demo_summary


class TestEnhancedDemoSummary(unittest.TestCase):
    def test_summary_lists_enhanced_runtime_capabilities(self):
        summary = build_enhanced_demo_summary()

        self.assertEqual(summary["type"], "enhanced_runtime_demo")
        capability_names = [
            capability["name"]
            for capability in summary["capabilities"]
        ]

        self.assertIn("ProviderHub", capability_names)
        self.assertIn("Memory/RAG", capability_names)
        self.assertIn("IntentRouter", capability_names)
        self.assertIn("PermissionGate", capability_names)
        self.assertIn("EpisodePackage", capability_names)
        self.assertIn("MCPToolAdapter", capability_names)
        self.assertIn("MultiAgentOrchestrator", capability_names)
        self.assertGreaterEqual(len(summary["verification_commands"]), 1)


if __name__ == "__main__":
    unittest.main()
