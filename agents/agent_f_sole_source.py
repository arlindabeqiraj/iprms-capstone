"""
Agent f — Standalone Sole-Source & Bid Threshold Agent

Standalone agent dedicated exclusively to:
1. Sole-source justification review (deep LLM analysis)
2. Bid threshold enforcement (deterministic)
3. Justification quality scoring (LLM)
4. Risk assessment (combined score)

Difference from Agent E:
- Agent E: quick pass/fail check as part of 4 checks
- Agent f: deep dedicated analysis with LLM quality scoring,
           gap identification, and risk assessment

LangGraph ReAct Agent with 3 specialized tools.
LLM: Groq Llama 3.3 70B, temperature=0.
"""

import json
import logging
import os
from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from models import (
    Finding,
    Severity,
    EvidencePointer,
    ExtractedPR,
    VendorMatch,
    VendorStatus,
)
from models.sole_source_models import (
    SoleSourceCheck,
    SoleSourceLineCheck,
    JustificationQuality,
    BidStatus,
    SoleSourceRiskLevel,
)
from models.policy_models import ProcurementScenario
from services.run_manager import load_artifact, artifact_exists
from services.output_writer import write_sole_source_check
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker

logger = logging.getLogger(__name__)

# ── Sole-source justification keywords ───────────────────────
SOLE_SOURCE_KEYWORDS = [
    "sole source", "sole-source", "only vendor", "unique capability",
    "proprietary", "no alternative", "single source", "emergency",
    "preferred vendor unavailable", "non-preferred", "exclusive",
    "patented", "specialized", "only supplier", "no substitute",
]

# ── Strong justification indicators ──────────────────────────
STRONG_JUSTIFICATION_INDICATORS = [
    "patent", "proprietary", "exclusive contract", "unique capability",
    "no alternative", "only supplier", "specialized expertise",
    "no substitute available",
]

# ── Weak justification indicators ────────────────────────────
WEAK_JUSTIFICATION_INDICATORS = [
    "preferred", "familiar", "used before", "comfortable with",
    "like this vendor", "always use",
]

# ── Shared Tool Context ──────────────────────────────────────
_sole_source_context: dict = {}


def _set_sole_source_context(
    extracted: ExtractedPR,
    vendor_match: VendorMatch,
    approval_policy: dict,
) -> None:
    """Loads all input data into shared context for tools."""
    global _sole_source_context
    _sole_source_context = {
        "extracted":       extracted,
        "vendor_match":    vendor_match,
        "approval_policy": approval_policy,
    }


# ──  _calculate_risk_score — single source of truth ──
def _calculate_risk_score(
    extracted: ExtractedPR,
    vendor_match: VendorMatch,
    approval_policy: dict,
) -> tuple[float, SoleSourceRiskLevel]:
    """
     Single source of truth for risk score calculation.

     Used by:
      - assess_sole_source_risk() tool (for LLM reasoning)
      - run_agent_f() (for deterministic fallback and SoleSourceCheck output)

     Risk score factors:
      - Factor 1: Vendor status           (0.00 – 0.40)
      - Factor 2: Procurement value band  (0.05 – 0.30)
      - Factor 3: Justification quality   (0.00 – 0.30)
      - Emergency adjustment:             -0.20
    """
    justification = extracted.header.justification or ""
    total_value   = extracted.total_value
    scenario      = approval_policy.get("procurement_scenario", "STANDARD").upper()
    high_min      = float(
        approval_policy.get("approval_thresholds", {})
                       .get("high_value", {})
                       .get("min_amount", 5001)
    )

    non_preferred = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]
    not_found = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]

    has_keywords = any(
        kw.lower() in justification.lower()
        for kw in SOLE_SOURCE_KEYWORDS
    )

    risk_score = 0.0

    if not_found:
        risk_score += 0.4
    elif non_preferred:
        risk_score += 0.25

    if total_value >= high_min:
        risk_score += 0.3
    elif total_value >= high_min * 0.5:
        risk_score += 0.15
    else:
        risk_score += 0.05

    if not non_preferred and not not_found:
        risk_score += 0.0
    elif not justification:
        risk_score += 0.3
    elif not has_keywords:
        risk_score += 0.2
    else:
        risk_score += 0.05

    if scenario == "EMERGENCY":
        risk_score = max(0.0, risk_score - 0.2)

    risk_score = round(min(risk_score, 1.0), 2)

    if risk_score >= 0.6:
        risk_level = SoleSourceRiskLevel.HIGH
    elif risk_score >= 0.3:
        risk_level = SoleSourceRiskLevel.MEDIUM
    else:
        risk_level = SoleSourceRiskLevel.LOW

    return risk_score, risk_level


