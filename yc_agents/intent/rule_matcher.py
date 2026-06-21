DEFAULT_KEYWORDS = {
    "opening-report": ["开题", "开题报告", "选题", "proposal"],
    "literature-review": ["文献", "综述", "研究现状", "literature", "review"],
    "thesis-system-design": ["系统方案", "系统设计", "接口", "数据库", "spring boot"],
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
                    "reason": f"规则关键词命中：{', '.join(matched_keywords)}",
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
