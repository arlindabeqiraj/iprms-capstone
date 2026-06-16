import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.agent_a_intake import run_intake


RUNS_DIR = Path("runs")


def generate_run_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:6]
    return f"run_{timestamp}_{suffix}"


def ensure_run_dir(run_id: str) -> Path:
    run_path = RUNS_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


class PipelineAuditLogger:
    """
    Minimal pipeline-level audit logger.

    It provides the method names expected by Agent A:
    - log_agent_start()
    - log_agent_end()

    It writes a lightweight pipeline audit file into runs/{run_id}/pipeline_audit_log.md.
    Agent H can still generate the final audit_log.md later.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.run_path = ensure_run_dir(run_id)
        self.events: list[dict[str, Any]] = []

    def log_agent_start(self, agent_name: str, input_summary: str) -> None:
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "agent_name": agent_name,
                "event": "START",
                "summary": input_summary,
            }
        )

    def log_agent_end(self, agent_name: str, output_summary: str) -> None:
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "agent_name": agent_name,
                "event": "END",
                "summary": output_summary,
            }
        )

    def write(self) -> Path:
        path = self.run_path / "pipeline_audit_log.md"

        lines = [
            f"# Pipeline Audit Log — {self.run_id}",
            "",
        ]

        for event in self.events:
            lines.extend(
                [
                    f"## {event['agent_name']} — {event['event']}",
                    "",
                    f"- **Timestamp:** {event['timestamp']}",
                    f"- **Summary:** {event['summary']}",
                    "",
                ]
            )

        path.write_text("\n".join(lines), encoding="utf-8")
        return path


class PipelineMetricsTracker:
    """
    Minimal pipeline-level metrics tracker.

    It provides the method names expected by Agent A:
    - start_agent()
    - end_agent()

    It writes timing data into runs/{run_id}/pipeline_metrics.json.
    Agent H can still generate the final metrics.json later.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.run_path = ensure_run_dir(run_id)
        self.starts: dict[str, float] = {}
        self.timings_ms: dict[str, float] = {}

    def start_agent(self, agent_name: str) -> None:
        self.starts[agent_name] = time.time()

    def end_agent(self, agent_name: str) -> None:
        start_time = self.starts.get(agent_name)

        if start_time is None:
            return

        self.timings_ms[agent_name] = round((time.time() - start_time) * 1000, 2)

    def write(self) -> Path:
        path = self.run_path / "pipeline_metrics.json"

        data = {
            "run_id": self.run_id,
            "agent_timings_ms": self.timings_ms,
            "created_at": datetime.now().isoformat(),
        }

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path


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
            "All agents in the same pipeline run must use the same run_id."
        ),
    )

    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    run_id = args.run_id or generate_run_id()

    ensure_run_dir(run_id)

    audit_logger = PipelineAuditLogger(run_id)
    metrics_tracker = PipelineMetricsTracker(run_id)

    print(f"Processing bundle: {bundle_path}")
    print(f"Shared Run ID: {run_id}")

    context_packet = run_intake(
        bundle_path=bundle_path,
        run_id=run_id,
        audit_logger=audit_logger,
        metrics_tracker=metrics_tracker,
    )

    audit_logger.write()
    metrics_tracker.write()

    print("Agent A completed successfully.")
    print(f"Run ID: {context_packet.run_id}")
    print(f"PR Type: {context_packet.pr_type.value}")
    print(f"Requester: {context_packet.requester}")
    print(f"Department: {context_packet.department}")
    print(f"Cost Center: {context_packet.cost_center}")
    print(f"Total Estimated Value: {context_packet.total_estimated_value}")
    print(f"Risk Score: {context_packet.risk_score}")
    print(f"Risk Flags: {[flag.value for flag in context_packet.risk_flags]}")
    print(f"Output: runs/{context_packet.run_id}/context_packet.json")
    print(f"Pipeline audit: runs/{context_packet.run_id}/pipeline_audit_log.md")
    print(f"Pipeline metrics: runs/{context_packet.run_id}/pipeline_metrics.json")


if __name__ == "__main__":
    main()