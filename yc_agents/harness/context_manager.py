from yc_agents.harness.context_report import build_context_report


class ContextManager:
    def build_skill_selection_context(
        self,
        user_input,
        skills,
        memory_messages=None,
        memory_context=None,
        workspace_context=None,
        include_context_report=False,
        context_budget_tokens=8000,
    ):
        memory = self.build_memory_context(
            session=memory_messages,
            memory_context=memory_context,
        )

        context = {
            "task": "skill_selection",
            "user_input": user_input,
            "workspace": workspace_context or {},
            "memory": memory,
            "skills": [
                self._summarize_skill(skill)
                for skill in skills
            ],
        }

        if include_context_report:
            context["context_report"] = build_context_report(
                context,
                max_tokens=context_budget_tokens,
            )

        return context

    def build_skill_execution_context(
        self,
        user_input,
        selected_skill,
        selection,
        memory_context=None,
        rag_results=None,
        workspace_context=None,
        include_context_report=False,
        context_budget_tokens=8000,
    ):
        memory = self.build_memory_context(memory_context=memory_context)

        context = {
            "task": "skill_execution",
            "user_input": user_input,
            "workspace": workspace_context or {},
            "memory": memory,
            "selected_skill": selected_skill.to_dict(),
            "selection": selection,
            "rag_results": rag_results or [],
        }

        if include_context_report:
            context["context_report"] = build_context_report(
                context,
                max_tokens=context_budget_tokens,
            )

        return context

    def build_memory_context(
        self,
        session=None,
        summary="",
        profile=None,
        memory_context=None,
    ):
        if memory_context is not None:
            result = {
                "session": memory_context.get("session", []),
                "summary": memory_context.get("summary", ""),
                "profile": memory_context.get("profile", {}),
            }
            if "retrieved" in memory_context:
                result["retrieved"] = memory_context.get("retrieved", [])
            return result

        session_messages = session or []
        return {
            "session": session_messages,
            "summary": summary or "",
            "profile": profile or {},
            "retrieved": [],
        }

    def _summarize_skill(self, skill):
        to_summary = getattr(skill, "to_summary", None)
        if to_summary is not None:
            return to_summary()

        return {
            "name": skill.name,
            "description": skill.description,
        }
