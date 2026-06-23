import re


class SemanticIntentMatcher:
    def match(self, user_input, skills):
        query_terms = self._terms(user_input)

        if not query_terms:
            return []

        matches = []

        for skill in skills:
            skill_terms = self._terms(
                " ".join(
                    [
                        skill.name,
                        skill.description,
                        skill.body,
                    ]
                )
            )
            overlap_terms = sorted(query_terms & skill_terms)

            if not overlap_terms:
                confidence = 0.0
            else:
                confidence = len(overlap_terms) / len(query_terms)

            matches.append(
                {
                    "skill_name": skill.name,
                    "confidence": confidence,
                    "reason": f"文本重叠命中 {len(overlap_terms)} 个语义片段",
                    "overlap_terms": overlap_terms,
                }
            )

        matches.sort(key=lambda item: item["confidence"], reverse=True)
        return matches

    def _terms(self, text):
        normalized_text = (text or "").lower()
        tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized_text))

        for token in list(tokens):
            if self._is_chinese(token) and len(token) > 2:
                tokens.update(
                    token[index:index + 2]
                    for index in range(len(token) - 1)
                )

        return {token for token in tokens if token.strip()}

    def _is_chinese(self, text):
        return all("\u4e00" <= char <= "\u9fff" for char in text)
