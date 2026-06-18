from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from models.anomaly_models import (
    AnomalyCheck,
    AnomalyGroup,
    AnomalyStatus,
    AnomalyType,
)
from models.shared_models import EvidencePointer, Finding, Severity


RUNS_DIR = Path("runs")
AGENT_NAME = "Agent G"

OUTPUT_JSON = "anomaly_check.json"
OUTPUT_MD = "split_order_anomalies.md"

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_SPLIT_ORDER_THRESHOLD = 5000.0
LOW_CONFIDENCE_THRESHOLD = 0.70

VAGUE_ITEM_WORDS = {
    "item",
    "items",
    "equipment",
    "service",
    "services",
    "misc",
    "miscellaneous",
    "other",
    "hardware",
    "software",
    "supplies",
}


def _stable_id(prefix: str, key: str) -> str:
    """
    Build deterministic finding IDs.

    Python hash() is not stable between sessions because of PYTHONHASHSEED.
    For audit trail and idempotency we need stable IDs.
    """
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _run_dir(run_id: str) -> Path:
    path = RUNS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(run_id: str, filename: str, data: dict[str, Any]) -> Path:
    path = _run_dir(run_id) / filename
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path


def _write_markdown(run_id: str, filename: str, content: str) -> Path:
    path = _run_dir(run_id) / filename
    path.write_text(content, encoding="utf-8")
    return path


def _safe_audit_start(
    audit_logger: Any,
    agent_name: str,
    input_summary: str,
) -> None:
    if audit_logger is None or not hasattr(audit_logger, "log_agent_start"):
        return

    try:
        audit_logger.log_agent_start(
            agent_name=agent_name,
            input_summary=input_summary,
        )
    except TypeError:
        try:
            audit_logger.log_agent_start(agent_name, input_summary)
        except TypeError:
            audit_logger.log_agent_start(input_summary=input_summary)


def _safe_audit_end(
    audit_logger: Any,
    agent_name: str,
    output_summary: str,
) -> None:
    if audit_logger is None or not hasattr(audit_logger, "log_agent_end"):
        return

    try:
        audit_logger.log_agent_end(
            agent_name=agent_name,
            output_summary=output_summary,
        )
    except TypeError:
        try:
            audit_logger.log_agent_end(agent_name, output_summary)
        except TypeError:
            audit_logger.log_agent_end(output_summary=output_summary)


def _safe_audit_error(
    audit_logger: Any,
    agent_name: str,
    error: str,
) -> None:
    if audit_logger is None or not hasattr(audit_logger, "log_agent_error"):
        return

    try:
        audit_logger.log_agent_error(agent_name=agent_name, error=error)
    except TypeError:
        try:
            audit_logger.log_agent_error(agent_name, error)
        except TypeError:
            audit_logger.log_agent_error(error=error)


def _safe_metrics_start(metrics_tracker: Any, agent_name: str) -> None:
    if metrics_tracker is None or not hasattr(metrics_tracker, "start_agent"):
        return

    try:
        metrics_tracker.start_agent(agent_name=agent_name)
    except TypeError:
        metrics_tracker.start_agent(agent_name)


def _safe_metrics_end(
    metrics_tracker: Any,
    agent_name: str,
    confidence: float = 1.0,
) -> None:
    if metrics_tracker is None or not hasattr(metrics_tracker, "end_agent"):
        return

    try:
        metrics_tracker.end_agent(agent_name=agent_name, confidence=confidence)
    except TypeError:
        try:
            metrics_tracker.end_agent(agent_name, confidence)
        except TypeError:
            metrics_tracker.end_agent(agent_name)


