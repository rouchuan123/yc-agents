class ContextManager:
    def build_skill_selection_context(
        self,
        user_input,
        skills,
        memory_messages=None,
        memory_context=None,
        workspace_context=None,
    ):
        memory = self.build_memory_context(
            session=memory_messages,
            memory_context=memory_context,
        )

        return {
            "task": "skill_selection",
            "user_input": user_input,
            "workspace": workspace_context or {},
            "memory": memory,
            "recent_messages": memory["session"],
            "skills": [
                self._summarize_skill(skill)
                for skill in skills
            ],
        }

    def build_skill_execution_context(
        self,
        user_input,
        selected_skill,
        selection,
        memory_context=None,
        rag_results=None,
        workspace_context=None,
    ):
        memory = self.build_memory_context(memory_context=memory_context)

        return {
            "task": "skill_execution",
            "user_input": user_input,
            "workspace": workspace_context or {},
            "memory": memory,
            "recent_messages": memory["session"],
            "selected_skill": selected_skill.to_dict(),
            "selection": selection,
            "rag_results": rag_results or [],
        }

    def build_memory_context(
        self,
        session=None,
        summary="",
        profile=None,
        memory_context=None,
        memory_compressor=None,
        compression_threshold=None,
    ):
        if memory_context is not None:
            return {
                "session": memory_context.get("session", []),
                "summary": memory_context.get("summary", ""),
                "profile": memory_context.get("profile", {}),
            }

        session_messages = session or []
        summary_text = self._maybe_compress_summary(
            session_messages=session_messages,
            summary=summary or "",
            memory_compressor=memory_compressor,
            compression_threshold=compression_threshold,
        )

        return {
            "session": session_messages,
            "summary": summary_text,
            "profile": profile or {},
        }

    def _maybe_compress_summary(
        self,
        session_messages,
        summary,
        memory_compressor=None,
        compression_threshold=None,
    ):
        if memory_compressor is None:
            return summary

        if not compression_threshold or compression_threshold <= 0:
            return summary

        if len(session_messages) < compression_threshold:
            return summary

        return memory_compressor.compress_and_save(session_messages)

    def _summarize_skill(self, skill):
        to_summary = getattr(skill, "to_summary", None)
        if to_summary is not None:
            return to_summary()

        return {
            "name": skill.name,
            "description": skill.description,
            "allowed_tools": skill.allowed_tools,
        }
