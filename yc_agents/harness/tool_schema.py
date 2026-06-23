from dataclasses import dataclass


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


@dataclass(frozen=True)
class ToolField:
    name: str
    type: str
    required: bool = True
    default: object = None


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
