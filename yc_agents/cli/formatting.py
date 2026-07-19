def middle_truncate(value, max_length):
    text = str(value)

    if max_length <= 0:
        return ""

    if len(text) <= max_length:
        return text

    if max_length <= 3:
        return text[:max_length]

    marker = "..."
    remaining = max_length - len(marker)
    start_len = (remaining + 1) // 2
    end_len = remaining // 2

    return f"{text[:start_len]}{marker}{text[-end_len:]}"


def format_context_usage(used, limit, source="estimated"):
    if limit <= 0:
        return "0/0"

    used = max(0, int(used or 0))
    percent = max(0.0, min(100.0, (used / limit) * 100))
    prefix = "~" if source == "estimated" and used > 0 else ""
    used_label = _format_token_count(used)
    limit_label = _format_token_limit(limit)

    return f"{prefix}{used_label}/{limit_label} ({percent:.2f}%)"


def _format_token_count(tokens):
    tokens = max(0, int(tokens or 0))
    if tokens < 1000:
        return str(tokens)
    value = tokens / 1000
    if tokens % 1000 == 0 or value >= 100:
        return f"{value:.0f}k"
    return f"{value:.1f}k"


def _format_token_limit(limit):
    if limit >= 1000 and limit % 1000 == 0:
        return f"{limit // 1000}k"

    return str(limit)