# ── Tool 1: Analyze Sole-Source Justification ────────────────
@tool
def analyze_sole_source_justification(input: str = "") -> str:
    """
    Deep analysis of sole-source justification quality.
    Goes beyond pass/fail — assesses quality, identifies gaps,
    and provides specific recommendations for improvement.
    """
    extracted: ExtractedPR    = _sole_source_context["extracted"]
    vendor_match: VendorMatch = _sole_source_context["vendor_match"]
    policy: dict              = _sole_source_context["approval_policy"]

    justification = extracted.header.justification or ""
    scenario      = policy.get("procurement_scenario", "STANDARD").upper()

    non_preferred = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]
    not_found_lines = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]

    has_sole_source_keywords = any(
        kw.lower() in justification.lower()
        for kw in SOLE_SOURCE_KEYWORDS
    )
    has_strong_indicators = any(
        ind.lower() in justification.lower()
        for ind in STRONG_JUSTIFICATION_INDICATORS
    )
    has_weak_indicators = any(
        ind.lower() in justification.lower()
        for ind in WEAK_JUSTIFICATION_INDICATORS
    )

    gaps = []
    if not justification:
        gaps.append("No justification provided")
    else:
        if len(justification.strip()) < 20:
            gaps.append("Justification too short — minimum 20 characters required")
        if not has_sole_source_keywords:
            gaps.append("No sole-source keywords found — must reference why this specific vendor is required")
        if has_weak_indicators and not has_strong_indicators:
            gaps.append("Justification uses weak indicators — preference is not a valid sole-source reason")
        if not any(word in justification.lower() for word in ["because", "only", "unique", "no other", "cannot"]):
            gaps.append("Missing exclusivity reasoning — explain why no alternative exists")

    if not non_preferred and not not_found_lines:
        quality = JustificationQuality.STRONG
    elif scenario == "EMERGENCY":
        quality = JustificationQuality.ADEQUATE
    elif not justification or len(justification.strip()) < 20:
        quality = JustificationQuality.MISSING
    elif has_strong_indicators and not gaps:
        quality = JustificationQuality.STRONG
    elif has_sole_source_keywords and len(gaps) <= 1:
        quality = JustificationQuality.ADEQUATE
    elif has_weak_indicators and not has_strong_indicators:
        quality = JustificationQuality.WEAK
    else:
        quality = JustificationQuality.WEAK

    sole_source_justified = (
        not non_preferred
        or scenario == "EMERGENCY"
        or quality in (JustificationQuality.STRONG, JustificationQuality.ADEQUATE)
    )

    result = {
        "non_preferred_count":       len(non_preferred),
        "justification_text":        justification[:200],
        "justification_length":      len(justification),
        "has_sole_source_keywords":  has_sole_source_keywords,
        "has_strong_indicators":     has_strong_indicators,
        "has_weak_indicators":       has_weak_indicators,
        "justification_quality":     quality.value,
        "justification_gaps":        gaps,
        "sole_source_justified":     sole_source_justified,
        "scenario":                  scenario,
        "policy_reference":          (
            "approval_policy.yaml:sourcing_rules"
            ".require_justification_for_non_preferred_vendor"
        ),
    }
    logger.info(f"[Agent F Tool 1] sole_source: quality={quality.value}, gaps={len(gaps)}")
    return json.dumps(result)


