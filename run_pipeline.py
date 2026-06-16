import argparse
import importlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from agents.agent_a_intake import run_intake
from agents.agent_b_extraction import run as run_agent_b
from agents.agent_c_budget import run_agent_c
from agents.agent_d_vendor import run as run_agent_d
from agents.agent_h_orchestrator import run_agent_h
from services.file_loader import load_pr_bundle


RUNS_DIR = Path("runs")


def generate_run_id() -> str:
    """
    Generate one shared run_id for the whole pipeline execution.

    This run_id must be passed to all agents so that every agent reads
    and writes artifacts inside the same runs/{run_id}/ directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:6]
    return f"run_{timestamp}_{suffix}"


def ensure_run_dir(run_id: str) -> Path:
    """
    Create and return the shared run directory.
    """
    run_path = RUNS_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def optional_import_callable(
    module_name: str,
    possible_function_names: list[str],
) -> Callable[..., Any] | None:
    """
    Try to import an optional agent function without crashing the pipeline.

    This is useful while Agent E is still being implemented.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None

    for function_name in possible_function_names:
        function = getattr(module, function_name, None)

        if callable(function):
            return function

    return None


class PipelineAuditLogger:
    """
    Lightweight pipeline-level audit logger.

    This logger is intentionally flexible because different agents may call
    logging methods with slightly different signatures.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.run_path = ensure_run_dir(run_id)
        self.events: list[dict[str, Any]] = []
        self.current_agent: str | None = None

    def _normalize_agent_name(self, agent_name: Any = None) -> str:
        if agent_name is None or str(agent_name).strip() == "":
            return self.current_agent or "Unknown Agent"

        return str(agent_name).strip()

    def _normalize_summary(self, value: Any = None, default: str = "") -> str:
        if value is None:
            return default

        return str(value).strip()

    def _add_event(self, agent_name: str, event: str, summary: str) -> None:
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "agent_name": agent_name,
                "event": event,
                "summary": summary,
            }
        )

    def log_agent_start(
        self,
        agent_name: str | None = None,
        input_summary: str | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        input_summary = kwargs.get("input_summary", input_summary)
        input_summary = kwargs.get("summary", input_summary)

        resolved_agent = self._normalize_agent_name(agent_name)
        resolved_summary = self._normalize_summary(
            input_summary,
            "Agent started.",
        )

        self.current_agent = resolved_agent
        self._add_event(resolved_agent, "START", resolved_summary)

    def log_agent_end(
        self,
        agent_name: str | None = None,
        output_summary: str | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        output_summary = kwargs.get("output_summary", output_summary)
        output_summary = kwargs.get("summary", output_summary)

        resolved_agent = self._normalize_agent_name(agent_name)
        resolved_summary = self._normalize_summary(
            output_summary,
            "Agent completed.",
        )

        self._add_event(resolved_agent, "END", resolved_summary)

    def log_agent_skip(
        self,
        agent_name: str | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        reason = kwargs.get("reason", reason)
        reason = kwargs.get("summary", reason)

        resolved_agent = self._normalize_agent_name(agent_name)
        resolved_reason = self._normalize_summary(reason, "Agent skipped.")

        self._add_event(resolved_agent, "SKIPPED", resolved_reason)

    def log_agent_error(
        self,
        agent_name: str | None = None,
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        error = kwargs.get("error", error)
        error = kwargs.get("summary", error)

        resolved_agent = self._normalize_agent_name(agent_name)
        resolved_error = self._normalize_summary(error, "Agent failed.")

        self._add_event(resolved_agent, "ERROR", resolved_error)

    def log_tool_call(
        self,
        tool_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = kwargs.get("tool_name", tool_name)
        resolved_tool = self._normalize_summary(tool_name, "unknown_tool")

        self._add_event("pipeline", "TOOL_CALL", resolved_tool)

    def write(self) -> Path:
        output_path = self.run_path / "pipeline_audit_log.md"

        lines = [
            f"# Pipeline Audit Log - {self.run_id}",
            "",
        ]

        if not self.events:
            lines.append("No pipeline audit events were recorded.")
            lines.append("")

        for event in self.events:
            lines.extend(
                [
                    f"## {event['agent_name']} - {event['event']}",
                    "",
                    f"- Timestamp: {event['timestamp']}",
                    f"- Summary: {event['summary']}",
                    "",
                ]
            )

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path


class PipelineMetricsTracker:
    """
    Lightweight pipeline-level metrics tracker.

    This tracker is intentionally flexible because different agents may call
    timing/metrics methods with slightly different signatures.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.run_path = ensure_run_dir(run_id)
        self.starts: dict[str, float] = {}
        self.timings_ms: dict[str, float] = {}
        self.confidence_scores: dict[str, float] = {}
        self.exception_rates: dict[str, float] = {}
        self.confidence_avg: float | None = None
        self.skipped_agents: list[str] = []
        self.current_agent: str | None = None

    def _normalize_agent_name(self, agent_name: Any = None) -> str:
        if agent_name is None or str(agent_name).strip() == "":
            return self.current_agent or "Unknown Agent"

        return str(agent_name).strip()

    def start_agent(
        self,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        resolved_agent = self._normalize_agent_name(agent_name)

        self.current_agent = resolved_agent
        self.starts[resolved_agent] = time.time()

    def end_agent(
        self,
        agent_name: str | None = None,
        confidence: float = 1.0,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        confidence = kwargs.get("confidence", confidence)

        resolved_agent = self._normalize_agent_name(agent_name)
        start_time = self.starts.get(resolved_agent)

        if start_time is not None:
            self.timings_ms[resolved_agent] = round(
                (time.time() - start_time) * 1000,
                2,
            )

        try:
            self.confidence_scores[resolved_agent] = float(confidence)
        except (TypeError, ValueError):
            self.confidence_scores[resolved_agent] = 1.0

    def skip_agent(
        self,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = kwargs.get("agent_name", agent_name)
        resolved_agent = self._normalize_agent_name(agent_name)

        if resolved_agent not in self.skipped_agents:
            self.skipped_agents.append(resolved_agent)

    def log_exception_rate(
        self,
        rate: float | None = None,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        rate = kwargs.get("rate", rate)
        agent_name = kwargs.get("agent_name", agent_name)
        resolved_agent = self._normalize_agent_name(agent_name)

        try:
            numeric_rate = float(rate)
        except (TypeError, ValueError):
            numeric_rate = 0.0

        self.exception_rates[resolved_agent] = max(0.0, min(numeric_rate, 1.0))

    def log_confidence_avg(
        self,
        confidence_avg: float | None = None,
        **kwargs: Any,
    ) -> None:
        confidence_avg = kwargs.get("avg", confidence_avg)
        confidence_avg = kwargs.get("confidence_avg", confidence_avg)

        try:
            self.confidence_avg = float(confidence_avg)
        except (TypeError, ValueError):
            self.confidence_avg = None

    def write(self) -> Path:
        output_path = self.run_path / "pipeline_metrics.json"

        data = {
            "run_id": self.run_id,
            "agent_timings_ms": self.timings_ms,
            "confidence_scores": self.confidence_scores,
            "exception_rates": self.exception_rates,
            "confidence_avg": self.confidence_avg,
            "skipped_agents": self.skipped_agents,
            "created_at": datetime.now().isoformat(),
        }

        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return output_path


def require_state_success(state: dict[str, Any], agent_name: str) -> None:
    """
    Validate state returned by state-based agents.
    """
    if not isinstance(state, dict):
        raise RuntimeError(f"{agent_name} failed: returned state is not a dictionary")

    if state.get("error"):
        raise RuntimeError(f"{agent_name} failed: {state['error']}")


def run_optional_agent_e(
    run_id: str,
    bundle_data: dict[str, Any],
    audit_logger: PipelineAuditLogger,
    metrics_tracker: PipelineMetricsTracker,
) -> Any | None:
    """
    Run Agent E only if it exists.

    Supported function names:
    - run_agent_e
    - run
    - run_policy
    - run_compliance

    If Agent E is not ready yet, the pipeline does not fail.
    Agent H can work without policy artifact because policy is optional.
    """
    agent_name = "Agent E"

    run_agent_e = optional_import_callable(
        module_name="agents.agent_e_policy",
        possible_function_names=[
            "run_agent_e",
            "run",
            "run_policy",
            "run_compliance",
        ],
    )

    if run_agent_e is None:
        reason = (
            "Agent E was skipped because no supported callable was found in "
            "agents.agent_e_policy. Expected one of: run_agent_e, run, "
            "run_policy, run_compliance."
        )
        print(f"SKIP Agent E - {reason}")
        audit_logger.log_agent_skip(agent_name, reason)
        metrics_tracker.skip_agent(agent_name)
        return None

    print("Running Agent E - Compliance and Policy...")
    audit_logger.log_agent_start(
        agent_name,
        "Starting Agent E compliance and policy checks.",
    )
    metrics_tracker.start_agent(agent_name)

    try:
        compliance = run_agent_e(
            run_id=run_id,
            bundle_data=bundle_data,
            audit_logger=audit_logger,
            metrics_tracker=metrics_tracker,
        )

        audit_logger.log_agent_end(agent_name, "Agent E completed successfully.")
        metrics_tracker.end_agent(agent_name)

        print("OK Agent E completed")
        return compliance

    except TypeError:
        state = run_agent_e(
            {
                "run_id": run_id,
                "bundle_data": bundle_data,
            }
        )

        if isinstance(state, dict) and state.get("error"):
            raise RuntimeError(f"Agent E failed: {state['error']}")

        audit_logger.log_agent_end(
            agent_name,
            "Agent E completed successfully using state input.",
        )
        metrics_tracker.end_agent(agent_name)

        print("OK Agent E completed")
        return state


def run_pipeline(
    bundle_path: str | Path,
    run_id: str | None = None,
    use_llm: bool = False,
    llm_provider: str = "groq",
    llm_model: str | None = None,
    require_policy: bool = False,
) -> dict[str, Any]:
    """
    Run the IPRMS pipeline.

    Implemented agents:
    - Agent A: Intake and Context       -> context_packet.json
    - Agent B: Item Extraction          -> extracted_pr.json
    - Agent C: Budget Validation        -> budget_check.json
    - Agent D: Vendor Matching          -> vendor_match.json
    - Agent E: Compliance and Policy    -> optional
    - Agent H: Final orchestration      -> exceptions.md, approval_packet.json,
      po_draft.json, audit_log.md, audit_log.json, metrics.json
    """
    bundle_path = Path(bundle_path)

    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle folder not found: {bundle_path}")

    shared_run_id = run_id or generate_run_id()
    run_path = ensure_run_dir(shared_run_id)

    audit_logger = PipelineAuditLogger(shared_run_id)
    metrics_tracker = PipelineMetricsTracker(shared_run_id)

    bundle_data = load_pr_bundle(bundle_path)

    print("")
    print("=" * 60)
    print("IPRMS Pipeline Starting")
    print(f"Bundle : {bundle_path}")
    print(f"Run ID : {shared_run_id}")
    print("=" * 60)
    print("")

    print("Running Agent A - Intake and Classification...")
    context_packet = run_intake(
        bundle_path=bundle_path,
        run_id=shared_run_id,
        audit_logger=audit_logger,
        metrics_tracker=metrics_tracker,
    )
    print(f"OK Agent A completed - PR Type: {context_packet.pr_type.value}")

    print("Running Agent B - Item Extraction...")
    state = run_agent_b(
        {
            "run_id": shared_run_id,
            "bundle_path": str(bundle_path),
            "audit_logger": audit_logger,
            "metrics_tracker": metrics_tracker,
        }
    )
    require_state_success(state, "Agent B")
    print("OK Agent B completed - extracted_pr.json written")

    print("Running Agent C - Budget Validation...")
    budget_check = run_agent_c(
        run_id=shared_run_id,
        bundle_data=bundle_data,
        audit_logger=audit_logger,
        metrics_tracker=metrics_tracker,
    )

    budget_status = getattr(
        budget_check.overall_status,
        "value",
        budget_check.overall_status,
    )
    print(f"OK Agent C completed - budget status: {budget_status}")

    print("Running Agent D - Vendor Matching...")
    state["audit_logger"] = audit_logger
    state["metrics_tracker"] = metrics_tracker
    state = run_agent_d(state)
    require_state_success(state, "Agent D")
    print("OK Agent D completed - vendor_match.json written")

    compliance = run_optional_agent_e(
        run_id=shared_run_id,
        bundle_data=bundle_data,
        audit_logger=audit_logger,
        metrics_tracker=metrics_tracker,
    )

    print("Running Agent H - Final Orchestration...")
    agent_h_result = run_agent_h(
        run_id=shared_run_id,
        bundle_path=str(bundle_path),
        require_policy=require_policy,
        use_llm=use_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
        audit_logger=audit_logger,
        metrics_tracker=metrics_tracker,
    )
    print(f"OK Agent H completed - decision: {agent_h_result['decision']}")

    audit_path = audit_logger.write()
    metrics_path = metrics_tracker.write()

    print("")
    print("=" * 60)
    print("IPRMS Pipeline Completed")
    print(f"Run ID: {shared_run_id}")
    print("=" * 60)
    print("Artifacts:")
    print("  context_packet.json      -> Agent A")
    print("  extracted_pr.json        -> Agent B")
    print("  budget_check.json        -> Agent C")
    print("  vendor_match.json        -> Agent D")

    if compliance is not None:
        print("  policy/compliance artifact -> Agent E")
    else:
        print("  Agent E skipped - policy artifact not produced")

    print("  exceptions.md            -> Agent H")
    print("  approval_packet.json     -> Agent H")
    print("  po_draft.json            -> Agent H")
    print("  audit_log.md             -> Agent H")
    print("  audit_log.json           -> Agent H")
    print("  metrics.json             -> Agent H")
    print("  pipeline_audit_log.md    -> Pipeline")
    print("  pipeline_metrics.json    -> Pipeline")
    print("=" * 60)
    print("")

    result: dict[str, Any] = {
        "run_id": shared_run_id,
        "bundle_path": str(bundle_path),
        "run_path": str(run_path),
        "context_packet": context_packet,
        "budget_check": budget_check,
        "compliance": compliance,
        "agent_h_result": agent_h_result,
        "context_packet_path": str(run_path / "context_packet.json"),
        "extracted_pr_path": str(run_path / "extracted_pr.json"),
        "budget_check_path": str(run_path / "budget_check.json"),
        "vendor_match_path": str(run_path / "vendor_match.json"),
        "exceptions_path": str(run_path / "exceptions.md"),
        "approval_packet_path": str(run_path / "approval_packet.json"),
        "po_draft_path": str(run_path / "po_draft.json"),
        "audit_log_md_path": str(run_path / "audit_log.md"),
        "audit_log_json_path": str(run_path / "audit_log.json"),
        "metrics_path": str(run_path / "metrics.json"),
        "pipeline_audit_path": str(audit_path),
        "pipeline_metrics_path": str(metrics_path),
    }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run IPRMS procurement pipeline"
    )

    parser.add_argument(
        "--bundle",
        required=True,
        help="Path to PR bundle folder",
    )

    parser.add_argument(
        "--run-id",
        required=False,
        default=None,
        help=(
            "Optional shared run ID. If omitted, run_pipeline.py generates one. "
            "All agents must use the same run_id."
        ),
    )

    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use Agent H optional LLM explanation layer.",
    )

    parser.add_argument(
        "--llm-provider",
        default="groq",
        choices=["groq", "gemini"],
        help="LLM provider used by Agent H.",
    )

    parser.add_argument(
        "--llm-model",
        default=None,
        help="Optional LLM model name used by Agent H.",
    )

    parser.add_argument(
        "--require-policy",
        action="store_true",
        help=(
            "Require Agent E policy artifact before Agent H. "
            "Do not use this until Agent E is implemented."
        ),
    )

    args = parser.parse_args()

    result = run_pipeline(
        bundle_path=args.bundle,
        run_id=args.run_id,
        use_llm=args.use_llm,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        require_policy=args.require_policy,
    )

    context_packet = result["context_packet"]
    budget_check = result["budget_check"]
    compliance = result["compliance"]
    agent_h_result = result["agent_h_result"]

    budget_status = getattr(
        budget_check.overall_status,
        "value",
        budget_check.overall_status,
    )

    print("Summary:")
    print(f"PR Type     : {context_packet.pr_type.value}")
    print(f"Requester   : {context_packet.requester}")
    print(f"Department  : {context_packet.department}")
    print(f"Cost Center : {context_packet.cost_center}")
    print(f"Total Value : {context_packet.total_estimated_value}")
    print(f"Risk Score  : {context_packet.risk_score}")
    print(f"Risk Flags  : {[flag.value for flag in context_packet.risk_flags]}")
    print(f"Budget      : {budget_status}")

    if compliance is None:
        print("Compliance  : SKIPPED")
    else:
        compliance_status = getattr(
            compliance.overall_compliance,
            "value",
            compliance.overall_compliance,
        )
        findings = getattr(compliance, "findings", [])
        print(f"Compliance  : {compliance_status}")
        print(f"Findings    : {len(findings)}")

    print(f"Decision    : {agent_h_result['decision']}")
    print(f"LLM used    : {agent_h_result['llm_used']}")
    print(f"H Findings  : {agent_h_result['total_findings']}")


if __name__ == "__main__":
    main()