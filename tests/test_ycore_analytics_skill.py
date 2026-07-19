from yc_agents.skills.loader import SkillLoader


def test_ycore_analytics_skill_does_not_declare_tool_permissions():
    skills = {skill.name: skill for skill in SkillLoader("skills").load_all()}

    skill = skills["ycore-analytics"]

    assert skill.allowed_tools == []
    assert "allowed_tools" not in skill.to_dict()
    assert "运行情况" in skill.description