# ── Tool 2: Enforce Bid Threshold ────────────────────────────
@tool
def enforce_bid_threshold(input: str = "") -> str:
    """
    Detailed bid threshold enforcement.
    Deterministic — based on policy thresholds.
    """
    extracted: ExtractedPR = _sole_source_context["extracted"]
    policy: dict           = _sole_source_context["approval_policy"]

    total_value         = extracted.total_value
    scenario            = policy.get("procurement_scenario", "STANDARD").upper()
    bid_required_above  = float(
        policy.get("sourcing_rules", {}).get("bid_required_above", 5000)
    )
    justification       = extracted.header.justification or ""
    framework_agreement = policy.get("framework_agreement", None)
    bid_required        = total_value > bid_required_above

    if not bid_required:
        bid_status       = BidStatus.NOT_REQUIRED
        exemption_reason = f"Total value ${total_value:.2f} is below bid threshold ${bid_required_above:.2f}"
    elif scenario == "EMERGENCY":
        bid_status       = BidStatus.WAIVED
        exemption_reason = "Emergency procurement — competitive bidding waived per policy"
    elif framework_agreement:
        bid_status       = BidStatus.WAIVED
        exemption_reason = f"Framework agreement '{framework_agreement}' covers this procurement"
    elif len(justification.strip()) > 10:
        bid_status       = BidStatus.MET
        exemption_reason = "Justification provided for sole-source procurement"
    else:
        bid_status       = BidStatus.REQUIRED
        exemption_reason = f"Competitive bidding required — total value ${total_value:.2f} exceeds ${bid_required_above:.2f}"

    bid_ok = bid_status in (BidStatus.NOT_REQUIRED, BidStatus.WAIVED, BidStatus.MET)

    result = {
        "total_value":         total_value,
        "bid_required_above":  bid_required_above,
        "bid_required":        bid_required,
        "bid_status":          bid_status.value,
        "bid_ok":              bid_ok,
        "exemption_reason":    exemption_reason,
        "scenario":            scenario,
        "framework_agreement": framework_agreement,
        "policy_reference":    "approval_policy.yaml:sourcing_rules.bid_required_above",
    }
    logger.info(f"[Agent F Tool 2] bid: status={bid_status.value}, ok={bid_ok}")
    return json.dumps(result)


# ── Tool 3: Assess Sole-Source Risk ──────────────────────────
@tool
def assess_sole_source_risk(input: str = "") -> str:
    """
    Combined risk assessment using _calculate_risk_score().
    Same function used by run_agent_f() for deterministic output.
    """
    extracted: ExtractedPR    = _sole_source_context["extracted"]
    vendor_match: VendorMatch = _sole_source_context["vendor_match"]
    policy: dict              = _sole_source_context["approval_policy"]

    risk_score, risk_level = _calculate_risk_score(extracted, vendor_match, policy)

    justification = extracted.header.justification or ""
    total_value   = extracted.total_value
    scenario      = policy.get("procurement_scenario", "STANDARD").upper()
    high_min      = float(
        policy.get("approval_thresholds", {})
              .get("high_value", {})
              .get("min_amount", 5001)
    )

    non_preferred = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]
    not_found = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]

    has_keywords = any(
        kw.lower() in justification.lower()
        for kw in SOLE_SOURCE_KEYWORDS
    )

    result = {
        "risk_score":          risk_score,
        "risk_level":          risk_level.value,
        "non_preferred_count": len(non_preferred),
        "not_found_count":     len(not_found),
        "total_value":         total_value,
        "value_band":          (
            "HIGH" if total_value >= high_min
            else "MEDIUM" if total_value >= high_min * 0.5
            else "LOW"
        ),
        "has_justification":   bool(justification),
        "has_keywords":        has_keywords,
        "scenario":            scenario,
    }
    logger.info(f"[Agent F Tool 3] risk: score={risk_score}, level={risk_level.value}")
    return json.dumps(result)


# ── LangGraph ReAct Agent ────────────────────────────────────
def _create_react_agent_graph(llm, tools):
    return create_react_agent(model=llm, tools=tools)


