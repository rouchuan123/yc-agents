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


def format_context_usage(used, limit):
    if limit <= 0:
        return "0% / 0 est"

    percent = int((max(0, used) / limit) * 100)
    percent = max(0, min(100, percent))
    limit_label = _format_token_limit(limit)

    return f"{percent}% / {limit_label} est"


def _format_token_limit(limit):
    if limit >= 1000 and limit % 1000 == 0:
        return f"{limit // 1000}k"

    return str(limit)
