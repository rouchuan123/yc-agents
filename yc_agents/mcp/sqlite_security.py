import re


class SQLSecurityError(ValueError):
    pass


DANGEROUS_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "replace",
    "pragma",
    "attach",
    "detach",
    "vacuum",
}


def normalize_readonly_sql(sql, max_rows=100):
    original = str(sql or "").strip()
    if not original:
        raise SQLSecurityError("SQL is empty")

    stripped = original[:-1].strip() if original.endswith(";") else original
    if ";" in stripped:
        raise SQLSecurityError("Only one SQL statement is allowed")

    lowered = re.sub(r"\s+", " ", stripped).lower()
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        raise SQLSecurityError("Only SELECT or WITH ... SELECT queries are allowed")

    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            raise SQLSecurityError(f"Keyword is not allowed: {keyword}")

    if not re.search(r"\blimit\b", lowered):
        return f"{stripped} LIMIT {int(max_rows)}"

    return stripped
