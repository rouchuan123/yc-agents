import threading


class RunController:
    def __init__(self, run_id):
        self.run_id = run_id
        self.cancelled = False
        self.paused = False
        self.redirects = []
        self.approvals = {}
        self._condition = threading.Condition()

    def cancel(self):
        with self._condition:
            self.cancelled = True
            self.paused = False
            self._condition.notify_all()

    def pause(self):
        with self._condition:
            self.paused = True

    def resume(self):
        with self._condition:
            self.paused = False
            self._condition.notify_all()

    def redirect(self, content):
        with self._condition:
            self.redirects.append(content)
            self.paused = False
            self._condition.notify_all()

    def pop_redirects(self):
        with self._condition:
            redirects = list(self.redirects)
            self.redirects.clear()
            return redirects

    def wait_if_paused(self):
        with self._condition:
            while self.paused and not self.cancelled:
                self._condition.wait(timeout=0.1)

    def raise_if_cancelled(self, checkpoint):
        if self.cancelled:
            raise RuntimeError(f"Run cancelled at {checkpoint}")

    def record_approval(self, approval_id, decision):
        if decision not in {"allow_once", "allow_for_project", "deny"}:
            raise ValueError(f"Unsupported approval decision: {decision}")
        with self._condition:
            self.approvals[approval_id] = decision
            self._condition.notify_all()

    def wait_for_approval(self, approval_id):
        with self._condition:
            while approval_id not in self.approvals and not self.cancelled:
                self._condition.wait(timeout=0.1)

            self.raise_if_cancelled(f"approval:{approval_id}")
            return self.approvals[approval_id]
