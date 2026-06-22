import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    model: str = ""
    base_url: str = ""
    api_key: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(
            model=str(data.get("model", "")),
            base_url=str(data.get("base_url", "")),
            api_key=str(data.get("api_key", "")),
        )

    def to_dict(self):
        return asdict(self)

    def to_public_dict(self):
        return {
            "model": self.model,
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
        }


class SettingsStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return AppSettings()

        with self.path.open("r", encoding="utf-8") as f:
            return AppSettings.from_dict(json.load(f))

    def save(self, settings):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
        return settings

    def load_with_env_fallback(self):
        settings = self.load()
        return AppSettings(
            model=settings.model
            or os.environ.get("LLM_MODEL_ID", "")
            or os.environ.get("YC_AGENTS_MODEL", ""),
            base_url=settings.base_url
            or os.environ.get("LLM_BASE_URL", "")
            or os.environ.get("YC_AGENTS_BASE_URL", ""),
            api_key=settings.api_key
            or os.environ.get("LLM_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", ""),
        )


def apply_settings_to_env(settings):
    if settings.model:
        os.environ["LLM_MODEL_ID"] = settings.model
    if settings.base_url:
        os.environ["LLM_BASE_URL"] = settings.base_url
    if settings.api_key:
        os.environ["LLM_API_KEY"] = settings.api_key
