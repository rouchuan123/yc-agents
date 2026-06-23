import pytest

from yc_agents.harness.tool_schema import ToolField, ToolSchema, ToolValidationError


def test_tool_schema_accepts_valid_arguments():
    schema = ToolSchema(
        fields=[
            ToolField(name="path", type="str", required=True),
            ToolField(name="overwrite", type="bool", required=False, default=False),
        ]
    )

    validated = schema.validate({"path": "demo.md"})

    assert validated == {"path": "demo.md", "overwrite": False}


def test_tool_schema_rejects_missing_required_field():
    schema = ToolSchema(fields=[ToolField(name="path", type="str", required=True)])

    with pytest.raises(ToolValidationError) as exc:
        schema.validate({})

    assert "path" in str(exc.value)


def test_tool_schema_rejects_wrong_type():
    schema = ToolSchema(fields=[ToolField(name="overwrite", type="bool", required=True)])

    with pytest.raises(ToolValidationError):
        schema.validate({"overwrite": "yes"})
