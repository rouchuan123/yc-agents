import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from yc_agents.config.ycore import YCoreConfig


class TestYCoreConfig(unittest.TestCase):
    def test_missing_global_ycore_json_raises_clear_error(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            missing_global = root / "missing-global-ycore.json"

            with self.assertRaisesRegex(ValueError, "Missing global ycore.json"):
                YCoreConfig.load(workspace, global_path=missing_global)

    def test_workspace_root_ycore_json_is_not_loaded(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            global_config = root / "global-ycore.json"
            global_config.write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {
                                "model": {"primary": "deepseek/deepseek-v4-flash"}
                            }
                        },
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                                    "models": [{"id": "deepseek-v4-flash"}],
                                }
                            }
                        },
                        "analytics": {"enabled": False},
                    }
                ),
                encoding="utf-8",
            )
            (workspace / "ycore.json").write_text(
                json.dumps({"analytics": {"enabled": True}}),
                encoding="utf-8",
            )

            config = YCoreConfig.load(workspace, global_path=global_config)

            self.assertEqual(config.source_paths, [global_config])
            self.assertFalse(config.analytics_data()["enabled"])

    def test_loads_global_ycore_json_when_workspace_has_no_config(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            global_config = root / "global-ycore.json"
            global_config.write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {
                                "model": {
                                    "primary": "deepseek/deepseek-v4-flash",
                                }
                            }
                        },
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                                    "models": [{"id": "deepseek-v4-flash"}],
                                }
                            }
                        },
                        "analytics": {
                            "enabled": True,
                            "sqliteMcp": {"enabled": True},
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
                config = YCoreConfig.load(workspace, global_path=global_config)

            provider = config.resolve_model_provider()
            self.assertEqual(provider.model, "deepseek-v4-flash")
            self.assertTrue(config.analytics_data()["enabled"])
            self.assertTrue(config.analytics_data()["sqliteMcp"]["enabled"])
            self.assertEqual(config.source_path, global_config)

    def test_workspace_dot_ycore_config_partially_overrides_global_ycore_json(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".ycore").mkdir()
            global_config = root / "global-ycore.json"
            global_config.write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {
                                "model": {
                                    "primary": "deepseek/deepseek-v4-flash",
                                }
                            }
                        },
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                                    "models": [{"id": "deepseek-v4-flash"}],
                                }
                            }
                        },
                        "tools": {
                            "allow": ["workspace_files", "file_reader"],
                        },
                        "analytics": {
                            "enabled": False,
                            "sqliteMcp": {"enabled": False},
                            "maxRows": 100,
                        },
                    }
                ),
                encoding="utf-8",
            )
            workspace_override = workspace / ".ycore" / "ycore.json"
            workspace_override.write_text(
                json.dumps(
                    {
                        "analytics": {
                            "enabled": True,
                            "sqliteMcp": {"enabled": True},
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = YCoreConfig.load(workspace, global_path=global_config)

            self.assertEqual(config.primary_model_ref, "deepseek/deepseek-v4-flash")
            self.assertEqual(config.allowed_tools(), ["workspace_files", "file_reader"])
            self.assertTrue(config.analytics_data()["enabled"])
            self.assertTrue(config.analytics_data()["sqliteMcp"]["enabled"])
            self.assertEqual(config.analytics_data()["maxRows"], 100)
            self.assertEqual(config.source_path, workspace_override)

    def test_workspace_tool_entries_override_enabled_state(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".ycore").mkdir()
            global_config = root / "global-ycore.json"
            global_config.write_text(
                json.dumps(
                    {
                        "tools": {
                            "entries": {
                                "workspace_files": {"enabled": True},
                                "web_search": {"enabled": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (workspace / ".ycore" / "ycore.json").write_text(
                json.dumps(
                    {
                        "tools": {
                            "entries": {
                                "web_search": {"enabled": False},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = YCoreConfig.load(workspace, global_path=global_config)

            self.assertIn("workspace_files", config.enabled_tools())
            self.assertNotIn("web_search", config.enabled_tools())
            self.assertFalse(config.tool_entries()["web_search"]["enabled"])

    def test_workspace_dot_ycore_models_merge_by_id(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".ycore").mkdir()
            global_config = root / "global-ycore.json"
            global_config.write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {
                                "model": {"primary": "deepseek/deepseek-v4-flash"}
                            }
                        },
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                                    "models": [
                                        {
                                            "id": "deepseek-v4-flash",
                                            "name": "deepseek-v4-flash",
                                            "contextWindow": 64000,
                                            "maxOutputTokens": 4096,
                                            "request": {
                                                "max_tokens": 4096,
                                                "temperature": 0.2,
                                                "top_p": 0.95,
                                            },
                                        }
                                    ],
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (workspace / ".ycore" / "ycore.json").write_text(
                json.dumps(
                    {
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "models": [
                                        {
                                            "id": "deepseek-v4-flash",
                                            "request": {"max_tokens": 8192},
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = YCoreConfig.load(workspace, global_path=global_config)
            model = config.model_entry("deepseek", "deepseek-v4-flash")

            self.assertEqual(model["name"], "deepseek-v4-flash")
            self.assertEqual(model["contextWindow"], 64000)
            self.assertEqual(model["maxOutputTokens"], 4096)
            self.assertEqual(model["request"]["max_tokens"], 8192)
            self.assertEqual(model["request"]["temperature"], 0.2)
            self.assertEqual(model["request"]["top_p"], 0.95)

    def test_loads_root_ycore_json_and_resolves_primary_model(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "ycore.json").write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {
                                "model": {
                                    "primary": "deepseek/deepseek-v4-flash",
                                    "fallbacks": [],
                                }
                            }
                        },
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "api": "openai-completions",
                                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                                    "models": [{"id": "deepseek-v4-flash"}],
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
                config = YCoreConfig.load(root, global_path=root / "ycore.json")

            provider = config.resolve_model_provider()
            self.assertEqual(config.primary_model_ref, "deepseek/deepseek-v4-flash")
            self.assertEqual(provider.provider, "deepseek")
            self.assertEqual(provider.model, "deepseek-v4-flash")
            self.assertEqual(provider.base_url, "https://api.deepseek.com")
            self.assertEqual(provider.api_key, "secret")
            self.assertEqual(provider.api, "openai-completions")

    def test_resolve_model_provider_includes_model_request_metadata(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            global_config = root / "global-ycore.json"
            global_config.write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {
                                "model": {"primary": "deepseek/deepseek-v4-flash"}
                            }
                        },
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "api": "openai-completions",
                                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                                    "models": [
                                        {
                                            "id": "deepseek-v4-flash",
                                            "contextWindow": 64000,
                                            "maxOutputTokens": 4096,
                                            "request": {
                                                "max_tokens": 4096,
                                                "temperature": 0.2,
                                            },
                                            "structuredOutput": {
                                                "enabled": True,
                                                "request": {
                                                    "response_format": {
                                                        "type": "json_object"
                                                    }
                                                },
                                            },
                                        }
                                    ],
                                }
                            }
                        },
                        "runtime": {"modelTimeoutSeconds": 60},
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
                settings = YCoreConfig.load(
                    root,
                    global_path=global_config,
                ).resolve_model_provider()

            self.assertEqual(settings.context_window, 64000)
            self.assertEqual(settings.max_output_tokens, 4096)
            self.assertEqual(
                settings.request,
                {"max_tokens": 4096, "temperature": 0.2},
            )
            self.assertEqual(
                settings.structured_output_request,
                {"response_format": {"type": "json_object"}},
            )

    def test_safe_dict_masks_secret_values(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "ycore.json").write_text(
                json.dumps(
                    {
                        "agents": {"defaults": {"model": {"primary": "deepseek/m"}}},
                        "models": {
                            "providers": {
                                "deepseek": {
                                    "baseUrl": "https://api.deepseek.com",
                                    "apiKey": "plain-secret",
                                    "models": [{"id": "m"}],
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = YCoreConfig.load(root, global_path=root / "ycore.json")
            safe = config.to_safe_dict()

            self.assertEqual(
                safe["models"]["providers"]["deepseek"]["apiKey"],
                "***",
            )


if __name__ == "__main__":
    unittest.main()
