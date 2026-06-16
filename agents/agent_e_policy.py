"""
Agent E — Compliance & Policy Engine

Input:  extracted_pr.json + budget_check.json +
        vendor_match.json + approval_policy.yaml
Output: compliance_findings.json


Architecture:
- LangGraph ReAct Agent with 4 tools (LLM + Tools + ReAct)
- LLM reasoning is used for audit trail
- Deterministic _build_findings() ensures consistent structured output
- budget_check integrated from Agent C — links compliance to budget status
- LLM: Groq Llama 3.3 70B, temperature=0 for deterministic outputs
"""

import json
import logging
from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from models import (
    ComplianceFindings,
    ComplianceStatus,
    ProcurementScenario,
    Finding,
    Severity,
    EvidencePointer,
    ExtractedPR,
    VendorMatch,
    VendorStatus,
    BudgetCheck,
    BudgetStatus,
)
from services.run_manager import load_artifact, artifact_exists
from services.output_writer import write_compliance_findings
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker

logger = logging.getLogger(__name__)

# ── Supported currencies — multi-currency warning ─────────────
SUPPORTED_CURRENCIES = {"EUR", "USD", "GBP", "CHF"}

# ── Sole-source justification keywords ───────────────────────
SOLE_SOURCE_KEYWORDS = [
    "sole source", "sole-source", "only vendor", "unique capability",
    "proprietary", "no alternative", "single source", "emergency",
    "preferred vendor unavailable", "non-preferred"
]


# ── Shared Tool Context ──────────────────────────────────────
# Populated before agent execution — shared across all tools
_policy_context: dict = {}


def _set_policy_context(
    extracted: ExtractedPR,
    budget_check: BudgetCheck,
    vendor_match: VendorMatch,
    approval_policy: dict,
) -> None:
    """Loads all input data into shared context for tools."""
    global _policy_context
    _policy_context = {
        "extracted":       extracted,
        "budget_check":    budget_check,
        "vendor_match":    vendor_match,
        "approval_policy": approval_policy,
    }


# ── Tool 1: Approval Authority Check ────────────────────────
@tool
def check_approval_authority(input: str = "") -> str:
    """
    Checks if the PR value falls within the correct approval authority.
    Returns required approver role and escalation path based on
    approval_policy.yaml thresholds.
    """
    extracted: ExtractedPR = _policy_context["extracted"]
    policy: dict           = _policy_context["approval_policy"]

    total_value = extracted.total_value
    thresholds  = policy.get("approval_thresholds", {})

    low_max  = float(thresholds.get("low_value",    {}).get("max_amount", 1000))
    med_min  = float(thresholds.get("medium_value", {}).get("min_amount", 1001))
    med_max  = float(thresholds.get("medium_value", {}).get("max_amount", 5000))
    high_min = float(thresholds.get("high_value",   {}).get("min_amount", 5001))

    low_role  = thresholds.get("low_value",    {}).get("approver_role", "Team Lead")
    med_role  = thresholds.get("medium_value", {}).get("approver_role", "Department Manager")
    high_role = thresholds.get("high_value",   {}).get("approver_role", "Finance Director")

    if total_value <= low_max:
        required_approver = low_role
        escalation_path   = f"Approve by {low_role}"
        authority_ok      = True
    elif med_min <= total_value <= med_max:
        required_approver = med_role
        escalation_path   = (
            f"Approve by {med_role} — "
            f"escalate to {high_role} if exceptions exist"
        )
        authority_ok = True
    else:
        required_approver = high_role
        escalation_path   = (
            f"Mandatory approval by {high_role} — "
            f"value ${total_value:.2f} exceeds ${high_min:.0f} threshold"
        )
        authority_ok = total_value >= high_min

    result = {
        "total_value":       total_value,
        "required_approver": required_approver,
        "escalation_path":   escalation_path,
        "authority_ok":      authority_ok,
        "policy_reference":  "approval_policy.yaml:approval_thresholds",
    }
    logger.info(f"[Agent E Tool 1] approval_authority: {result}")
    return json.dumps(result)