# ── Build Sole Source Line Check ─────────────────────────────
def _build_line_check(
    item,
    vendor_match: VendorMatch,
    approval_policy: dict,
    justification: str = "",
) -> SoleSourceLineCheck:
    bid_required_above = float(
        approval_policy.get("sourcing_rules", {}).get("bid_required_above", 5000)
    )
    scenario = approval_policy.get("procurement_scenario", "STANDARD").upper()
    high_min = float(
        approval_policy.get("approval_thresholds", {})
                       .get("high_value", {})
                       .get("min_amount", 5001)
    )

    line_vendor = next(
        (lm for lm in vendor_match.line_matches if lm.line_number == item.line_number),
        None,
    )

    is_preferred  = line_vendor.is_preferred if line_vendor else True
    vendor_status = line_vendor.status if line_vendor else VendorStatus.NOT_FOUND

    sole_source_required = not is_preferred or vendor_status in (
        VendorStatus.NON_PREFERRED,
        VendorStatus.NOT_FOUND,
    )

    has_keywords = any(
        kw.lower() in justification.lower()
        for kw in SOLE_SOURCE_KEYWORDS
    )

    if scenario == "EMERGENCY":
        quality               = JustificationQuality.ADEQUATE
        sole_source_justified = True
    elif not sole_source_required:
        quality               = JustificationQuality.STRONG
        sole_source_justified = True
    elif has_keywords:
        quality               = JustificationQuality.ADEQUATE
        sole_source_justified = True
    else:
        quality               = JustificationQuality.MISSING if not justification else JustificationQuality.WEAK
        sole_source_justified = False

    bid_required = item.total_price > bid_required_above
    if not bid_required:
        bid_status = BidStatus.NOT_REQUIRED
    elif scenario == "EMERGENCY":
        bid_status = BidStatus.WAIVED
    else:
        bid_status = BidStatus.REQUIRED if not justification else BidStatus.MET

    risk_score = 0.0
    if vendor_status == VendorStatus.NOT_FOUND:
        risk_score += 0.4
    elif not is_preferred:
        risk_score += 0.25

    if item.total_price >= high_min:
        risk_score += 0.3
    elif item.total_price >= high_min * 0.5:
        risk_score += 0.15
    else:
        risk_score += 0.05

    if is_preferred and vendor_status not in (VendorStatus.NON_PREFERRED, VendorStatus.NOT_FOUND):
        risk_score += 0.0
    elif not justification:
        risk_score += 0.3
    elif not has_keywords:
        risk_score += 0.2
    else:
        risk_score += 0.05

    if scenario == "EMERGENCY":
        risk_score = max(0.0, risk_score - 0.2)
    risk_score = round(min(risk_score, 1.0), 2)

    if risk_score >= 0.6:
        risk_level = SoleSourceRiskLevel.HIGH
    elif risk_score >= 0.3:
        risk_level = SoleSourceRiskLevel.MEDIUM
    else:
        risk_level = SoleSourceRiskLevel.LOW

    return SoleSourceLineCheck(
        line_number           = item.line_number,
        item_name             = item.item_name,
        requested_vendor      = item.requested_vendor,
        is_preferred_vendor   = is_preferred,
        total_price           = item.total_price,
        sole_source_required  = sole_source_required,
        sole_source_justified = sole_source_justified,
        justification_quality = quality,
        justification_gaps    = [] if sole_source_justified else [
            "Non-preferred vendor without adequate sole-source justification"
        ],
        bid_required          = bid_required,
        bid_status            = bid_status,
        bid_required_above    = bid_required_above,
        risk_score            = risk_score,
        risk_level            = risk_level,
        findings              = [],
    )


