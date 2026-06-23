from yc_agents.skills.definition import SkillDefinition
from yc_agents.skills.discovery import SkillDiscoveryIndex


def make_skill(name, description, triggers):
    return SkillDefinition(
        name=name,
        description=description,
        body="",
        path="skills/" + name,
        references=[],
        scripts=[],
        assets=[],
        triggers=triggers,
        inputs=[],
        outputs=[],
        allowed_tools=[],
        examples=[],
    )


def test_skill_discovery_returns_top_k_by_trigger():
    index = SkillDiscoveryIndex(
        [
            make_skill("literature-review", "文献综述", ["文献综述", "论文"]),
            make_skill("system-design", "系统设计", ["系统架构", "设计"]),
        ]
    )

    results = index.search("帮我写文献综述", top_k=1)

    assert results[0].skill.name == "literature-review"
    assert results[0].score > 0


def test_skill_summary_includes_discovery_metadata():
    skill = make_skill("literature-review", "文献综述", ["论文"])
    skill.inputs = ["topic"]
    skill.outputs = ["markdown"]
    skill.allowed_tools = ["rag_search"]

    summary = skill.to_summary()

    assert summary["triggers"] == ["论文"]
    assert summary["inputs"] == ["topic"]
    assert summary["outputs"] == ["markdown"]
    assert summary["allowed_tools"] == ["rag_search"]
