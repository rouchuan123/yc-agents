import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TOOL_ENTRIES = {
    "workspace_files": {"enabled": True},
    "file_reader": {"enabled": True},
    "workspace_write": {"enabled": True},
    "markdown_writer": {"enabled": True},
    "rag_search": {"enabled": True},
    "web_search": {"enabled": True},
    "git_inspector": {"enabled": True},
    "code_search": {"enabled": True},
    "verification_runner": {"enabled": True},
    "command_reader": {"enabled": True},
    "memory_search": {"enabled": True},
    "mcp_sqlite_list_tables": {"enabled": True},
    "mcp_sqlite_describe_table": {"enabled": True},
    "mcp_sqlite_query_readonly": {"enabled": True},
}


DEFAULT_CONFIG = {
    "agents": {
        "defaults": {
            "model": {
                "primary": "",
                "fallbacks": [],
            },
        },
        "entries": {"main": {"enabled": True}},
    },
    "models": {
        "mode": "merge",
        "providers": {},
    },
    "skills": {
        "dirs": ["skills"],
        "entries": {},
    },
    "tools": {
        "profile": "coding",
        "entries": copy.deepcopy(DEFAULT_TOOL_ENTRIES),
        "web": {
            "search": {
                "provider": "tavily",
                "apiKeyEnv": "TAVILY_API_KEY",
            }
        },
    },
    "mcp": {"servers": {}},
    "runtime": {
        "expectsJson": True,
        "toolCalling": "json-protocol",
        "modelTimeoutSeconds": 60,
        "maxToolCalls": 12,
        "toolTimeoutSeconds": 30,
        "invalidJsonRetryCount": 2,
        "providerRetryCount": 1,
        "providerRetryBackoffSeconds": 1,
        "toolExecutionRetryCount": 1,
        "verificationRetryCount": 1,
        "maxRecoveryAttempts": 4,
        "failOnInvalidJson": True,
    },
    "analytics": {
        "enabled": False,
        "sqliteMcp": {"enabled": False},
        "fullText": False,
        "strict": False,
        "dbPath": None,
        "previewChars": 200,
        "maxRows": 100,
        "retentionRuns": 1000,
    },
    "memory": {
        "enabled": True,
        "compressionThreshold": 12,
        "activeContextMaxTokens": 64000,
        "compactionTriggerPercent": 80,
        "compactionTargetPercent": 50,
        "retrieveTopK": 6,
        "retrievalTokenBudget": 4000,
        "minScore": 0.2,
        "sessionHalfLifeDays": 30,
        "embedding": {"enabled": False},
        "dream": {
            "enabled": False,
            "minSessions": 5,
            "minHours": 24,
            "maxInputTokens": 32000,
        },
    },
}


@dataclass(frozen=True)
class ModelProviderSettings:
    provider: str
    model: str
    api: str
    base_url: str
    api_key: str
    timeout: int
    context_window: int | None = None
    max_output_tokens: int | None = None
    request: dict | None = None
    structured_output_request: dict | None = None