# ── Build Findings ────────────────────────────────────────────
def _build_sole_source_findings(
    extracted: ExtractedPR,
    vendor_match: VendorMatch,
    approval_policy: dict,
    justification_quality: JustificationQuality,
    justification_gaps: list[str],
    bid_status: BidStatus,
    risk_level: SoleSourceRiskLevel,
    risk_score: float,
) -> tuple[list[Finding], list[str]]:
    findings:          list[Finding] = []
    policy_references: list[str]     = []

    justification      = extracted.header.justification or ""
    total_value        = extracted.total_value
    bid_required_above = float(
        approval_policy.get("sourcing_rules", {}).get("bid_required_above", 5000)
    )
    scenario  = approval_policy.get("procurement_scenario", "STANDARD").upper()
    high_role = (
        approval_policy.get("approval_thresholds", {})
                       .get("high_value", {})
                       .get("approver_role", "Finance Director")
    )

    non_preferred = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]
    not_found = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]

    policy_references.append(
        "approval_policy.yaml:sourcing_rules"
        ".require_justification_for_non_preferred_vendor"
    )
    policy_references.append(
        "approval_policy.yaml:sourcing_rules.bid_required_above"
    )

    if (justification_quality in (JustificationQuality.MISSING, JustificationQuality.WEAK)
            and non_preferred
            and scenario != "EMERGENCY"):
        severity  = (
            Severity.BLOCK
            if justification_quality == JustificationQuality.MISSING
            else Severity.EXCEPTION
        )
        gaps_text = "; ".join(justification_gaps) if justification_gaps else "See analysis"
        findings.append(Finding(
            finding_id             = "SOLE-JUSTIFICATION-001",
            agent_source           = "agent_f",
            severity               = severity,
            confidence             = 0.95,
            confidence_explanation = (
                f"LLM + keyword analysis: justification quality = "
                f"{justification_quality.value}. "
                f"Gaps identified: {len(justification_gaps)}."
            ),
            description            = (
                f"Sole-source justification is {justification_quality.value}. "
                f"{len(non_preferred)} non-preferred vendor(s) detected. "
                f"Gaps: {gaps_text}."
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
                f"Provide strong sole-source justification addressing: {gaps_text}. "
                f"Justification must reference specific technical, "
                f"legal, or operational reasons for vendor exclusivity."
            )
        ))

    if bid_status == BidStatus.REQUIRED:
        findings.append(Finding(
            finding_id             = "SOLE-BID-001",
            agent_source           = "agent_f",
            severity               = Severity.EXCEPTION,
            confidence             = 1.0,
            confidence_explanation = (
                f"Deterministic: total_value ${total_value:.2f} > "
                f"bid_required_above ${bid_required_above:.2f}. "
                f"No valid exemption applies."
            ),
            description            = (
                f"Competitive bidding required but not satisfied. "
                f"PR value ${total_value:.2f} exceeds threshold "
                f"${bid_required_above:.2f}."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "approval_policy.yaml",
                page_number = 1,
                field_name  = "sourcing_rules.bid_required_above"
            )],
            recommended_action = (
                "Either: (1) provide minimum 3 competitive bids, "
                "(2) document sole-source justification with strong "
                "technical/legal reasoning, or "
                "(3) obtain emergency procurement authorization."
            )
        ))

    if risk_level == SoleSourceRiskLevel.HIGH:
        findings.append(Finding(
            finding_id             = "SOLE-RISK-001",
            agent_source           = "agent_f",
            severity               = Severity.EXCEPTION,
            confidence             = round(risk_score, 2),
            confidence_explanation = (
                f"Risk score {risk_score:.2f} based on: "
                f"vendor status ({len(non_preferred)} non-preferred, "
                f"{len(not_found)} not found), "
                f"value band (${total_value:.2f}), "
                f"justification quality ({justification_quality.value})."
            ),
            description            = (
                f"HIGH risk sole-source procurement detected. "
                f"Risk score: {risk_score:.2f}/1.0."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "vendor_match.json",
                page_number = 1,
                field_name  = "overall_status"
            )],
            recommended_action = (
                f"Mandatory escalation to {high_role}. "
                f"Independent review of sole-source decision required."
            )
        ))

    if scenario == "EMERGENCY":
        policy_references.append(
            "approval_policy.yaml:procurement_scenario=EMERGENCY"
        )
        findings.append(Finding(
            finding_id             = "SOLE-EMERGENCY-001",
            agent_source           = "agent_f",
            severity               = Severity.WARNING,
            confidence             = 1.0,
            confidence_explanation = (
                "Procurement scenario is EMERGENCY — "
                "sole-source and bid requirements waived."
            ),
            description            = (
                f"Emergency sole-source procurement for PR {extracted.pr_id}. "
                f"Bid and sole-source justification requirements waived."
            ),
            evidence_pointers      = [EvidencePointer(
                source_file = "approval_policy.yaml",
                page_number = 1,
                field_name  = "procurement_scenario"
            )],
            recommended_action = (
                f"Route immediately to {high_role} for expedited approval. "
                f"Post-procurement audit within 5 business days."
            )
        ))

    return findings, list(dict.fromkeys(policy_references))