# ── Tool 2: Bid Threshold Check ──────────────────────────────
@tool
def check_bid_threshold(input: str = "") -> str:
    """
    Checks if competitive bidding is required based on total PR value.
    Emergency procurement bypasses bid requirements.
    Returns bid_threshold_met and policy reference.
    """
    extracted: ExtractedPR = _policy_context["extracted"]
    policy: dict           = _policy_context["approval_policy"]

    total_value        = extracted.total_value
    bid_required_above = float(
        policy.get("sourcing_rules", {}).get("bid_required_above", 5000)
    )
    scenario      = policy.get("procurement_scenario", "STANDARD").upper()
    justification = extracted.header.justification or ""
    bid_required  = total_value > bid_required_above

    # Emergency procurement bypasses bid requirements
    if scenario == "EMERGENCY":
        bid_threshold_met = True
        note = "Emergency procurement — bid requirement waived per policy."
    else:
        bid_threshold_met = not bid_required or len(justification.strip()) > 0
        note = ""

    result = {
        "total_value":        total_value,
        "bid_required_above": bid_required_above,
        "bid_required":       bid_required,
        "bid_threshold_met":  bid_threshold_met,
        "scenario":           scenario,
        "note":               note,
        "justification":      justification[:100],
        "policy_reference":   "approval_policy.yaml:sourcing_rules.bid_required_above",
    }
    logger.info(f"[Agent E Tool 2] bid_threshold: {result}")
    return json.dumps(result)


# ── Tool 3: Sole-Source Justification Check ──────────────────
@tool
def check_sole_source_justification(input: str = "") -> str:
    """
    Checks if non-preferred vendors have written sole-source justification.
    Generic PR justification is NOT sufficient — requires vendor-specific keywords.
    Emergency procurement is exempt
    """
    extracted: ExtractedPR    = _policy_context["extracted"]
    vendor_match: VendorMatch = _policy_context["vendor_match"]
    policy: dict              = _policy_context["approval_policy"]

    scenario = policy.get("procurement_scenario", "STANDARD").upper()
    require_justification = policy.get(
        "sourcing_rules", {}
    ).get("require_justification_for_non_preferred_vendor", True)

    non_preferred_lines = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]

    justification = extracted.header.justification or ""
    has_sole_source_justification = any(
        keyword.lower() in justification.lower()
        for keyword in SOLE_SOURCE_KEYWORDS
    )

    if scenario == "EMERGENCY":
        sole_source_justified = True
        issue                 = "none — emergency procurement exemption applies"
    elif not non_preferred_lines:
        sole_source_justified = True
        issue                 = "none — all vendors are preferred"
    elif require_justification and not has_sole_source_justification:
        sole_source_justified = False
        issue                 = (
            f"{len(non_preferred_lines)} non-preferred vendor(s) "
            f"without sole-source justification."
        )
    else:
        sole_source_justified = True
        issue                 = "none"

    result = {
        "non_preferred_count":           len(non_preferred_lines),
        "has_sole_source_justification": has_sole_source_justification,
        "sole_source_justified":         sole_source_justified,
        "scenario":                      scenario,
        "issue":                         issue,
        "policy_reference":              (
            "approval_policy.yaml:sourcing_rules"
            ".require_justification_for_non_preferred_vendor"
        ),
    }
    logger.info(f"[Agent E Tool 3] sole_source: {result}")
    return json.dumps(result)


