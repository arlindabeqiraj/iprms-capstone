import time
from datetime import datetime
from models import AuditStep, AuditLog, Decision
from services.run_manager import save_artifact


class AuditLogger:

    def __init__(self, run_id: str, bundle_path: str):
        self.run_id       = run_id
        self.bundle_path  = bundle_path
        self.steps:       list[AuditStep] = []
        self.started_at   = datetime.now()
        self._step_start: float = 0.0
        self._current_agent: str = ''
        self._current_input: str = ''
        self._current_tools: list[str] = []

    def log_agent_start(self, agent_name: str, input_summary: str) -> None:
        self._step_start    = time.time()
        self._current_agent = agent_name
        self._current_input = input_summary
        self._current_tools = []

    def log_tool_call(self, tool_name: str) -> None:
        self._current_tools.append(tool_name)

    def log_agent_end(
        self,
        output_summary: str,
        decision: str = None
    ) -> None:
        duration_ms = round((time.time() - self._step_start) * 1000, 2)
        step = AuditStep(
            timestamp      = datetime.now(),
            agent_name     = self._current_agent,
            action         = f'{self._current_agent} completed',
            input_summary  = self._current_input,
            output_summary = output_summary,
            tools_called   = self._current_tools.copy(),
            decision       = decision,
            duration_ms    = duration_ms
        )
        self.steps.append(step)
        self._current_tools = []

    def build_audit_log(self, final_decision: Decision) -> AuditLog:
        return AuditLog(
            run_id         = self.run_id,
            bundle_path    = self.bundle_path,
            started_at     = self.started_at,
            completed_at   = datetime.now(),
            final_decision = final_decision,
            steps          = self.steps
        )

    def save(self, final_decision: Decision) -> AuditLog:
        audit_log = self.build_audit_log(final_decision)
        save_artifact(
            self.run_id,
            'audit_log.json',
            audit_log.model_dump(mode='json')
        )
        return audit_log