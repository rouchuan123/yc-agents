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
                "document-format-normalizer",
                "Word 文档格式调整",
                ["Word 格式", "docx", "模板排版"],
            ),
            make_skill("other-skill", "其他能力", ["聊天"]),
        ]
    )

    results = index.search("帮我把 docx 按模板排版", top_k=1)

    assert results[0].skill.name == "document-format-normalizer"
    assert results[0].score > 0


def test_skill_summary_includes_discovery_metadata():
    skill = make_skill("document-format-normalizer", "Word 文档格式调整", ["docx"])
    skill.inputs = ["source_docx"]
    skill.outputs = ["normalized_docx"]
    skill.allowed_tools = ["docx_format_normalizer"]

    summary = skill.to_summary()

    assert summary["triggers"] == ["docx"]
    assert summary["inputs"] == ["source_docx"]
    assert summary["outputs"] == ["normalized_docx"]
    assert summary["allowed_tools"] == ["docx_format_normalizer"]