def _safe_string(value: Any, default: str = "") -> str:
    if value is None:
        return default

    text = str(value).strip()
    return text if text else default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default

        return int(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return data if isinstance(data, dict) else {}


def _load_manifest(bundle_path: Path) -> dict[str, Any]:
    manifest_path = bundle_path / "manifest.yaml"

    if not manifest_path.exists():
        return {}

    return _read_yaml_if_exists(manifest_path)


def _load_requisition(
    bundle_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    requisition_file = _safe_string(
        manifest.get("requisition_file"),
        "requisition.json",
    )
    requisition_path = bundle_path / requisition_file

    if not requisition_path.exists():
        raise FileNotFoundError(f"Requisition file not found: {requisition_path}")

    return _read_json(requisition_path)


def _load_policy(bundle_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    policy_file = _safe_string(manifest.get("policy_file"), "approval_policy.yaml")
    return _read_yaml_if_exists(bundle_path / policy_file)


def _header(requisition: dict[str, Any]) -> dict[str, Any]:
    header = requisition.get("header")
    return header if isinstance(header, dict) else {}


def _field(
    requisition: dict[str, Any],
    name: str,
    default: str = "",
) -> str:
    if requisition.get(name) not in (None, ""):
        return _safe_string(requisition.get(name), default)

    header = _header(requisition)
    return _safe_string(header.get(name), default)


def _request_date(requisition: dict[str, Any]) -> datetime | None:
    raw_value = _field(requisition, "request_date")

    if not raw_value:
        return None

    normalized = raw_value.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _line_items(requisition: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["line_items", "items"]:
        value = requisition.get(key)

        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def _item_name(item: dict[str, Any]) -> str:
    return _safe_string(
        item.get("item_name")
        or item.get("description")
        or item.get("name"),
        "UNKNOWN_ITEM",
    )


def _item_key(name: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else " "
        for character in name
    )
    return " ".join(cleaned.split())


def _item_total(item: dict[str, Any]) -> float:
    if item.get("total_price") not in (None, ""):
        return _to_float(item.get("total_price"))

    if item.get("total_value") not in (None, ""):
        return _to_float(item.get("total_value"))

    quantity = _to_float(item.get("quantity"), 1.0)
    unit_price = _to_float(item.get("unit_price"), 0.0)

    return quantity * unit_price


def _item_confidence(item: dict[str, Any]) -> float:
    return _to_float(item.get("confidence"), 1.0)


def _evidence_for_item(source_file: str, index: int) -> EvidencePointer:
    return EvidencePointer(
        source_file=source_file,
        page_number=1,
        field_name=f"line_items[{index}]",
        bounding_box=None,
    )


def _policy_threshold(policy: dict[str, Any]) -> float:
    if policy.get("split_order_threshold") not in (None, ""):
        return _to_float(
            policy.get("split_order_threshold"),
            DEFAULT_SPLIT_ORDER_THRESHOLD,
        )

    sourcing_rules = policy.get("sourcing_rules")

    if isinstance(sourcing_rules, dict):
        for key in [
            "bid_required_above",
            "competitive_bid_threshold",
            "minimum_bid_threshold",
        ]:
            if sourcing_rules.get(key) not in (None, ""):
                return _to_float(
                    sourcing_rules.get(key),
                    DEFAULT_SPLIT_ORDER_THRESHOLD,
                )

    approval_thresholds = policy.get("approval_thresholds")

    if isinstance(approval_thresholds, dict):
        high_value = approval_thresholds.get("high_value")

        if (
            isinstance(high_value, dict)
            and high_value.get("min_amount") not in (None, "")
        ):
            return _to_float(
                high_value.get("min_amount"),
                DEFAULT_SPLIT_ORDER_THRESHOLD,
            )

    return DEFAULT_SPLIT_ORDER_THRESHOLD


def _is_vague_description(item_name: str) -> bool:
    key = _item_key(item_name)
    tokens = key.split()

    if not tokens:
        return True

    if len(tokens) <= 1:
        return True

    if len(tokens) <= 2 and any(token in VAGUE_ITEM_WORDS for token in tokens):
        return True

    return key in VAGUE_ITEM_WORDS


def _bundle_id(
    bundle_path: Path,
    manifest: dict[str, Any],
    requisition: dict[str, Any],
) -> str:
    return _safe_string(
        manifest.get("bundle_id")
        or requisition.get("bundle_id")
        or bundle_path.name,
        bundle_path.name,
    )


def _pr_id(requisition: dict[str, Any]) -> str:
    return _safe_string(
        requisition.get("pr_id")
        or requisition.get("pr_number")
        or _header(requisition).get("pr_number"),
        "UNKNOWN_PR",
    )


def _scan_peer_bundles(
    current_bundle_path: Path,
    examples_root: Path,
) -> list[dict[str, Any]]:
    peer_records: list[dict[str, Any]] = []

    if not examples_root.exists():
        return peer_records

    for candidate_path in sorted(examples_root.iterdir()):
        if not candidate_path.is_dir():
            continue

        if candidate_path.resolve() == current_bundle_path.resolve():
            continue

        requisition_path = candidate_path / "requisition.json"

        if not requisition_path.exists():
            continue

        try:
            manifest = _load_manifest(candidate_path)
            requisition = _load_requisition(candidate_path, manifest)
        except Exception:
            continue

        peer_records.append(
            {
                "bundle_path": candidate_path,
                "bundle_id": _bundle_id(candidate_path, manifest, requisition),
                "pr_id": _pr_id(requisition),
                "department": _field(
                    requisition,
                    "department",
                    "UNKNOWN_DEPARTMENT",
                ),
                "cost_center": _field(requisition, "cost_center", "UNKNOWN_CC"),
                "request_date": _request_date(requisition),
                "items": _line_items(requisition),
            }
        )

    return peer_records


def _within_window(
    current_date: datetime | None,
    peer_date: datetime | None,
    lookback_days: int,
) -> bool:
    if current_date is None or peer_date is None:
        return False

    delta = abs(current_date - peer_date)
    return delta <= timedelta(days=lookback_days)


def _finding(
    finding_id: str,
    severity: Severity,
    confidence: float,
    description: str,
    recommended_action: str,
    evidence: list[EvidencePointer],
) -> Finding:
    return Finding(
        finding_id=finding_id,
        agent_source=AGENT_NAME,
        severity=severity,
        confidence=max(0.0, min(confidence, 1.0)),
        confidence_explanation="Deterministic anomaly rule applied by Agent G.",
        description=description,
        evidence_pointers=evidence,
        recommended_action=recommended_action,
    )


def _status_from_findings(findings: list[Finding]) -> AnomalyStatus:
    severities = {finding.severity for finding in findings}

    if Severity.BLOCK in severities:
        return AnomalyStatus.BLOCK

    if Severity.EXCEPTION in severities:
        return AnomalyStatus.EXCEPTION

    if Severity.WARNING in severities:
        return AnomalyStatus.WARNING

    return AnomalyStatus.CLEAR


def _score_from_findings(findings: list[Finding]) -> float:
    weights = {
        Severity.BLOCK: 0.60,
        Severity.EXCEPTION: 0.40,
        Severity.WARNING: 0.20,
    }

    score = sum(weights.get(finding.severity, 0.10) for finding in findings)

    return min(round(score, 2), 1.0)


def _detect_within_pr_split_order(
    requisition: dict[str, Any],
    source_file: str,
    threshold: float,
) -> tuple[list[AnomalyGroup], list[Finding]]:
    groups: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(_line_items(requisition)):
        name = _item_name(item)
        key = _item_key(name)

        if not key:
            continue

        group = groups.setdefault(
            key,
            {
                "count": 0,
                "total": 0.0,
                "evidence": [],
                "display_name": name,
            },
        )
        group["count"] += 1
        group["total"] += _item_total(item)
        group["evidence"].append(_evidence_for_item(source_file, index))

    anomaly_groups: list[AnomalyGroup] = []
    findings: list[Finding] = []

    for key, group in groups.items():
        if group["count"] < 2:
            continue

        severity = (
            Severity.EXCEPTION
            if group["total"] >= threshold
            else Severity.WARNING
        )

        explanation = (
            f"Same item '{group['display_name']}' appears {group['count']} times "
            f"inside the same requisition. "
            f"Cumulative value: {group['total']:.2f}."
        )

        anomaly_groups.append(
            AnomalyGroup(
                anomaly_type=AnomalyType.SPLIT_ORDER_WITHIN_PR,
                item_key=key,
                department=_field(requisition, "department", "UNKNOWN_DEPARTMENT"),
                cost_center=_field(requisition, "cost_center", "UNKNOWN_CC"),
                occurrence_count=group["count"],
                cumulative_value=round(group["total"], 2),
                involved_pr_ids=[_pr_id(requisition)],
                involved_bundles=[],
                severity=severity.value,
                explanation=explanation,
            )
        )

        findings.append(
            _finding(
                finding_id=_stable_id("AGENT-G-SPLIT-WITHIN", key),
                severity=severity,
                confidence=0.92,
                description=explanation,
                recommended_action=(
                    "Review whether the PR was split to avoid bid or approval thresholds."
                ),
                evidence=group["evidence"],
            )
        )

    return anomaly_groups, findings


def _detect_cross_bundle_split_order(
    current_bundle_path: Path,
    requisition: dict[str, Any],
    source_file: str,
    threshold: float,
    lookback_days: int,
    examples_root: Path,
) -> tuple[list[AnomalyGroup], list[Finding], list[str]]:
    current_department = _field(
        requisition,
        "department",
        "UNKNOWN_DEPARTMENT",
    )
    current_cost_center = _field(requisition, "cost_center", "UNKNOWN_CC")
    current_date = _request_date(requisition)
    current_pr_id = _pr_id(requisition)

    scanned_bundles: list[str] = []
    records_by_item: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(_line_items(requisition)):
        key = _item_key(_item_name(item))

        if not key:
            continue

        records_by_item.setdefault(
            key,
            {
                "total": 0.0,
                "count": 0,
                "pr_ids": set(),
                "bundles": set(),
                "evidence": [],
            },
        )

        records_by_item[key]["total"] += _item_total(item)
        records_by_item[key]["count"] += 1
        records_by_item[key]["pr_ids"].add(current_pr_id)
        records_by_item[key]["bundles"].add(current_bundle_path.name)
        records_by_item[key]["evidence"].append(_evidence_for_item(source_file, index))

    for peer in _scan_peer_bundles(current_bundle_path, examples_root):
        scanned_bundles.append(str(peer["bundle_id"]))

        if peer["department"] != current_department:
            continue

        if peer["cost_center"] != current_cost_center:
            continue

        if not _within_window(current_date, peer["request_date"], lookback_days):
            continue

        for item in peer["items"]:
            key = _item_key(_item_name(item))

            if key not in records_by_item:
                continue

            records_by_item[key]["total"] += _item_total(item)
            records_by_item[key]["count"] += 1
            records_by_item[key]["pr_ids"].add(peer["pr_id"])
            records_by_item[key]["bundles"].add(peer["bundle_id"])

    anomaly_groups: list[AnomalyGroup] = []
    findings: list[Finding] = []

    for key, record in records_by_item.items():
        if len(record["pr_ids"]) < 2:
            continue

        if record["total"] < threshold:
            continue

        explanation = (
            f"Potential split-order pattern: same item '{key}' appears across "
            f"{len(record['pr_ids'])} PRs in department {current_department} "
            f"and cost center {current_cost_center} within {lookback_days} days. "
            f"Cumulative value {record['total']:.2f} reaches or exceeds "
            f"threshold {threshold:.2f}."
        )

        anomaly_groups.append(
            AnomalyGroup(
                anomaly_type=AnomalyType.SPLIT_ORDER_CROSS_BUNDLE,
                item_key=key,
                department=current_department,
                cost_center=current_cost_center,
                occurrence_count=record["count"],
                cumulative_value=round(record["total"], 2),
                involved_pr_ids=sorted(record["pr_ids"]),
                involved_bundles=sorted(record["bundles"]),
                severity=Severity.EXCEPTION.value,
                explanation=explanation,
            )
        )

        findings.append(
            _finding(
                finding_id=_stable_id("AGENT-G-SPLIT-CROSS", key),
                severity=Severity.EXCEPTION,
                confidence=0.90,
                description=explanation,
                recommended_action=(
                    "Route to procurement/compliance for split-order review "
                    "before PO creation."
                ),
                evidence=record["evidence"],
            )
        )

    return anomaly_groups, findings, scanned_bundles


def _detect_quality_anomalies(
    requisition: dict[str, Any],
    source_file: str,
) -> tuple[list[AnomalyGroup], list[Finding]]:
    anomaly_groups: list[AnomalyGroup] = []
    findings: list[Finding] = []

    for index, item in enumerate(_line_items(requisition)):
        name = _item_name(item)
        key = _item_key(name)
        confidence = _item_confidence(item)
        evidence = [_evidence_for_item(source_file, index)]

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            description = (
                f"Line item '{name}' has low extraction confidence "
                f"{confidence:.2f}."
            )

            anomaly_groups.append(
                AnomalyGroup(
                    anomaly_type=AnomalyType.LOW_CONFIDENCE_EXTRACTION,
                    item_key=key,
                    department=_field(
                        requisition,
                        "department",
                        "UNKNOWN_DEPARTMENT",
                    ),
                    cost_center=_field(requisition, "cost_center", "UNKNOWN_CC"),
                    occurrence_count=1,
                    cumulative_value=round(_item_total(item), 2),
                    involved_pr_ids=[_pr_id(requisition)],
                    involved_bundles=[],
                    severity=Severity.WARNING.value,
                    explanation=description,
                )
            )

            findings.append(
                _finding(
                    finding_id=f"AGENT-G-LOW-CONFIDENCE-{index + 1}",
                    severity=Severity.WARNING,
                    confidence=0.88,
                    description=description,
                    recommended_action=(
                        "Route to buyer clarification or manual extraction review."
                    ),
                    evidence=evidence,
                )
            )

        if _is_vague_description(name):
            description = (
                f"Line item description '{name}' is too vague for reliable "
                f"pricing or matching."
            )

            anomaly_groups.append(
                AnomalyGroup(
                    anomaly_type=AnomalyType.VAGUE_ITEM_DESCRIPTION,
                    item_key=key,
                    department=_field(
                        requisition,
                        "department",
                        "UNKNOWN_DEPARTMENT",
                    ),
                    cost_center=_field(requisition, "cost_center", "UNKNOWN_CC"),
                    occurrence_count=1,
                    cumulative_value=round(_item_total(item), 2),
                    involved_pr_ids=[_pr_id(requisition)],
                    involved_bundles=[],
                    severity=Severity.WARNING.value,
                    explanation=description,
                )
            )

            findings.append(
                _finding(
                    finding_id=f"AGENT-G-VAGUE-DESCRIPTION-{index + 1}",
                    severity=Severity.WARNING,
                    confidence=0.84,
                    description=description,
                    recommended_action=(
                        "Ask requester or buyer to provide a clearer item specification."
                    ),
                    evidence=evidence,
                )
            )

    return anomaly_groups, findings


def _markdown_report(check: AnomalyCheck) -> str:
    lines = [
        f"# Split-Order and Anomaly Report - {check.run_id}",
        "",
        f"Overall status: {check.overall_status.value}",
        f"Split-order detected: {check.split_order_detected}",
        f"Anomaly score: {check.anomaly_score}",
        f"Total findings: {len(check.findings)}",
        "",
        "## Rules applied",
        "",
    ]

    for rule in check.rules_applied:
        lines.append(f"- {rule}")

    lines.extend(["", "## Findings", ""])

    if not check.findings:
        lines.append("No split-order or anomaly findings detected.")
        lines.append("")

    for finding in check.findings:
        lines.extend(
            [
                f"### [{finding.severity.value}] {finding.finding_id}",
                "",
                f"- Description: {finding.description}",
                f"- Recommended action: {finding.recommended_action}",
                f"- Confidence: {finding.confidence}",
            ]
        )

        if finding.evidence_pointers:
            lines.append("- Evidence:")

            for evidence in finding.evidence_pointers:
                lines.append(
                    f"  - {evidence.source_file} -> {evidence.field_name} "
                    f"(page {evidence.page_number})"
                )

        lines.append("")

    lines.extend(["", "## Anomaly groups", ""])

    if not check.anomaly_groups:
        lines.append("No anomaly groups detected.")
        lines.append("")

    for group in check.anomaly_groups:
        lines.extend(
            [
                f"### {group.anomaly_type.value} - {group.item_key}",
                "",
                f"- Department: {group.department}",
                f"- Cost center: {group.cost_center or 'N/A'}",
                f"- Occurrence count: {group.occurrence_count}",
                f"- Cumulative value: {group.cumulative_value}",
                f"- Severity: {group.severity}",
                f"- Explanation: {group.explanation}",
            ]
        )

        if group.involved_pr_ids:
            lines.append(f"- Involved PRs: {', '.join(group.involved_pr_ids)}")

        if group.involved_bundles:
            lines.append(f"- Involved bundles: {', '.join(group.involved_bundles)}")

        lines.append("")

    return "\n".join(lines)


def run_agent_g(
    run_id: str,
    bundle_path: str | Path,
    audit_logger: Any = None,
    metrics_tracker: Any = None,
    examples_root: str | Path | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> AnomalyCheck:
    """
    Agent G - Split-order and anomaly detection.

    This agent is deterministic and rule-based.
    It does not use LLM because split-order detection must be reproducible
    and audit-ready.

    Important:
    - Cross-bundle scan is disabled by default.
    - Cross-bundle scan runs only when examples_root is explicitly provided.
    - This prevents clean demo bundles from being compared against unrelated
      synthetic examples in the examples/ directory.
    """
    bundle_path = Path(bundle_path)

    enable_cross_bundle_scan = examples_root is not None
    examples_root_path = Path(examples_root) if examples_root is not None else None

    _safe_audit_start(
        audit_logger,
        AGENT_NAME,
        f"Starting split-order/anomaly detection for bundle_path={bundle_path}",
    )
    _safe_metrics_start(metrics_tracker, AGENT_NAME)

    try:
        manifest = _load_manifest(bundle_path)
        requisition = _load_requisition(bundle_path, manifest)
        policy = _load_policy(bundle_path, manifest)

        threshold = _policy_threshold(policy)
        source_file = _safe_string(
            manifest.get("requisition_file"),
            "requisition.json",
        )

        groups_within, findings_within = _detect_within_pr_split_order(
            requisition=requisition,
            source_file=source_file,
            threshold=threshold,
        )

        groups_cross: list[AnomalyGroup] = []
        findings_cross: list[Finding] = []
        scanned_bundles: list[str] = []

        if enable_cross_bundle_scan and examples_root_path is not None:
            groups_cross, findings_cross, scanned_bundles = (
                _detect_cross_bundle_split_order(
                    current_bundle_path=bundle_path,
                    requisition=requisition,
                    source_file=source_file,
                    threshold=threshold,
                    lookback_days=lookback_days,
                    examples_root=examples_root_path,
                )
            )

        groups_quality, findings_quality = _detect_quality_anomalies(
            requisition=requisition,
            source_file=source_file,
        )

        anomaly_groups = groups_within + groups_cross + groups_quality
        findings = findings_within + findings_cross + findings_quality

        overall_status = _status_from_findings(findings)
        anomaly_score = _score_from_findings(findings)

        check = AnomalyCheck(
            run_id=run_id,
            bundle_id=_bundle_id(bundle_path, manifest, requisition),
            overall_status=overall_status,
            split_order_detected=bool(groups_within or groups_cross),
            anomaly_score=anomaly_score,
            scanned_bundles=scanned_bundles,
            rules_applied=[
                "within_pr_duplicate_item_threshold=2",
                (
                    f"cross_bundle_scan_enabled=true; lookback_days={lookback_days}"
                    if enable_cross_bundle_scan
                    else "cross_bundle_scan_enabled=false"
                ),
                f"split_order_value_threshold={threshold}",
                f"low_confidence_threshold={LOW_CONFIDENCE_THRESHOLD}",
                "vague_description_rule=generic_or_too_short_item_name",
            ],
            anomaly_groups=anomaly_groups,
            findings=findings,
        )

        _write_json(run_id, OUTPUT_JSON, check.model_dump(mode="json"))
        _write_markdown(run_id, OUTPUT_MD, _markdown_report(check))

        _safe_audit_end(
            audit_logger,
            AGENT_NAME,
            (
                f"Completed Agent G. status={check.overall_status.value}, "
                f"findings={len(check.findings)}, "
                f"split_order_detected={check.split_order_detected}"
            ),
        )

        return check

    except Exception as exc:
        _safe_audit_error(audit_logger, AGENT_NAME, str(exc))
        raise

    finally:
        _safe_metrics_end(metrics_tracker, AGENT_NAME)


def run(state: dict[str, Any]) -> dict[str, Any]:
    """
    State-based entry point for LangGraph or state-based pipeline calls.
    """
    run_id = _safe_string(state.get("run_id"))
    bundle_path = _safe_string(state.get("bundle_path"))

    if not run_id:
        raise ValueError("Agent G requires state['run_id']")

    if not bundle_path:
        raise ValueError("Agent G requires state['bundle_path']")

    check = run_agent_g(
        run_id=run_id,
        bundle_path=bundle_path,
        audit_logger=state.get("audit_logger"),
        metrics_tracker=state.get("metrics_tracker"),
        examples_root=state.get("examples_root"),
        lookback_days=_to_int(
            state.get("lookback_days"),
            DEFAULT_LOOKBACK_DAYS,
        ),
    )

    state["anomaly_check"] = check.model_dump(mode="json")
    state["anomaly_check_path"] = str(RUNS_DIR / run_id / OUTPUT_JSON)

    return state


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Agent G split-order/anomaly detection"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--bundle-path", required=True)
    parser.add_argument("--examples-root", default=None)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)

    args = parser.parse_args()

    result = run_agent_g(
        run_id=args.run_id,
        bundle_path=args.bundle_path,
        examples_root=args.examples_root,
        lookback_days=args.lookback_days,
    )

    print("Agent G completed successfully.")
    print(f"Run ID: {result.run_id}")
    print(f"Status: {result.overall_status.value}")
    print(f"Split-order detected: {result.split_order_detected}")
    print(f"Findings: {len(result.findings)}")
    print("Artifacts written:")
    print(f"- runs/{result.run_id}/{OUTPUT_JSON}")
    print(f"- runs/{result.run_id}/{OUTPUT_MD}")


if __name__ == "__main__":
    main()