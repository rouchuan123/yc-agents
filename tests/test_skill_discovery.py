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
            make_skill(
                "code-review",
                "项目架构审查和风险总结",
                ["代码审查", "架构", "风险"],
            ),
            make_skill("eval-writer", "评估用例和指标设计", ["评估", "eval", "测试数据"]),
        ]
    )

    results = index.search(
        "请帮我做一次代码审查并总结架构风险",
        top_k=1,
    )

    assert results[0].skill.name == "code-review"
    assert results[0].score > 0


def test_skill_summary_includes_discovery_metadata():
    skill = make_skill(
        "code-review",
        "项目架构审查和风险总结",
        ["代码审查"],
    )
    skill.inputs = ["project_files"]
    skill.outputs = ["review_note"]
    skill.allowed_tools = ["workspace_files", "file_reader"]

    summary = skill.to_summary()

    assert summary["triggers"] == ["代码审查"]
    assert summary["inputs"] == ["project_files"]
    assert summary["outputs"] == ["review_note"]
    assert summary["allowed_tools"] == ["workspace_files", "file_reader"]