# ── Main Function ────────────────────────────────────────────
def run_agent_f(
    run_id: str,
    bundle_data: dict,
    audit_logger: AuditLogger,
    metrics_tracker: MetricsTracker,
) -> SoleSourceCheck:
    """
    Entry point for Agent f — Standalone Sole-Source & Bid Threshold.
    
    """

    if artifact_exists(run_id, "sole_source_check.json"):
        logger.info("[Agent F] sole_source_check.json exists — skipping.")
        return SoleSourceCheck.model_validate(
            load_artifact(run_id, "sole_source_check.json")
        )

    audit_logger.log_agent_start(
        "agent_f",
        "Standalone sole-source & bid threshold analysis"
    )
    metrics_tracker.start_agent("agent_f")

    extracted = ExtractedPR.model_validate(
        load_artifact(run_id, "extracted_pr.json")
    )
    audit_logger.log_tool_call("load_artifact:extracted_pr.json")

    vendor_match = VendorMatch.model_validate(
        load_artifact(run_id, "vendor_match.json")
    )
    audit_logger.log_tool_call("load_artifact:vendor_match.json")

    approval_policy = bundle_data["approval_policy"]
    audit_logger.log_tool_call("load_bundle:approval_policy.yaml")

    scenario = approval_policy.get("procurement_scenario", "STANDARD").upper()

    # ProcurementScenario enum 
    try:
        scenario_enum = ProcurementScenario[scenario]
    except KeyError:
        scenario_enum = ProcurementScenario.STANDARD

    _set_sole_source_context(
        extracted       = extracted,
        vendor_match    = vendor_match,
        approval_policy = approval_policy,
    )
    audit_logger.log_tool_call("set_sole_source_context")

    non_preferred = [
        lm for lm in vendor_match.line_matches
        if not lm.is_preferred or lm.status == VendorStatus.NON_PREFERRED
    ]
    not_found = [
        lm for lm in vendor_match.line_matches
        if lm.status == VendorStatus.NOT_FOUND
    ]

    pr_context = (
        f"Perform deep sole-source and bid threshold analysis:\n"
        f"PR ID: {extracted.pr_id} | "
        f"Total Value: ${extracted.total_value:.2f} | "
        f"Scenario: {scenario} | "
        f"Non-preferred vendors: {len(non_preferred)} | "
        f"Vendors not found: {len(not_found)} | "
        f"Justification: {extracted.header.justification or 'None provided'}\n\n"
        f"Run ALL 3 tools in order:\n"
        f"1. analyze_sole_source_justification — assess quality and gaps\n"
        f"2. enforce_bid_threshold — check competitive bidding requirements\n"
        f"3. assess_sole_source_risk — calculate combined risk score"
    )

    logger.info(f"[Agent F] Running LangGraph ReAct agent for {extracted.pr_id}")

    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        temperature=0,
    )
    tools = [
        analyze_sole_source_justification,
        enforce_bid_threshold,
        assess_sole_source_risk,
    ]

    agent_graph = _create_react_agent_graph(llm, tools)

    try:
        agent_result = agent_graph.invoke({"messages": [("human", pr_context)]})
        messages     = agent_result.get("messages", [])
        agent_output = messages[-1].content if messages else ""
        audit_logger.log_tool_call("langgraph_react_agent")
        logger.info(f"[Agent F] LLM reasoning completed — length: {len(agent_output)}")
        if agent_output:
            logger.info(f"[Agent F] LLM summary: {agent_output[:300]}")
    except Exception as e:
        logger.error(f"[Agent F] LangGraph agent failed: {e}")
        agent_output = ""

    justification = extracted.header.justification or ""

    has_keywords = any(kw.lower() in justification.lower() for kw in SOLE_SOURCE_KEYWORDS)
    has_strong   = any(ind.lower() in justification.lower() for ind in STRONG_JUSTIFICATION_INDICATORS)
    has_weak     = any(ind.lower() in justification.lower() for ind in WEAK_JUSTIFICATION_INDICATORS)

    gaps = []
    if not justification:
        gaps.append("No justification provided")
    else:
        if len(justification.strip()) < 20:
            gaps.append("Justification too short")
        if not has_keywords:
            gaps.append("No sole-source keywords found")
        if has_weak and not has_strong:
            gaps.append("Uses weak indicators — preference is not valid")
        if not any(w in justification.lower() for w in ["because", "only", "unique", "no other", "cannot"]):
            gaps.append("Missing exclusivity reasoning")

    if not non_preferred and not not_found:
        justification_quality = JustificationQuality.STRONG
    elif scenario == "EMERGENCY":
        justification_quality = JustificationQuality.ADEQUATE
    elif not justification or len(justification.strip()) < 20:
        justification_quality = JustificationQuality.MISSING
    elif has_strong and not gaps:
        justification_quality = JustificationQuality.STRONG
    elif has_keywords and len(gaps) <= 1:
        justification_quality = JustificationQuality.ADEQUATE
    else:
        justification_quality = JustificationQuality.WEAK

    total_value         = extracted.total_value
    bid_required_above  = float(
        approval_policy.get("sourcing_rules", {}).get("bid_required_above", 5000)
    )
    framework_agreement = approval_policy.get("framework_agreement", None)
    bid_required        = total_value > bid_required_above

    if not bid_required:
        bid_status = BidStatus.NOT_REQUIRED
    elif scenario == "EMERGENCY":
        bid_status = BidStatus.WAIVED
    elif framework_agreement:
        bid_status = BidStatus.WAIVED
    elif len(justification.strip()) > 10:
        bid_status = BidStatus.MET
    else:
        bid_status = BidStatus.REQUIRED

    #  single source of truth
    risk_score, risk_level = _calculate_risk_score(extracted, vendor_match, approval_policy)

    overall_sole_source_ok = (
        not non_preferred
        or scenario == "EMERGENCY"
        or justification_quality in (JustificationQuality.STRONG, JustificationQuality.ADEQUATE)
    )
    overall_bid_ok = bid_status in (BidStatus.NOT_REQUIRED, BidStatus.WAIVED, BidStatus.MET)

    line_checks = [
        _build_line_check(item, vendor_match, approval_policy, justification)
        for item in extracted.line_items
    ]

    findings, policy_references = _build_sole_source_findings(
        extracted             = extracted,
        vendor_match          = vendor_match,
        approval_policy       = approval_policy,
        justification_quality = justification_quality,
        justification_gaps    = gaps,
        bid_status            = bid_status,
        risk_level            = risk_level,
        risk_score            = risk_score,
    )
    audit_logger.log_tool_call("build_sole_source_findings")

    sole_source_check = SoleSourceCheck(
        run_id                 = run_id,
        overall_sole_source_ok = overall_sole_source_ok,
        overall_bid_ok         = overall_bid_ok,
        overall_risk_level     = risk_level,
        overall_risk_score     = risk_score,
        justification_text     = justification or None,
        justification_quality  = justification_quality,
        llm_reasoning          = agent_output[:500] if agent_output else None,
        procurement_scenario   = scenario_enum,
        total_value            = total_value,
        line_checks            = line_checks,
        findings               = findings,
        policy_references      = policy_references,
    )

    write_sole_source_check(run_id, sole_source_check)
    audit_logger.log_tool_call("write_sole_source_check.json")

    # dynamic confidence 
    confidence = (
        1.0  if overall_sole_source_ok and overall_bid_ok
        else 0.95 if risk_level == SoleSourceRiskLevel.MEDIUM
        else 0.90
    )
    metrics_tracker.end_agent("agent_f", confidence=confidence)
    audit_logger.log_agent_end(
        output_summary=(
            f"sole_source_ok={overall_sole_source_ok} | "
            f"bid_ok={overall_bid_ok} | "
            f"risk={risk_level.value} ({risk_score:.2f}) | "
            f"justification_quality={justification_quality.value} | "
            f"findings={len(findings)} | "
            f"llm_reasoning_length={len(agent_output)}"
        )
    )

    logger.info(f"[Agent F] Completed — risk={risk_level.value} | findings={len(findings)}")
    return sole_source_check