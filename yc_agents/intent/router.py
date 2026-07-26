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
        short_circuit_threshold=0.35,
        short_circuit_ratio=2.0,
    ):
        self.rule_matcher = rule_matcher
        self.semantic_matcher = semantic_matcher
        self.llm_classifier = llm_classifier
        self.weights = weights or DEFAULT_WEIGHTS
        self.short_circuit_threshold = float(short_circuit_threshold)
        self.short_circuit_ratio = float(short_circuit_ratio)

    def route(self, user_input, skills, allow_llm_skip=False):
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
        # LLM classification is advisory: any failure (malformed JSON, provider
        # outage) degrades to rule+semantic routing instead of killing the run.
        llm_error = None
        llm_skipped = False
        if allow_llm_skip and self._rule_semantic_lead_is_decisive(scores):
            # A decisive rule+semantic agreement makes the LLM vote redundant,
            # so skipping it saves one classification call for this turn.
            llm_skipped = True
        else:
            try:
                self._merge_llm_selection(
                    scores,
                    self.llm_classifier.classify(user_input, skills),
                )
            except Exception as exc:
                llm_error = f"{exc.__class__.__name__}: {exc}"

        candidates = self._rank_candidates(scores)
        selected = candidates[0] if candidates else None

        result = {
            "type": "intent_route",
            "selected_skill": selected["skill_name"] if selected else None,
            "confidence": selected["score"] if selected else 0.0,
            "candidates": candidates,
            "weights": dict(self.weights),
        }
        if llm_skipped:
            result["llm_skipped"] = True
        if llm_error is not None:
            result["llm_error"] = llm_error
        return result

    def _rule_semantic_lead_is_decisive(self, scores):
        fused = sorted(
            (
                candidate["components"]["rule"] * self.weights.get("rule", 0.0)
                + candidate["components"]["semantic"] * self.weights.get("semantic", 0.0)
                for candidate in scores.values()
            ),
            reverse=True,
        )
        if not fused:
            return False

        top = fused[0]
        runner_up = fused[1] if len(fused) > 1 else 0.0
        if top <= self.short_circuit_threshold:
            return False

        return top >= runner_up * self.short_circuit_ratio

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
