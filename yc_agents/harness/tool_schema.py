from dataclasses import dataclass
from copy import deepcopy


class ToolValidationError(ValueError):
    pass


TYPE_MAP = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "dict": dict,
    "list": list,
}


OPENAI_JSON_SCHEMA_TYPES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "dict": "object",
    "list": "array",
}


@dataclass(frozen=True)
class ToolField:
    name: str
    type: str
    required: bool = True
    default: object = None
    json_schema: dict | None = None
    description: str = ""


@dataclass(frozen=True)
class ToolSchema:
    fields: list[ToolField]

    def validate(self, arguments):
        arguments = dict(arguments)
        validated = {}

        for field in self.fields:
            if field.name not in arguments:
                if field.required:
                    raise ToolValidationError(f"Missing required field: {field.name}")
                validated[field.name] = field.default
                continue

            value = arguments[field.name]
            expected_type = TYPE_MAP[field.type]
            if not isinstance(value, expected_type):
                raise ToolValidationError(
                    f"Field {field.name} expected {field.type}, got {type(value).__name__}"
                )

            validated[field.name] = value

        extra = set(arguments) - {field.name for field in self.fields}
        if extra:
            raise ToolValidationError(f"Unknown fields: {sorted(extra)}")

        return validated

    def to_openai_schema(self):
        """把字段定义翻译成 OpenAI tools 的 parameters JSON Schema，让原生
        function calling 与文本协议共用同一份工具契约。"""
        properties = {}
        required = []

        for field in self.fields:
            json_type = OPENAI_JSON_SCHEMA_TYPES.get(field.type)
            if json_type is None:
                raise ToolValidationError(
                    f"Cannot export field {field.name} to an OpenAI schema: "
                    f"unknown type {field.type}. Use one of "
                    f"{sorted(OPENAI_JSON_SCHEMA_TYPES)}."
                )
            prop = (
                deepcopy(field.json_schema)
                if field.json_schema is not None
                else {"type": json_type}
            )
            if field.description:
                prop["description"] = field.description
            if not field.required and field.default is not None:
                prop["default"] = field.default
            properties[field.name] = prop
            if field.required:
                required.append(field.name)

        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = required
        return schema