def _deep_merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _merge_lists_by_id(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_lists_by_id(base_items, override_items):
    combined = list(base_items or []) + list(override_items or [])
    if not all(isinstance(item, dict) and "id" in item for item in combined):
        return copy.deepcopy(override_items)

    merged = {item["id"]: copy.deepcopy(item) for item in base_items}
    order = [item["id"] for item in base_items]

    for item in override_items:
        item_id = item["id"]
        if item_id in merged:
            merged[item_id] = _deep_merge(merged[item_id], item)
        else:
            merged[item_id] = copy.deepcopy(item)
            order.append(item_id)

    return [merged[item_id] for item_id in order]


def _mask_secrets(value, key_name=""):
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            lower = str(key).lower()
            is_secret_key = any(
                marker in lower
                for marker in ["apikey", "api_key", "token", "secret", "password"]
            )
            is_env_reference = lower.endswith("env")
            if is_secret_key and not is_env_reference:
                output[key] = "***" if child not in (None, "", False, True) else child
            else:
                output[key] = _mask_secrets(child, key)
        return output

    if isinstance(value, list):
        return [_mask_secrets(item, key_name) for item in value]

    return value


class YCoreConfig:
    def __init__(self, root_path, data, source_path=None, env=None, source_paths=None):
        self.root_path = Path(root_path)
        self.data = data
        self.source_path = source_path
        self.source_paths = list(source_paths or ([] if source_path is None else [source_path]))
        self.env = dict(env or os.environ)

    @classmethod
    def load(cls, root_path, global_path=None):
        root = Path(root_path)
        env = dict(os.environ)
        global_config = (
            Path(global_path)
            if global_path is not None
            else cls.default_global_config_path()
        )

        if not global_config.exists():
            raise ValueError(
                f"Missing global ycore.json: {global_config}. "
                "Create ycore.json for non-secret runtime config. "
                "Put only secrets in .env."
            )

        source_paths = []
        source_configs = []
        search_paths = cls._config_search_paths(root, global_config)
        for path in search_paths:
            if path.exists():
                source_configs.append(
                    (path, json.loads(path.read_text(encoding="utf-8")))
                )

        entries_declared = any(
            isinstance(source_data.get("tools", {}).get("entries"), dict)
            for _path, source_data in source_configs
        )
        data = copy.deepcopy(DEFAULT_CONFIG)
        for path, source_data in source_configs:
            data = _deep_merge(data, source_data)
            source_paths.append(path)

        if not entries_declared:
            legacy_allow = data.get("tools", {}).get("allow")
            if isinstance(legacy_allow, list):
                legacy_names = [str(name) for name in legacy_allow]
                enabled_names = set(legacy_names)
                known_names = list(
                    dict.fromkeys([*legacy_names, *DEFAULT_TOOL_ENTRIES])
                )
                data.setdefault("tools", {})["entries"] = {
                    name: {"enabled": name in enabled_names}
                    for name in known_names
                }

        return cls(
            root,
            data,
            source_path=source_paths[-1],
            env=env,
            source_paths=source_paths,
        )

    @classmethod
    def _config_search_paths(cls, root, global_path):
        paths = [
            Path(global_path),
            Path(root) / ".ycore" / "ycore.json",
        ]

        unique_paths = []
        seen = set()
        for path in paths:
            resolved = path.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_paths.append(path)
        return unique_paths

    @staticmethod
    def default_global_config_path():
        return Path(__file__).resolve().parents[2] / "ycore.json"

    @property
    def primary_model_ref(self):
        return self.data["agents"]["defaults"]["model"]["primary"]

    def resolve_model_provider(self):
        primary = self.primary_model_ref
        if "/" not in primary:
            raise ValueError("agents.defaults.model.primary must use provider/model format")

        provider_id, model_id = primary.split("/", 1)
        providers = self.data.get("models", {}).get("providers", {})
        if provider_id not in providers:
            raise ValueError(f"Model provider not configured: {provider_id}")

        provider = providers[provider_id]
        model_entry = self.model_entry(provider_id, model_id)
        structured = model_entry.get("structuredOutput") or {}
        structured_request = {}
        if structured.get("enabled"):
            structured_request = dict(structured.get("request") or {})
        api_key = self._resolve_secret(provider, "apiKey", "apiKeyEnv")
        timeout = int(self.data.get("runtime", {}).get("modelTimeoutSeconds", 60))
        return ModelProviderSettings(
            provider=provider_id,
            model=model_id,
            api=provider.get("api", "openai-completions"),
            base_url=provider.get("baseUrl", ""),
            api_key=api_key,
            timeout=timeout,
            context_window=model_entry.get("contextWindow"),
            max_output_tokens=model_entry.get("maxOutputTokens"),
            request=dict(model_entry.get("request") or {}),
            structured_output_request=structured_request,
        )

    def resolve_web_search_api_key(self):
        search = self.data.get("tools", {}).get("web", {}).get("search", {})
        return self._resolve_secret(search, "apiKey", "apiKeyEnv")

    def model_entry(self, provider_id, model_id):
        provider = self.data.get("models", {}).get("providers", {}).get(provider_id, {})
        for model in provider.get("models") or []:
            if model.get("id") == model_id:
                return dict(model)
        return {}

    def tool_entries(self):
        entries = self.data.get("tools", {}).get("entries") or {}
        return {
            str(name): dict(settings) if isinstance(settings, dict) else {"enabled": bool(settings)}
            for name, settings in entries.items()
        }

    def enabled_tools(self):
        return [
            name
            for name, settings in self.tool_entries().items()
            if bool(settings.get("enabled", False))
        ]

    def allowed_tools(self):
        return self.enabled_tools()

    def skills_dirs(self):
        return list(self.data.get("skills", {}).get("dirs") or ["skills"])

    def analytics_data(self):
        return dict(self.data.get("analytics") or {})

    def runtime_data(self):
        return dict(self.data.get("runtime") or {})

    def memory_data(self):
        return dict(self.data.get("memory") or {})

    def to_safe_dict(self):
        return _mask_secrets(self.data)

    def _resolve_secret(self, data, value_key, env_key):
        env_name = data.get(env_key)
        if env_name:
            value = self.env.get(env_name, "")
            if value:
                return value
        return data.get(value_key, "") or ""
