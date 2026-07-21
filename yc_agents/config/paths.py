import os
import sys
from pathlib import Path


def ycore_home(env=None):
    values = os.environ if env is None else env
    configured = values.get("YCORE_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".ycore"


def source_checkout_root():
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file() and (candidate / "ycore.json").is_file():
        return candidate
    return None


def installed_resource_root():
    return Path(sys.prefix) / "share" / "ycore"


def default_config_path():
    installed = installed_resource_root() / "ycore.json"
    if installed.is_file():
        return installed

    source_root = source_checkout_root()
    if source_root is not None:
        return source_root / "ycore.json"
    return installed


def development_config_path():
    source_root = source_checkout_root()
    return source_root / "ycore.json" if source_root is not None else None


def builtin_skills_dir():
    source_root = source_checkout_root()
    if source_root is not None and (source_root / "skills").is_dir():
        return source_root / "skills"
    return installed_resource_root() / "skills"


def env_template_path():
    source_root = source_checkout_root()
    if source_root is not None and (source_root / ".env.example").is_file():
        return source_root / ".env.example"
    return installed_resource_root() / ".env.example"
