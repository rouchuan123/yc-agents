import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yc_agents.desktop.settings import AppSettings, SettingsStore, apply_settings_to_env


class TestDesktopSettings(unittest.TestCase):
    def test_loads_defaults_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "app_settings.json")

            settings = store.load()

            self.assertEqual(settings.model, "")
            self.assertEqual(settings.base_url, "")
            self.assertEqual(settings.api_key, "")

    def test_saves_and_loads_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app_settings.json"
            store = SettingsStore(path)

            store.save(
                AppSettings(
                    model="gpt-test",
                    base_url="https://example.test",
                    api_key="secret",
                )
            )
            loaded = store.load()

            self.assertEqual(loaded.model, "gpt-test")
            self.assertEqual(loaded.base_url, "https://example.test")
            self.assertEqual(loaded.api_key, "secret")

    def test_env_fallback_fills_missing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "app_settings.json")

            with patch.dict(
                os.environ,
                {
                    "YC_AGENTS_MODEL": "env-model",
                    "YC_AGENTS_BASE_URL": "https://env.test",
                    "OPENAI_API_KEY": "env-key",
                },
                clear=True,
            ):
                settings = store.load_with_env_fallback()

            self.assertEqual(settings.model, "env-model")
            self.assertEqual(settings.base_url, "https://env.test")
            self.assertEqual(settings.api_key, "env-key")

    def test_apply_settings_to_env_uses_runtime_variable_names(self):
        settings = AppSettings(
            model="gpt-test",
            base_url="https://example.test/v1",
            api_key="secret",
        )

        with patch.dict(os.environ, {}, clear=True):
            apply_settings_to_env(settings)

            self.assertEqual(os.environ["LLM_MODEL_ID"], "gpt-test")
            self.assertEqual(os.environ["LLM_BASE_URL"], "https://example.test/v1")
            self.assertEqual(os.environ["LLM_API_KEY"], "secret")

    def test_to_public_dict_masks_api_key(self):
        settings = AppSettings(
            model="gpt-test",
            base_url="https://example.test",
            api_key="secret",
        )

        public = settings.to_public_dict()

        self.assertEqual(public["model"], "gpt-test")
        self.assertEqual(public["base_url"], "https://example.test")
        self.assertTrue(public["has_api_key"])
        self.assertNotIn("api_key", public)


if __name__ == "__main__":
    unittest.main()
