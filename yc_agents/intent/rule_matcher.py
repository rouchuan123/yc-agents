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

MARKDOWN_OUTPUT_MARKERS = ("markdown", ".md", "md文档", "md 文档")
DOCX_OUTPUT_MARKERS = ("word", "docx", ".docx")


class RuleIntentMatcher:
    def __init__(self, keywords=None):
        self.keywords = keywords or DEFAULT_KEYWORDS

    def match(self, user_input, skills):
        text = (user_input or "").lower()
        matches = []

        for skill in skills:
            if self._explicitly_requests_non_docx_markdown(text, skill):
                continue

            matched_keywords, matched_triggers = self._matched_keywords(text, skill)

            if not matched_keywords:
                continue

            confidence = min(1.0, len(matched_keywords) / 3)
            if matched_triggers:
                confidence = max(0.9, confidence)
            matches.append(
                {
                    "skill_name": skill.name,
                    "confidence": confidence,
                    "reason": f"Rule keywords matched: {', '.join(matched_keywords)}",
                    "matched_keywords": matched_keywords,
                    "matched_triggers": matched_triggers,
                }
            )

        matches.sort(key=lambda item: item["confidence"], reverse=True)
        return matches

    def _matched_keywords(self, text, skill):
        configured = list(self.keywords.get(skill.name, []))
        triggers = list(getattr(skill, "triggers", []) or [])
        keywords = list(dict.fromkeys([*configured, *triggers]))
        matched = []
        matched_triggers = []

        for keyword in keywords:
            normalized_keyword = keyword.lower()

            if normalized_keyword in text:
                matched.append(keyword)
                if keyword in triggers:
                    matched_triggers.append(keyword)

        return matched, matched_triggers

    @staticmethod
    def _explicitly_requests_non_docx_markdown(text, skill):
        if getattr(skill, "name", "") != "docx-template-authoring":
            return False
        requests_markdown = any(marker in text for marker in MARKDOWN_OUTPUT_MARKERS)
        requests_docx = any(marker in text for marker in DOCX_OUTPUT_MARKERS)
        return requests_markdown and not requests_docx