# ── Tool 4: Sourcing Rules Check ─────────────────────────────
@tool
def check_sourcing_rules(input: str = "") -> str:
    """
    Checks if vendors are on the approved vendor list.
    Emergency procurement may use unapproved vendors with justification.
    Returns sourcing compliance and issues 
    """
    vendor_match: VendorMatch = _policy_context["vendor_match"]
    policy: dict              = _policy_context["approval_policy"]

    scenario         = policy.get("procurement_scenario", "STANDARD").upper()
    require_approved = policy.get(
        "sourcing_rules", {}
    ).get("require_approved_vendor", True)

    not_found_lines = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]
    non_preferred_lines = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NON_PREFERRED
    ]

    sourcing_ok = True
    issues      = []

    if scenario == "EMERGENCY" and not_found_lines:
        issues.append(
            f"Emergency procurement: {len(not_found_lines)} unapproved "
            f"vendor(s) — post-procurement approval required."
        )
        sourcing_ok = True
    elif require_approved and not_found_lines:
        sourcing_ok = False
        issues.append(
            f"{len(not_found_lines)} vendor(s) not on approved list."
        )

    if non_preferred_lines:
        issues.append(
            f"{len(non_preferred_lines)} non-preferred vendor(s) detected."
        )

    result = {
        "require_approved_vendor": require_approved,
        "not_found_count":         len(not_found_lines),
        "non_preferred_count":     len(non_preferred_lines),
        "sourcing_ok":             sourcing_ok,
        "scenario":                scenario,
        "issues":                  issues,
        "policy_reference":        (
            "approval_policy.yaml:sourcing_rules.require_approved_vendor"
        ),
    }
    logger.info(f"[Agent E Tool 4] sourcing_rules: {result}")
    return json.dumps(result)


# ── LangGraph ReAct Agent ────────────────────────────────────
def _create_react_agent_graph(llm, tools):
    """
    Creates LangGraph ReAct agent with 4 compliance tools.
    LangGraph 0.2+ replaces LangChain AgentExecutor.
    temperature=0 ensures deterministic outputs
    """
    return create_react_agent(
        model = llm,
        tools = tools,
    )


# ── Helper: Detect Framework Agreement ───────────────────────
def _detect_framework_agreement(approval_policy: dict) -> str | None:
    """
    Reads framework_agreement from approval_policy.yaml if present.
    Supports framework agreements.
    """
    return approval_policy.get("framework_agreement", None)


# ── Helper: Multi-currency Warning ───────────────────────────
def _check_currency(
    currency: str,
    findings: list[Finding],
) -> None:
    """
    Adds WARNING finding if currency is non-standard.
    Supports multi-currency POs.
    """
    if currency.upper() not in SUPPORTED_CURRENCIES:
        findings.append(Finding(
            finding_id             = "COMPLIANCE-CURRENCY-001",
            agent_source           = "agent_e",
            severity               = Severity.WARNING,
            confidence             = 1.0,
            confidence_explanation = (
                f"Currency '{currency}' not in supported set "
                f"{SUPPORTED_CURRENCIES}. Manual FX review required."
            ),
            description            = (
                f"PR uses non-standard currency '{currency}'. "
                f"Multi-currency PO requires additional FX compliance review."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "approval_policy.yaml",
                page_number = 1,
                field_name  = "currency"
            )],
            recommended_action = (
                "Submit FX rate confirmation and obtain Finance Director "
                "sign-off for multi-currency PO processing."
            )
        ))


# ── Helper: Emergency Procurement Path ───────────────────────
def _check_emergency_path(
    scenario: ProcurementScenario,
    extracted: ExtractedPR,
    findings: list[Finding],
    policy_references: list[str],
) -> None:
    """
    Adds expedited approval finding for emergency procurement.
    Emergency triggers expedited path.
    """
    if scenario != ProcurementScenario.EMERGENCY:
        return

    justification = extracted.header.justification or ""
    policy_references.append(
        "approval_policy.yaml:procurement_scenario=EMERGENCY"
    )
    findings.append(Finding(
        finding_id             = "COMPLIANCE-EMERGENCY-001",
        agent_source           = "agent_e",
        severity               = Severity.WARNING,
        confidence             = 1.0,
        confidence_explanation = (
            "Procurement scenario is EMERGENCY — expedited approval "
            "path triggered per Slide 21 requirements."
        ),
        description            = (
            f"Emergency procurement detected for PR {extracted.pr_id}. "
            f"Standard competitive bidding waived. "
            f"Justification: {justification[:100] or 'None provided'}."
        ),
        evidence_pointers      = [EvidencePointer(
            source_file = "approval_policy.yaml",
            page_number = 1,
            field_name  = "procurement_scenario"
        )],
        recommended_action = (
            "Route immediately to Finance Director for expedited approval. "
            "Post-procurement audit required within 5 business days."
        )
    ))
    logger.info(f"[Agent E] Emergency path triggered for {extracted.pr_id}")


