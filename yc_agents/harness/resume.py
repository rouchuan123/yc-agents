from dataclasses import dataclass


@dataclass(frozen=True)
class ResumePoint:
    run_id: str
    status: str
    last_step: str
    user_input: str
    selected_skill: str | None = None
    redirect_instruction: str | None = None

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "status": self.status,
            "last_step": self.last_step,
            "user_input": self.user_input,
            "selected_skill": self.selected_skill,
            "redirect_instruction": self.redirect_instruction,
        }
