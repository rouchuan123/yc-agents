class RunController:
    def __init__(self, run_id):
        self.run_id = run_id
        self.cancelled = False
        self.paused = False
        self.redirects = []
        self.approvals = {}

    def cancel(self):
        self.cancelled = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def redirect(self, content):
        self.redirects.append(content)

    def pop_redirects(self):
        redirects = list(self.redirects)
        self.redirects.clear()
        return redirects

    def record_approval(self, approval_id, decision):
        if decision not in {"allow_once", "allow_for_project", "deny"}:
            raise ValueError(f"Unsupported approval decision: {decision}")
        self.approvals[approval_id] = decision