# ── Helper: Blanket Order Path ───────────────────────────────
def _check_blanket_order(
    scenario: ProcurementScenario,
    extracted: ExtractedPR,
    findings: list[Finding],
    policy_references: list[str],
) -> None:
    """
    Adds informational finding for blanket order procurement.
    Supports blanket orders.
    """
    if scenario != ProcurementScenario.BLANKET_ORDER:
        return

    policy_references.append(
        "approval_policy.yaml:procurement_scenario=BLANKET_ORDER"
    )
    findings.append(Finding(
        finding_id             = "COMPLIANCE-BLANKET-001",
        agent_source           = "agent_e",
        severity               = Severity.WARNING,
        confidence             = 1.0,
        confidence_explanation = (
            "Procurement scenario is BLANKET_ORDER — "
            "standard approval applies with periodic review."
        ),
        description            = (
            f"Blanket order detected for PR {extracted.pr_id}. "
            f"Ensure blanket order framework is active and value "
            f"${extracted.total_value:.2f} is within approved limits."
        ),
        evidence_pointers      = [EvidencePointer(
            source_file = "approval_policy.yaml",
            page_number = 1,
            field_name  = "procurement_scenario"
        )],
        recommended_action = (
            "Verify blanket order reference number and confirm "
            "remaining balance covers this requisition. "
            "Route to Department Manager for periodic review."
        )
    ))
    logger.info(f"[Agent E] Blanket order detected for {extracted.pr_id}")


# ── Helper: Budget Status Integration ────────────────────────
def _check_budget_status(
    budget_check: BudgetCheck,
    required_approver: str,
    findings: list[Finding],
    policy_references: list[str],
) -> None:
    """
    Integrates Agent C budget findings into Agent E compliance.
    Compliance validation links to budget status.
    If budget is EXCEEDED → compliance cannot be COMPLIANT.
    If budget is BORDERLINE → WARNING added for approver attention.
    """
    if budget_check.overall_status == BudgetStatus.EXCEEDED:
        policy_references.append("budget_check.json:overall_status=EXCEEDED")
        findings.append(Finding(
            finding_id             = "COMPLIANCE-BUDGET-001",
            agent_source           = "agent_e",
            severity               = Severity.BLOCK,
            confidence             = 1.0,
            confidence_explanation = (
                "Budget check from Agent C returned EXCEEDED. "
                "PR cannot proceed to approval without budget resolution."
            ),
            description            = (
                f"Budget validation failed: total requested "
                f"${budget_check.total_requested:.2f} exceeds "
                f"available ${budget_check.total_available:.2f} "
                f"(deficit: "
                f"${budget_check.total_requested - budget_check.total_available:.2f}). "
                f"PR blocked pending budget review."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "budget_check.json",
                page_number = 1,
                field_name  = "overall_status=EXCEEDED"
            )],
            recommended_action = (
                f"Resolve budget deficit before proceeding. "
                f"Route to FP&A and {required_approver}."
            )
        ))
        logger.info(
            f"[Agent E] Budget EXCEEDED — BLOCK finding added. "
            f"Deficit: "
            f"{budget_check.total_requested - budget_check.total_available:.2f}"
        )

    elif budget_check.overall_status == BudgetStatus.BORDERLINE:
        policy_references.append("budget_check.json:overall_status=BORDERLINE")
        findings.append(Finding(
            finding_id             = "COMPLIANCE-BUDGET-002",
            agent_source           = "agent_e",
            severity               = Severity.WARNING,
            confidence             = 1.0,
            confidence_explanation = (
                "Budget check from Agent C returned BORDERLINE. "
                "Budget is near limit — additional scrutiny required."
            ),
            description            = (
                f"Budget near limit: requested "
                f"${budget_check.total_requested:.2f} against "
                f"available ${budget_check.total_available:.2f} "
                f"(above 90% threshold)."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "budget_check.json",
                page_number = 1,
                field_name  = "overall_status=BORDERLINE"
            )],
            recommended_action = (
                f"Flag for {required_approver} attention. "
                f"Verify remaining budget before final approval."
            )
        ))
        logger.info("[Agent E] Budget BORDERLINE — WARNING finding added.")


