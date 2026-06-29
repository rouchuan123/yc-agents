from yc_agents.skills.loader import SkillLoader


def test_ycore_analytics_skill_declares_sqlite_mcp_tools():
    skills = {skill.name: skill for skill in SkillLoader("skills").load_all()}

    skill = skills["ycore-analytics"]

    assert "mcp_sqlite_list_tables" in skill.allowed_tools
    assert "mcp_sqlite_describe_table" in skill.allowed_tools
    assert "mcp_sqlite_query_readonly" in skill.allowed_tools
    assert "运行情况" in skill.description
