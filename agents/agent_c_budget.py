"""
Agent C — Budget Validation

Input:  extracted_pr.json + budget_snapshot.csv + approval_policy.yaml
Output: budget_check.json


"""

import logging
from models import (
    BudgetCheck,
    BudgetLineCheck,
    BudgetStatus,
    Finding,
    Severity,
    EvidencePointer,
    ExtractedPR,
)
from services.run_manager import load_artifact, artifact_exists
from services.output_writer import write_budget_check
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────
BORDERLINE_THRESHOLD = 0.90  # above 90% of budget = WARNING


# ── Helper Functions ─────────────────────────────────────────

def _get_budget_row(
    cost_center: str,
    budget_snapshot: list[dict]
) -> dict | None:
    """
    Searches budget_snapshot for a specific cost center.
    Returns None if not found.
    """
    for row in budget_snapshot:
        if row.get("cost_center", "").strip() == cost_center.strip():
            return row
    return None


def _determine_status(
    requested: float,
    available: float
) -> BudgetStatus:
    """
    Deterministic logic — pure math:
    - EXCEEDED  : requested > available
    - BORDERLINE: requested > available * 90%
    - AVAILABLE : everything OK
    """
    if requested > available:
        return BudgetStatus.EXCEEDED
    elif requested > available * BORDERLINE_THRESHOLD:
        return BudgetStatus.BORDERLINE
    return BudgetStatus.AVAILABLE


def _check_capex(capex_required: str) -> bool:
    """
    Reads capex_required directly from budget_snapshot.csv.
    Column 'capex_required' is 'true'/'false' as string.
    """
    return capex_required.strip().lower() == "true"


def _check_period_cap(
    requested: float,
    period_cap: float
) -> bool:
    """
    Checks if requested amount does not exceed the period cap.
    period_cap comes directly from budget_snapshot.csv.
    """
    return requested <= period_cap


def _get_capex_threshold(approval_policy: dict) -> float:
    """
    Reads capex approval threshold from approval_policy.yaml.
    Used to flag items that require additional capex approval.
    Falls back to 10000 if not defined.
    """
    thresholds = approval_policy.get("approval_thresholds", {})
    high_value = thresholds.get("high_value", {})
    return float(high_value.get("min_amount", 10000.0))


def _build_finding(
    line_number: int,
    status: BudgetStatus,
    cost_center: str,
    gl_account: str,
    budget_period: str,
    requested: float,
    available: float,
) -> Finding | None:
    """
    Creates a Finding only when there is a problem (EXCEEDED or BORDERLINE).
    AVAILABLE status produces no finding.
    Evidence pointer includes cost_center, gl_account and budget_period
    for full traceability 
    """
    if status == BudgetStatus.AVAILABLE:
        return None

    if status == BudgetStatus.EXCEEDED:
        severity    = Severity.BLOCK
        description = (
            f"Cost center '{cost_center}' | GL '{gl_account}' | "
            f"Period '{budget_period}': requested ${requested:.2f} "
            f"exceeds available budget ${available:.2f} "
            f"(deficit: ${requested - available:.2f})."
        )
        action = "Block PR and route to FP&A for budget review."
        confidence_explanation = (
            f"Deterministic decision: {requested:.2f} > {available:.2f}."
        )
    else:  # BORDERLINE
        severity    = Severity.WARNING
        description = (
            f"Cost center '{cost_center}' | GL '{gl_account}' | "
            f"Period '{budget_period}': requested ${requested:.2f} "
            f"exceeds 90% of available budget ${available:.2f}."
        )
        action = (
            "Warning: budget near limit. "
            "Financial manager attention required."
        )
        confidence_explanation = (
            f"Deterministic decision: {requested:.2f} > "
            f"{available * BORDERLINE_THRESHOLD:.2f} "
            f"(90% of {available:.2f})."
        )

    return Finding(
        finding_id             = f"BUDGET-{line_number:03d}-{status.value}",
        agent_source           = "agent_c",
        severity               = severity,
        confidence             = 1.0,
        confidence_explanation = confidence_explanation,
        description            = description,
        evidence_pointers      = [
            EvidencePointer(
                source_file = "budget_snapshot.csv",
                page_number = 1,
                field_name  = (
                    f"cost_center={cost_center}|"
                    f"gl_account={gl_account}|"
                    f"period={budget_period}"
                )
            )
        ],
        recommended_action = action
    )


# ── Main Function ────────────────────────────────────────────

