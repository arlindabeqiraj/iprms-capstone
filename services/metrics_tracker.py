import time
import mlflow
from models import Metrics
from services.run_manager import save_artifact


class MetricsTracker:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.started_at = time.time()
        self.agents_timing: dict[str, float] = {}
        self.confidence_per_agent: dict[str, float] = {}
        self._agent_start: float = 0.0
        self._current_agent: str = ""
        self.total_line_items = 0
        self.items_auto_approved = 0
        self.items_excepted = 0
        self.items_blocked = 0
        self.extraction_accuracy = 0.0
        self.vendor_match_rate = 0.0
        self.exception_rate = 0.0
        self.confidence_avg = 0.0

    def start_agent(self, agent_name: str) -> None:
        self._current_agent = agent_name
        self._agent_start = time.time()

    def end_agent(self, agent_name: str, confidence: float = None) -> None:
        duration = round((time.time() - self._agent_start) * 1000, 2)
        self.agents_timing[agent_name] = duration

        if confidence is not None:
            self.confidence_per_agent[agent_name] = confidence

    def log_extraction_accuracy(self, accuracy: float) -> None:
        self.extraction_accuracy = accuracy

    def log_vendor_match_rate(self, rate: float) -> None:
        self.vendor_match_rate = rate

    def log_exception_rate(self, rate: float) -> None:
        self.exception_rate = rate

    def log_confidence_avg(self, avg: float) -> None:
        self.confidence_avg = avg

    def finalize(self) -> Metrics:
        total_seconds = round(time.time() - self.started_at, 2)
        throughput = round(3600 / total_seconds, 2) if total_seconds > 0 else 0.0

        metrics = Metrics(
            run_id=self.run_id,
            total_time_seconds=total_seconds,
            extraction_accuracy=self.extraction_accuracy,
            vendor_match_rate=self.vendor_match_rate,
            exception_rate=self.exception_rate,
            confidence_avg=self.confidence_avg,
            confidence_per_agent=self.confidence_per_agent,
            agents_timing=self.agents_timing,
            total_line_items=self.total_line_items,
            items_auto_approved=self.items_auto_approved,
            items_excepted=self.items_excepted,
            items_blocked=self.items_blocked,
            throughput_prs_per_hour=throughput,
        )

        save_artifact(self.run_id, "metrics.json", metrics.model_dump(mode="json"))
        return metrics

    def track_to_mlflow(self, metrics: Metrics) -> None:
        with mlflow.start_run(run_name=self.run_id):
            mlflow.log_metric("extraction_accuracy", metrics.extraction_accuracy)
            mlflow.log_metric("vendor_match_rate", metrics.vendor_match_rate)
            mlflow.log_metric("exception_rate", metrics.exception_rate)
            mlflow.log_metric("confidence_avg", metrics.confidence_avg)
            mlflow.log_metric("total_time_seconds", metrics.total_time_seconds)
            mlflow.log_metric(
                "throughput_prs_per_hour",
                metrics.throughput_prs_per_hour,
            )
            mlflow.log_metric("total_line_items", metrics.total_line_items)
            mlflow.log_metric("items_auto_approved", metrics.items_auto_approved)
            mlflow.log_metric("items_excepted", metrics.items_excepted)
            mlflow.log_metric("items_blocked", metrics.items_blocked)