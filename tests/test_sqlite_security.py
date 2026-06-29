import pytest

from yc_agents.mcp.sqlite_security import SQLSecurityError, normalize_readonly_sql


def test_select_without_limit_gets_limit():
    assert normalize_readonly_sql("SELECT * FROM agent_runs", max_rows=100) == (
        "SELECT * FROM agent_runs LIMIT 100"
    )


def test_select_with_existing_limit_is_preserved():
    assert normalize_readonly_sql("SELECT * FROM agent_runs LIMIT 5", max_rows=100) == (
        "SELECT * FROM agent_runs LIMIT 5"
    )


def test_with_select_is_allowed_and_limited():
    sql = "WITH recent AS (SELECT * FROM agent_runs) SELECT * FROM recent"

    assert normalize_readonly_sql(sql, max_rows=10).endswith("LIMIT 10")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM agent_runs",
        "DROP TABLE agent_runs",
        "PRAGMA table_info(agent_runs)",
        "SELECT * FROM agent_runs; DELETE FROM agent_runs",
        "ATTACH DATABASE 'x' AS x",
    ],
)
def test_dangerous_sql_is_rejected(sql):
    with pytest.raises(SQLSecurityError):
        normalize_readonly_sql(sql, max_rows=100)