def run_agent_c(
    run_id: str,
    bundle_data: dict,
    audit_logger: AuditLogger,
    metrics_tracker: MetricsTracker,
) -> BudgetCheck:
    """
    Entry point for Agent C.

    Args:
        run_id:          Current run ID (from run_manager)
        bundle_data:     Output of file_loader.load_pr_bundle()
        audit_logger:    Instance from run_pipeline.py
        metrics_tracker: Instance from run_pipeline.py

    Returns:
        BudgetCheck: Validated Pydantic model — written to
                     runs/{run_id}/budget_check.json
    """

    # ── Idempotency check ────────────────────────────────────
    if artifact_exists(run_id, "budget_check.json"):
        logger.info("[Agent C] budget_check.json exists — skipping.")
        return BudgetCheck.model_validate(
            load_artifact(run_id, "budget_check.json")
        )

    # ── Start logging ────────────────────────────────────────
    audit_logger.log_agent_start(
        "agent_c",
        "Budget validation for all line items from extracted_pr.json"
    )
    metrics_tracker.start_agent("agent_c")

    # ── Load extracted_pr from run directory ─────────────────
    extracted = ExtractedPR.model_validate(
        load_artifact(run_id, "extracted_pr.json")
    )
    audit_logger.log_tool_call("load_artifact:extracted_pr.json")

    # ── Load budget data and policy from bundle ───────────────
    budget_snapshot = bundle_data["budget_snapshot"]
    approval_policy = bundle_data["approval_policy"]
    audit_logger.log_tool_call("load_bundle:budget_snapshot.csv")
    audit_logger.log_tool_call("load_bundle:approval_policy.yaml")

    # ── Read capex threshold from approval_policy.yaml ────────
    # validating against period caps and capex approval thresholds
    capex_threshold = _get_capex_threshold(approval_policy)
    logger.info(f"[Agent C] Capex threshold from policy: {capex_threshold}")

    # ── Validate each line item ──────────────────────────────
    line_checks: list[BudgetLineCheck] = []
    total_requested   = 0.0
    total_available   = 0.0
    seen_cost_centers: set[str] = set()  # avoid double-counting same CC

    for item in extracted.line_items:
        requested        = item.total_price
        total_requested += requested

        # Find budget row for this item's cost center
        budget_row = _get_budget_row(item.cost_center, budget_snapshot)
        audit_logger.log_tool_call("budget_snapshot_lookup")

        if budget_row is None:
            # Cost center not found in budget_snapshot — treat as EXCEEDED
            logger.warning(
                f"[Agent C] Cost center '{item.cost_center}' "
                f"not found in budget_snapshot."
            )
            available      = 0.0
            gl_account     = "UNKNOWN"
            period_cap     = 0.0
            budget_period  = "UNKNOWN"
            currency       = "UNKNOWN"
            capex_required = False
            status         = BudgetStatus.EXCEEDED
        else:
            available     = float(budget_row.get("available_budget", 0))
            gl_account    = budget_row.get("gl_account", "N/A")
            period_cap    = float(budget_row.get("period_cap", available))
            budget_period = budget_row.get("budget_period", "N/A")
            currency      = budget_row.get("currency", "EUR")

            # capex_required: from CSV column OR from policy threshold
            capex_from_csv    = _check_capex(
                budget_row.get("capex_required", "false")
            )
            capex_from_policy = requested >= capex_threshold
            capex_required    = capex_from_csv or capex_from_policy

            status = _determine_status(requested, available)

            # Count each cost center budget only once 
            if item.cost_center not in seen_cost_centers:
                total_available += available
                seen_cost_centers.add(item.cost_center)

            logger.info(
                f"[Agent C] Validating | cost_center={item.cost_center} | "
                f"gl_account={gl_account} | period={budget_period} | "
                f"currency={currency} | requested={requested:.2f} | "
                f"available={available:.2f} | capex_required={capex_required}"
            )

        # Period cap check
        period_cap_ok = _check_period_cap(requested, period_cap)

        # Build finding only if there is a problem
        finding = _build_finding(
            line_number   = item.line_number,
            status        = status,
            cost_center   = item.cost_center,
            gl_account    = gl_account,
            budget_period = budget_period,
            requested     = requested,
            available     = available,
        )

        line_checks.append(BudgetLineCheck(
            line_number      = item.line_number,
            cost_center      = item.cost_center,
            gl_account       = gl_account,
            requested_amount = requested,
            available_budget = available,
            status           = status,
            period_cap_ok    = period_cap_ok,
            capex_required   = capex_required,
            findings         = [finding] if finding else []
        ))

        logger.info(
            f"[Agent C] Line {item.line_number} | "
            f"status={status.value} | "
            f"period_cap_ok={period_cap_ok}"
        )

    # ── Overall status: worst-case logic ─────────────────────
    # If even 1 line is EXCEEDED → overall is EXCEEDED
    statuses = [lc.status for lc in line_checks]
    if BudgetStatus.EXCEEDED in statuses:
        overall = BudgetStatus.EXCEEDED
    elif BudgetStatus.BORDERLINE in statuses:
        overall = BudgetStatus.BORDERLINE
    else:
        overall = BudgetStatus.AVAILABLE

    # ── Log exception rate to MetricsTracker ─────────────────
    # Tracks how many line items had budget issues
    exceeded_count = sum(
        1 for lc in line_checks
        if lc.status == BudgetStatus.EXCEEDED
    )
    exception_rate = (
        round(exceeded_count / len(line_checks), 2)
        if line_checks else 0.0
    )
    metrics_tracker.log_exception_rate(exception_rate)
    logger.info(f"[Agent C] Exception rate: {exception_rate}")

    # ── Build BudgetCheck model ──────────────────────────────
    budget_check = BudgetCheck(
        run_id          = run_id,
        overall_status  = overall,
        line_checks     = line_checks,
        total_requested = total_requested,
        total_available = total_available,
    )

    # ── Write artifact ───────────────────────────────────────
    write_budget_check(run_id, budget_check)
    audit_logger.log_tool_call("write_budget_check:budget_check.json")

    # ── End logging + metrics ────────────────────────────────
    metrics_tracker.end_agent("agent_c", confidence=1.0)
    audit_logger.log_agent_end(
        output_summary=(
            f"overall_status={overall.value} | "
            f"total_requested={total_requested:.2f} | "
            f"total_available={total_available:.2f} | "
            f"lines_checked={len(line_checks)} | "
            f"exception_rate={exception_rate} | "
            f"capex_threshold={capex_threshold:.2f}"
        )
    )

    logger.info(f"[Agent C] Completed — overall={overall.value}")
    return budget_check