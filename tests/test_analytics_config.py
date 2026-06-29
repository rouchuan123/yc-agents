from yc_agents.analytics.config import AnalyticsConfig


def test_config_defaults_are_disabled_and_workspace_local(tmp_path):
    config = AnalyticsConfig.from_ycore(workspace_path=tmp_path, data={})

    assert config.analytics_enabled is False
    assert config.sqlite_mcp_enabled is False
    assert config.db_path == tmp_path / ".ycore" / "sqlite" / "analytics.sqlite"
    assert config.full_text is False
    assert config.strict is False
    assert config.preview_chars == 200
    assert config.max_rows == 100
    assert config.retention_runs == 1000


def test_config_reads_ycore_analytics_block(tmp_path):
    data = {
        "enabled": True,
        "sqliteMcp": {"enabled": True},
        "fullText": True,
        "strict": True,
        "dbPath": str(tmp_path / "configured.sqlite"),
        "previewChars": 80,
        "maxRows": 25,
        "retentionRuns": 50,
    }

    config = AnalyticsConfig.from_ycore(workspace_path=tmp_path, data=data)

    assert config.analytics_enabled is True
    assert config.sqlite_mcp_enabled is True
    assert config.full_text is True
    assert config.strict is True
    assert config.db_path == tmp_path / "configured.sqlite"
    assert config.preview_chars == 80
    assert config.max_rows == 25
    assert config.retention_runs == 50