# ── Build Findings ────────────────────────────────────────────
def _build_findings(
    extracted: ExtractedPR,
    vendor_match: VendorMatch,
    approval_policy: dict,
    scenario_enum: ProcurementScenario,
    currency: str,
    budget_check: BudgetCheck,
) -> tuple[list[Finding], list[str], bool, bool, bool, str | None]:
    """
    Builds structured Finding objects from deterministic checks.
    Covers all requirements:
    1. Approval authority + escalation paths
    2. Bid threshold
    3. Sole-source justification
    4. Sourcing rules
    5. Budget status integration (Agent C → Agent E link)
    6. Emergency procurement path
    7. Multi-currency warning
    8. Blanket order path
    9. Framework agreement detection

    Returns: (findings, policy_references,
              approval_ok, bid_ok, sole_source_ok, framework_agreement)
    """
    findings:          list[Finding] = []
    policy_references: list[str]     = []

    total_value        = extracted.total_value
    thresholds         = approval_policy.get("approval_thresholds", {})
    bid_required_above = float(
        approval_policy.get("sourcing_rules", {}).get("bid_required_above", 5000)
    )
    require_approved = approval_policy.get(
        "sourcing_rules", {}
    ).get("require_approved_vendor", True)
    justification    = extracted.header.justification or ""
    scenario_str     = approval_policy.get(
        "procurement_scenario", "STANDARD"
    ).upper()

    # ── 1. Approval Authority + Escalation Path ──────────────
    low_max   = float(thresholds.get("low_value",    {}).get("max_amount", 1000))
    med_max   = float(thresholds.get("medium_value", {}).get("max_amount", 5000))
    high_min  = float(thresholds.get("high_value",   {}).get("min_amount", 5001))
    low_role  = thresholds.get("low_value",    {}).get("approver_role", "Team Lead")
    med_role  = thresholds.get("medium_value", {}).get("approver_role", "Department Manager")
    high_role = thresholds.get("high_value",   {}).get("approver_role", "Finance Director")

    if total_value <= low_max:
        required_approver = low_role
        escalation_path   = f"Approve by {low_role}"
    elif total_value <= med_max:
        required_approver = med_role
        escalation_path   = (
            f"Approve by {med_role} — "
            f"escalate to {high_role} if exceptions exist"
        )
    else:
        required_approver = high_role
        escalation_path   = (
            f"Mandatory approval by {high_role} — "
            f"value ${total_value:.2f} exceeds ${high_min:.0f} threshold"
        )

    approval_ok = True
    policy_references.append("approval_policy.yaml:approval_thresholds")
    logger.info(
        f"[Agent E] Required approver: {required_approver} | "
        f"Escalation: {escalation_path}"
    )

    # ── 2. Bid Threshold ─────────────────────────────────────
    bid_required = total_value > bid_required_above

    if scenario_str == "EMERGENCY":
        bid_ok = True
        logger.info("[Agent E] Emergency — bid requirement waived")
    else:
        bid_ok = not bid_required or len(justification.strip()) > 0

    policy_references.append(
        "approval_policy.yaml:sourcing_rules.bid_required_above"
    )

    if not bid_ok:
        findings.append(Finding(
            finding_id             = "COMPLIANCE-BID-001",
            agent_source           = "agent_e",
            severity               = Severity.EXCEPTION,
            confidence             = 1.0,
            confidence_explanation = (
                f"Deterministic: total_value {total_value} > "
                f"bid_required_above {bid_required_above}. "
                f"No justification provided."
            ),
            description            = (
                f"PR value ${total_value:.2f} exceeds bid threshold "
                f"${bid_required_above:.2f}. "
                f"Competitive bidding required but no justification found."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "approval_policy.yaml",
                page_number = 1,
                field_name  = "sourcing_rules.bid_required_above"
            )],
            recommended_action = (
                f"Provide competitive bid documentation or sole-source "
                f"justification. Escalate to {required_approver}."
            )
        ))

    # ── 3. Sole-Source Justification ─────────────────────────
    non_preferred = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]
    has_sole_source_justification = any(
        keyword.lower() in justification.lower()
        for keyword in SOLE_SOURCE_KEYWORDS
    )

    if scenario_str == "EMERGENCY":
        sole_source_ok = True
    else:
        sole_source_ok = not non_preferred or has_sole_source_justification

    policy_references.append(
        "approval_policy.yaml:sourcing_rules"
        ".require_justification_for_non_preferred_vendor"
    )

    if (non_preferred
            and not has_sole_source_justification
            and scenario_str != "EMERGENCY"):
        findings.append(Finding(
            finding_id             = "COMPLIANCE-SOLE-001",
            agent_source           = "agent_e",
            severity               = Severity.EXCEPTION,
            confidence             = 0.95,
            confidence_explanation = (
                f"Non-preferred vendor on {len(non_preferred)} line(s). "
                f"PR justification does not contain vendor-specific "
                f"sole-source reasoning."
            ),
            description            = (
                f"{len(non_preferred)} line item(s) use non-preferred "
                f"vendor(s) without sole-source justification. "
                f"Generic PR justification is not sufficient."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "approval_policy.yaml",
                page_number = 1,
                field_name  = (
                    "sourcing_rules"
                    ".require_justification_for_non_preferred_vendor"
                )
            )],
            recommended_action = (
                f"Provide explicit sole-source justification or switch to "
                f"approved vendor. Escalation path: {escalation_path}."
            )
        ))

    # ── 4. Sourcing Rules ────────────────────────────────────
    not_found = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]
    policy_references.append(
        "approval_policy.yaml:sourcing_rules.require_approved_vendor"
    )

    if require_approved and not_found and scenario_str != "EMERGENCY":
        findings.append(Finding(
            finding_id             = "COMPLIANCE-VENDOR-001",
            agent_source           = "agent_e",
            severity               = Severity.BLOCK,
            confidence             = 1.0,
            confidence_explanation = (
                f"{len(not_found)} vendor(s) not found "
                f"in approved vendor list."
            ),
            description            = (
                f"{len(not_found)} line item(s) have vendors "
                f"not on the approved vendor list."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "approval_policy.yaml",
                page_number = 1,
                field_name  = "sourcing_rules.require_approved_vendor"
            )],
            recommended_action = (
                f"Replace vendor with approved supplier from "
                f"approved_vendors.csv or request vendor approval. "
                f"Escalation path: {escalation_path}."
            )
        ))

    # ── 5. Budget Status Integration — Agent C → Agent E ─────
    # Compliance links to budget status from Agent C
    _check_budget_status(
        budget_check      = budget_check,
        required_approver = required_approver,
        findings          = findings,
        policy_references = policy_references,
    )

    # ── 6. Emergency Procurement Path ─────
    _check_emergency_path(
        scenario          = scenario_enum,
        extracted         = extracted,
        findings          = findings,
        policy_references = policy_references,
    )

    # ── 7. Multi-currency Warning  ─────────
    _check_currency(currency, findings)

    # ── 8. Blanket Order — Slide 14 point 3 ──────────────────
    _check_blanket_order(
        scenario          = scenario_enum,
        extracted         = extracted,
        findings          = findings,
        policy_references = policy_references,
    )

    # ── 9. Framework Agreement  ────────────
    framework_agreement = _detect_framework_agreement(approval_policy)
    if framework_agreement:
        policy_references.append(
            f"framework_agreement:{framework_agreement}"
        )
        logger.info(f"[Agent E] Framework agreement: {framework_agreement}")

    return (
        findings,
        list(set(policy_references)),
        approval_ok,
        bid_ok,
        sole_source_ok,
        framework_agreement,
    )


