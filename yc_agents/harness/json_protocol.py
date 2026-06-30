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


def parse_model_json(text, allowed_types=None):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidModelJSONError(
            f"Model output is not valid JSON: {exc.msg}",
            raw_text=text,
        ) from exc

    _validate_base_message(data, text, allowed_types=allowed_types)

    if data["type"] == "tool_call":
        _validate_tool_call(data, text)

    if data["type"] == "final_answer":
        _validate_final_answer(data, text)

    return data


def extract_model_json(text, allowed_types=None):
    raw_text = str(text or "")
    stripped = raw_text.strip()
    if not stripped:
        raise InvalidModelJSONError("Model output is empty", raw_text=raw_text)

    try:
        return "", parse_model_json(stripped, allowed_types=allowed_types)
    except InvalidModelJSONError:
        pass

    fenced = _extract_fenced_json(stripped)
    if fenced is not None:
        preface, candidate = fenced
        return preface, parse_model_json(candidate, allowed_types=allowed_types)

    start = stripped.find("{")
    if start < 0:
        raise InvalidModelJSONError(
            "Model output does not contain JSON",
            raw_text=raw_text,
        )

    decoder = json.JSONDecoder()
    try:
        _data, end = decoder.raw_decode(stripped[start:])
    except json.JSONDecodeError as exc:
        raise InvalidModelJSONError(
            f"Model output is not valid JSON: {exc.msg}",
            raw_text=raw_text,
        ) from exc

    candidate = stripped[start : start + end]
    preface = stripped[:start].strip()
    return preface, parse_model_json(candidate, allowed_types=allowed_types)


def _extract_fenced_json(text):
    fence_start = text.find("```")
    if fence_start < 0:
        return None

    line_end = text.find("\n", fence_start)
    if line_end < 0:
        return None

    fence_header = text[fence_start + 3 : line_end].strip().lower()
    if fence_header and fence_header not in {"json", "jsonc"}:
        return None

    fence_end = text.find("```", line_end + 1)
    if fence_end < 0:
        return None

    preface = text[:fence_start].strip()
    candidate = text[line_end + 1 : fence_end].strip()
    return preface, candidate


def _validate_base_message(data, raw_text, allowed_types=None):
    if not isinstance(data, dict):
        raise InvalidModelJSONError("Model JSON must be an object", raw_text=raw_text)

    message_type = data.get("type")

    if not message_type:
        raise InvalidModelJSONError(
            "Model JSON must include a type field",
            raw_text=raw_text,
        )

    effective_allowed = set(allowed_types or ALLOWED_MESSAGE_TYPES)
    if message_type not in effective_allowed:
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


def _validate_final_answer(data, raw_text):
    if "content" not in data:
        raise InvalidModelJSONError(
            "final_answer JSON must include content",
            raw_text=raw_text,
        )

    if not isinstance(data["content"], str):
        raise InvalidModelJSONError(
            "final_answer content must be a string",
            raw_text=raw_text,
        )
