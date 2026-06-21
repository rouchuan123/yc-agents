DEFAULT_WEIGHTS = {
    "rule": 0.25,
    "semantic": 0.35,
    "llm": 0.40,
}


class IntentRouter:
    def __init__(
        self,
        rule_matcher,
        semantic_matcher,
        llm_classifier,
        weights=None,
    ):
        self.rule_matcher = rule_matcher
        self.semantic_matcher = semantic_matcher
        self.llm_classifier = llm_classifier
        self.weights = weights or DEFAULT_WEIGHTS

    def route(self, user_input, skills):
        scores = {
            skill.name: self._empty_candidate(skill.name)
            for skill in skills
        }

        self._merge_matches(
            scores,
            source="rule",
            matches=self.rule_matcher.match(user_input, skills),
        )
        self._merge_matches(
            scores,
            source="semantic",
            matches=self.semantic_matcher.match(user_input, skills),
        )
        self._merge_llm_selection(
            scores,
            self.llm_classifier.classify(user_input, skills),
        )

        candidates = self._rank_candidates(scores)
        selected = candidates[0] if candidates else None

        return {
            "type": "intent_route",
            "selected_skill": selected["skill_name"] if selected else None,
            "confidence": selected["score"] if selected else 0.0,
            "candidates": candidates,
            "weights": dict(self.weights),
        }

    def _empty_candidate(self, skill_name):
        return {
            "skill_name": skill_name,
            "components": {
                "rule": 0.0,
                "semantic": 0.0,
                "llm": 0.0,
            },
            "reasons": {},
        }

    def _merge_matches(self, scores, source, matches):
        for match in matches:
            skill_name = match.get("skill_name")

            if skill_name not in scores:
                continue

            scores[skill_name]["components"][source] = self._confidence(match)
            scores[skill_name]["reasons"][source] = match.get("reason", "")

    def _merge_llm_selection(self, scores, selection):
        skill_name = selection.get("selected_skill")

        if skill_name not in scores:
            return

        scores[skill_name]["components"]["llm"] = self._confidence(selection)
        scores[skill_name]["reasons"]["llm"] = selection.get("reason", "")

    def _rank_candidates(self, scores):
        candidates = []

        for candidate in scores.values():
            weighted_scores = {
                source: round(
                    candidate["components"][source] * self.weights[source],
                    6,
                )
                for source in self.weights
            }
            score = round(sum(weighted_scores.values()), 6)
            candidates.append(
                {
                    "skill_name": candidate["skill_name"],
                    "score": score,
                    "components": dict(candidate["components"]),
                    "weighted_scores": weighted_scores,
                    "reasons": dict(candidate["reasons"]),
                }
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def _confidence(self, result):
        confidence = result.get("confidence", 0.0)
        return max(0.0, min(1.0, float(confidence)))
