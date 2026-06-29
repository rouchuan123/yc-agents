import pytest

from yc_agents.analytics.config import AnalyticsConfig, parse_bool_env


def test_parse_bool_env_accepts_only_true_false():
    assert parse_bool_env("YCORE_ANALYTICS_ENABLED", "true") is True
    assert parse_bool_env("YCORE_ANALYTICS_ENABLED", "false") is False

    with pytest.raises(ValueError) as exc:
        parse_bool_env("YCORE_ANALYTICS_ENABLED", "1")

    assert "true or false" in str(exc.value)


def test_config_defaults_are_disabled_and_workspace_local(tmp_path, monkeypatch):
    monkeypatch.delenv("YCORE_ANALYTICS_ENABLED", raising=False)
    monkeypatch.delenv("YCORE_SQLITE_MCP_ENABLED", raising=False)
    monkeypatch.delenv("YCORE_ANALYTICS_DB_PATH", raising=False)

    config = AnalyticsConfig.from_env(workspace_path=tmp_path)

    assert config.analytics_enabled is False
    assert config.sqlite_mcp_enabled is False
    assert config.db_path == tmp_path / ".ycore" / "sqlite" / "analytics.sqlite"
    assert config.full_text is False
    assert config.strict is False
    assert config.preview_chars == 200
    assert config.max_rows == 100
    assert config.retention_runs == 1000


def test_config_reads_true_false_and_custom_path(tmp_path, monkeypatch):
    db_path = tmp_path / "custom.sqlite"
    monkeypatch.setenv("YCORE_ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("YCORE_SQLITE_MCP_ENABLED", "true")
    monkeypatch.setenv("YCORE_ANALYTICS_FULL_TEXT", "true")
    monkeypatch.setenv("YCORE_ANALYTICS_STRICT", "true")
    monkeypatch.setenv("YCORE_ANALYTICS_DB_PATH", str(db_path))
    monkeypatch.setenv("YCORE_ANALYTICS_PREVIEW_CHARS", "80")
    monkeypatch.setenv("YCORE_ANALYTICS_MAX_ROWS", "25")
    monkeypatch.setenv("YCORE_ANALYTICS_RETENTION_RUNS", "50")

    config = AnalyticsConfig.from_env(workspace_path=tmp_path)

    assert config.analytics_enabled is True
    assert config.sqlite_mcp_enabled is True
    assert config.full_text is True
    assert config.strict is True
    assert config.db_path == db_path
    assert config.preview_chars == 80
    assert config.max_rows == 25
    assert config.retention_runs == 50