# ── Main Function ────────────────────────────────────────────
def run_agent_e(
    run_id: str,
    bundle_data: dict,
    audit_logger: AuditLogger,
    metrics_tracker: MetricsTracker,
) -> ComplianceFindings:
    """
    Entry point for Agent E — Compliance & Policy Engine.

    Architecture:
    1. LangGraph ReAct agent runs 4 tools for compliance reasoning
    2. LLM reasoning logged for audit trail — Slide 17 traceability
    3. _build_findings() produces deterministic structured output
    4. budget_check integrated from Agent C output

    Args:
        run_id:          Current run ID (from run_manager)
        bundle_data:     Output of file_loader.load_pr_bundle()
        audit_logger:    Instance from Intern 1 (run_pipeline.py)
        metrics_tracker: Instance from Intern 1 (run_pipeline.py)

    Returns:
        ComplianceFindings: Validated Pydantic model — written to
                            runs/{run_id}/compliance_findings.json
    """

    # ── Idempotency check ────────────────────────────────────
    if artifact_exists(run_id, "compliance_findings.json"):
        logger.info("[Agent E] compliance_findings.json exists — skipping.")
        return ComplianceFindings.model_validate(
            load_artifact(run_id, "compliance_findings.json")
        )

    # ── Start logging ────────────────────────────────────────
    audit_logger.log_agent_start(
        "agent_e",
        "Compliance & policy validation for PR bundle"
    )
    metrics_tracker.start_agent("agent_e")

    # ── Load artifacts from run directory ────────────────────
    extracted = ExtractedPR.model_validate(
        load_artifact(run_id, "extracted_pr.json")
    )
    audit_logger.log_tool_call("load_artifact:extracted_pr.json")

    budget_check = BudgetCheck.model_validate(
        load_artifact(run_id, "budget_check.json")
    )
    audit_logger.log_tool_call("load_artifact:budget_check.json")

    vendor_match = VendorMatch.model_validate(
        load_artifact(run_id, "vendor_match.json")
    )
    audit_logger.log_tool_call("load_artifact:vendor_match.json")

    # ── Load policy from bundle ──────────────────────────────
    approval_policy = bundle_data["approval_policy"]
    audit_logger.log_tool_call("load_bundle:approval_policy.yaml")

    # ── Read policy metadata ─────────────────────────────────
    currency             = approval_policy.get("currency", "EUR")
    procurement_scenario = approval_policy.get(
        "procurement_scenario", "STANDARD"
    ).upper()

    try:
        scenario_enum = ProcurementScenario[procurement_scenario]
    except KeyError:
        scenario_enum = ProcurementScenario.STANDARD
        logger.warning(
            f"[Agent E] Unknown scenario '{procurement_scenario}' "
            f"— defaulting to STANDARD"
        )

    # ── Set shared context for tools ─────────────────────────
    _set_policy_context(
        extracted       = extracted,
        budget_check    = budget_check,
        vendor_match    = vendor_match,
        approval_policy = approval_policy,
    )
    audit_logger.log_tool_call("set_policy_context")

    # ── Build PR context for LangGraph agent ─────────────────
    pr_context = (
        f"Validate this Purchase Requisition for compliance:\n"
        f"PR ID: {extracted.pr_id} | "
        f"Requester: {extracted.header.requester} | "
        f"Department: {extracted.header.department} | "
        f"Total Value: ${extracted.total_value:.2f} | "
        f"Currency: {currency} | "
        f"Scenario: {procurement_scenario} | "
        f"Line Items: {len(extracted.line_items)} | "
        f"Justification: {extracted.header.justification or 'None provided'} | "
        f"Budget Status: {budget_check.overall_status.value} | "
        f"Vendor Status: {vendor_match.overall_status.value}\n\n"
        f"Run ALL 4 tools: check_approval_authority, check_bid_threshold, "
        f"check_sole_source_justification, check_sourcing_rules."
    )

    # ── Run LangGraph ReAct Agent ─────────────────────────────
    # LLM reasoning is used for:
    # 1. Calling tools in the correct order
    # 2. Producing human-readable compliance summary
    # 3. Audit trail 
    logger.info(f"[Agent E] Running LangGraph ReAct agent for {extracted.pr_id}")

    llm   = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    tools = [
        check_approval_authority,
        check_bid_threshold,
        check_sole_source_justification,
        check_sourcing_rules,
    ]

    agent_graph = _create_react_agent_graph(llm, tools)

    try:
        agent_result = agent_graph.invoke({
            "messages": [("human", pr_context)]
        })
        messages     = agent_result.get("messages", [])
        agent_output = messages[-1].content if messages else ""
        audit_logger.log_tool_call("langgraph_react_agent")

        # LLM reasoning logged as audit evidence 
        # agent_output contains full ReAct chain: tool calls + LLM reasoning
        logger.info(
            f"[Agent E] LLM reasoning completed — "
            f"output length: {len(agent_output)}"
        )
        if agent_output:
            # Log first 300 chars of reasoning for audit trail
            logger.info(
                f"[Agent E] LLM reasoning summary: {agent_output[:300]}"
            )

    except Exception as e:
        logger.error(f"[Agent E] LangGraph agent failed: {e}")
        agent_output = ""

    

    # ── Build structured findings ─────────────────────────────
    # Deterministic checks ensure consistent output 
    # agent_output (LLM reasoning) is logged above for audit trail
    (
        findings,
        policy_references,
        approval_ok,
        bid_ok,
        sole_source_ok,
        framework_agreement,
    ) = _build_findings(
        extracted       = extracted,
        vendor_match    = vendor_match,
        approval_policy = approval_policy,
        scenario_enum   = scenario_enum,
        currency        = currency,
        budget_check    = budget_check,
    )
    audit_logger.log_tool_call("build_compliance_findings")

    # ── Determine overall compliance ─────────────────────────
    block_findings     = [f for f in findings if f.severity == Severity.BLOCK]
    exception_findings = [f for f in findings if f.severity == Severity.EXCEPTION]

    if block_findings:
        overall_compliance = ComplianceStatus.NON_COMPLIANT
    elif exception_findings:
        overall_compliance = ComplianceStatus.PARTIAL
    else:
        overall_compliance = ComplianceStatus.COMPLIANT

    # ── Build ComplianceFindings model ───────────────────────
    compliance_findings = ComplianceFindings(
        run_id                = run_id,
        overall_compliance    = overall_compliance,
        procurement_scenario  = scenario_enum,
        approval_authority_ok = approval_ok,
        sole_source_justified = sole_source_ok,
        bid_threshold_met     = bid_ok,
        framework_agreement   = framework_agreement,
        currency              = currency,
        findings              = findings,
        policy_references     = policy_references,
    )

    # ── Write artifact ───────────────────────────────────────
    write_compliance_findings(run_id, compliance_findings)
    audit_logger.log_tool_call("write_compliance_findings.json")

    # ── End logging + metrics ────────────────────────────────
    # ── End logging + metrics ────────────────────────────────
    metrics_tracker.end_agent("agent_e", confidence=0.90)
    audit_logger.log_agent_end(
        output_summary=(
            f"overall_compliance={overall_compliance.value} | "
            f"scenario={scenario_enum.value} | "
            f"findings={len(findings)} | "
            f"approval_ok={approval_ok} | "
            f"bid_ok={bid_ok} | "
            f"sole_source_ok={sole_source_ok} | "
            f"budget_status={budget_check.overall_status.value} | "
            f"framework_agreement={framework_agreement} | "
            f"llm_reasoning={agent_output[:200] if agent_output else 'none'}"
        )
    )

    logger.info(
        f"[Agent E] Completed — "
        f"compliance={overall_compliance.value} | "
        f"findings={len(findings)}"
    )
    return compliance_findings