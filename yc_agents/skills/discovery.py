from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDiscoveryResult:
    skill: object
    score: float
    matched_terms: list[str]


class SkillDiscoveryIndex:
    def __init__(self, skills):
        self.skills = list(skills)

    def search(self, query, top_k=5):
        query_lower = query.lower()
        results = []

        for skill in self.skills:
            terms = (
                [skill.name, skill.description]
                + list(getattr(skill, "triggers", []))
                + list(getattr(skill, "examples", []))
            )
            matched = [term for term in terms if term and term.lower() in query_lower]
            score = len(matched)

            if score:
                results.append(
                    SkillDiscoveryResult(
                        skill=skill,
                        score=score,
                        matched_terms=matched,
                    )
                )

        return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]
