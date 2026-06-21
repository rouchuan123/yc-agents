import json


ALLOWED_MESSAGE_TYPES = {
    "skill_selection",
    "tool_call",
    "final_answer",
}


class InvalidModelJSONError(ValueError):
    def __init__(self, message, raw_text=""):
        super().__init__(message)
        self.raw_text = raw_text


def parse_model_json(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidModelJSONError(
            f"Model output is not valid JSON: {exc.msg}",
            raw_text=text,
        ) from exc

    _validate_base_message(data, text)

    if data["type"] == "tool_call":
        _validate_tool_call(data, text)

    return data


def _validate_base_message(data, raw_text):
    if not isinstance(data, dict):
        raise InvalidModelJSONError("Model JSON must be an object", raw_text=raw_text)

    message_type = data.get("type")

    if not message_type:
        raise InvalidModelJSONError(
            "Model JSON must include a type field",
            raw_text=raw_text,
        )

    if message_type not in ALLOWED_MESSAGE_TYPES:
        raise InvalidModelJSONError(
            f"Unsupported model JSON type: {message_type}",
            raw_text=raw_text,
        )


def _validate_tool_call(data, raw_text):
    if not data.get("tool_name"):
        raise InvalidModelJSONError(
            "tool_call JSON must include tool_name",
            raw_text=raw_text,
        )

    if "arguments" not in data:
        raise InvalidModelJSONError(
            "tool_call JSON must include arguments",
            raw_text=raw_text,
        )

    if not isinstance(data["arguments"], dict):
        raise InvalidModelJSONError(
            "tool_call arguments must be an object",
            raw_text=raw_text,
        )