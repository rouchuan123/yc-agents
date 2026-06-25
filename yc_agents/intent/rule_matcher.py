DEFAULT_KEYWORDS = {
    "code-review": [
        "review",
        "architecture",
        "risk",
        "risks",
        "test gap",
        "code review",
        "project review",
    ],
}


class RuleIntentMatcher:
    def __init__(self, keywords=None):
        self.keywords = keywords or DEFAULT_KEYWORDS

    def match(self, user_input, skills):
        text = (user_input or "").lower()
        matches = []

        for skill in skills:
            matched_keywords = self._matched_keywords(text, skill)

            if not matched_keywords:
                continue

            matches.append(
                {
                    "skill_name": skill.name,
                    "confidence": min(1.0, len(matched_keywords) / 3),
                    "reason": f"Rule keywords matched: {', '.join(matched_keywords)}",
                    "matched_keywords": matched_keywords,
                }
            )

        matches.sort(key=lambda item: item["confidence"], reverse=True)
        return matches

    def _matched_keywords(self, text, skill):
        keywords = self.keywords.get(skill.name, [])
        matched = []

        for keyword in keywords:
            normalized_keyword = keyword.lower()

            if normalized_keyword in text:
                matched.append(keyword)

        return matched
