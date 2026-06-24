import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.harness.context import RunContext
from yc_agents.harness.episode import EpisodePackage
from yc_agents.harness.run_outputs import RunOutputWriter


class TestEpisodePackage(unittest.TestCase):
    def test_manifest_lists_existing_episode_files(self):
        with TemporaryDirectory() as tmpdir:
            context = RunContext(
                user_input="hello",
                run_id="run_test_episode",
            )
            context.outputs_dir = Path(tmpdir) / context.run_id
            writer = RunOutputWriter(context)
            writer.write_input()
            writer.write_context({"selected_skill": "document-format-normalizer"})
            writer.write_final_output("done")
            writer.write_retrieved_sources(
                [
                    {
                        "source": "paper.md",
                        "chunk_id": "c1",
                        "score": 0.8,
                        "text": "evidence",
                    }
                ]
            )
            writer.write_verification(
                {
                    "passed": True,
                    "checks": [
                        {
                            "name": "final_output_non_empty",
                            "passed": True,
                            "message": "ok",
                        }
                    ],
                }
            )

            manifest = EpisodePackage(context).build_manifest()

            self.assertEqual(manifest["run_id"], "run_test_episode")
            self.assertIn("input.md", manifest["files"])
            self.assertIn("context.json", manifest["files"])
            self.assertIn("final_output.md", manifest["files"])
            self.assertIn("retrieved_sources.md", manifest["files"])
            self.assertIn("verification.md", manifest["files"])


if __name__ == "__main__":
    unittest.main()

