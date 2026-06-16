"""
Agent E — Compliance & Policy Engine Tests
Covers:
  - Bundle 002 (Non-preferred vendor — exception)
  - Bundle 004 (Emergency sole-source — expedited approval)
Run: python tests/test_agent_e.py
"""

import json
import os
from services.run_manager import generate_run_id, create_run_dir, save_artifact
from services.file_loader import load_pr_bundle
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker
from agents.agent_c_budget import run_agent_c
from agents.agent_e_policy import run_agent_e
from models import (
    VendorMatch, VendorLineMatch, VendorStatus,
    BudgetCheck, BudgetStatus, BudgetLineCheck
)


def _create_vendor_match_bundle_002(run_id: str) -> None:
    """
    Simulates Agent D output for Bundle 002.
    Random Tech Supplier is NON_PREFERRED — exists but not on preferred list.
    Agent D is not executed here — preloaded for isolated testing.
    """
    vendor_match = VendorMatch(
        run_id         = run_id,
        overall_status = VendorStatus.NON_PREFERRED,
        line_matches   = [
            VendorLineMatch(
                line_number        = 1,
                item_name          = "Dell Latitude Laptop",
                matched_vendor     = "Random Tech Supplier",
                is_preferred       = False,
                catalogue_price    = None,
                requested_price    = 2550.0,
                price_variance_pct = 0.0,
                status             = VendorStatus.NON_PREFERRED,
                findings           = []
            )
        ]
    )
    save_artifact(run_id, "vendor_match.json", vendor_match.model_dump(mode="json"))
    print(f"✅ vendor_match.json preloaded (Agent D simulated — NON_PREFERRED)")


def _create_vendor_match_bundle_004(run_id: str) -> None:
    """
    Simulates Agent D output for Bundle 004.
    Emergency Tech Solutions is NOT_FOUND — not on approved vendor list.
    Emergency procurement allows unapproved vendors with post-approval.
    Agent D is not executed here — preloaded for isolated testing.
    """
    vendor_match = VendorMatch(
        run_id         = run_id,
        overall_status = VendorStatus.NOT_FOUND,
        line_matches   = [
            VendorLineMatch(
                line_number        = 1,
                item_name          = "Dell PowerEdge Server R750",
                matched_vendor     = "Emergency Tech Solutions",
                is_preferred       = False,
                catalogue_price    = None,
                requested_price    = 8500.0,
                price_variance_pct = 0.0,
                status             = VendorStatus.NOT_FOUND,
                findings           = []
            )
        ]
    )
    save_artifact(run_id, "vendor_match.json", vendor_match.model_dump(mode="json"))
    print(f"✅ vendor_match.json preloaded (Agent D simulated — NOT_FOUND)")


def test_agent_e_bundle_002():
    """
    Bundle 002 — Non-preferred vendor without sole-source justification.
    Expected: PARTIAL, sole_source_justified=False, bid_threshold_met=True.
    PR002: Dell Laptop x3, $2,550, Random Tech Supplier (NON_PREFERRED).
    """

    BUNDLE_PATH = "examples/pr_bundle_002_exception_vendor"

    # ── Setup run ────────────────────────────────────────────
    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    # ── Load bundle data ─────────────────────────────────────
    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    # ── Preload extracted_pr.json (Agent B simulated) ────────
    # Agent B is not executed here.
    # We preload extracted_pr.json so Agent E can be tested in isolation.
    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    # ── Run Agent C to produce budget_check.json ─────────────
    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C")

    # ── Preload vendor_match.json (Agent D simulated) ────────
    _create_vendor_match_bundle_002(run_id)

    # ── Create logger and tracker for Agent E ────────────────
    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    # ── Run Agent E ──────────────────────────────────────────
    print(f"\n🔄 Running Agent E...")
    result = run_agent_e(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    # ── Print results ────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"RESULT — AGENT E (Bundle 002)")
    print(f"{'='*50}")
    print(f"Overall Compliance   : {result.overall_compliance.value}")
    print(f"Procurement Scenario : {result.procurement_scenario.value}")
    print(f"Approval Authority OK: {result.approval_authority_ok}")
    print(f"Sole Source Justified: {result.sole_source_justified}")
    print(f"Bid Threshold Met    : {result.bid_threshold_met}")
    print(f"Currency             : {result.currency}")
    print(f"Findings             : {len(result.findings)}")
    print(f"Policy References    : {len(result.policy_references)}")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")
        print(f"  🔧 {f.recommended_action}")

    print(f"\n── Policy References ──")
    for ref in result.policy_references:
        print(f"  📋 {ref}")

    # ── Assertions ───────────────────────────────────────────
    print(f"\n── Assertions ──")

    assert result.overall_compliance.value in ["NON_COMPLIANT", "PARTIAL"], \
        f"❌ Expected NON_COMPLIANT or PARTIAL, got {result.overall_compliance.value}"
    print(f"✅ overall_compliance = {result.overall_compliance.value} (correct)")

    assert result.sole_source_justified is False, \
        f"❌ Expected sole_source_justified=False"
    print(f"✅ sole_source_justified = False (correct)")

    assert result.bid_threshold_met is True, \
        f"❌ Expected bid_threshold_met=True (2550 < 5000)"
    print(f"✅ bid_threshold_met = True (correct — 2550 < 5000)")

    assert result.approval_authority_ok is True, \
        f"❌ Expected approval_authority_ok=True"
    print(f"✅ approval_authority_ok = True (correct)")

    assert len(result.findings) >= 1, \
        f"❌ Expected at least 1 finding"
    print(f"✅ findings >= 1 (correct)")

    assert len(result.policy_references) >= 1, \
        f"❌ Expected at least 1 policy reference"
    print(f"✅ policy_references populated (correct)")

    assert result.currency == "EUR", \
        f"❌ Expected currency=EUR, got {result.currency}"
    print(f"✅ currency = EUR (correct)")

    assert result.procurement_scenario.value == "STANDARD", \
        f"❌ Expected STANDARD, got {result.procurement_scenario.value}"
    print(f"✅ procurement_scenario = STANDARD (correct)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 002!")


def test_agent_e_bundle_004():
    """
    Bundle 004 — Emergency Sole-Source.
    Expected: COMPLIANT or PARTIAL (emergency WARNING only),
    sole_source_justified=True (emergency exempt),
    bid_threshold_met=True (emergency waived).
    PR004: Dell Server $8,500 — Emergency Tech Solutions (NOT_FOUND).
    """

    BUNDLE_PATH = "examples/pr_bundle_004_emergency_sole_source"

    # ── Setup run ────────────────────────────────────────────
    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    # ── Load bundle data ─────────────────────────────────────
    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    # ── Preload extracted_pr.json (Agent B simulated) ────────
    # Agent B is not executed here.
    # We preload extracted_pr.json so Agent E can be tested in isolation.
    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    # ── Run Agent C to produce budget_check.json ─────────────
    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C")

    # ── Preload vendor_match.json (Agent D simulated) ────────
    _create_vendor_match_bundle_004(run_id)

    # ── Create logger and tracker for Agent E ────────────────
    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    # ── Run Agent E ──────────────────────────────────────────
    print(f"\n🔄 Running Agent E...")
    result = run_agent_e(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    # ── Print results ────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"RESULT — AGENT E (Bundle 004)")
    print(f"{'='*50}")
    print(f"Overall Compliance   : {result.overall_compliance.value}")
    print(f"Procurement Scenario : {result.procurement_scenario.value}")
    print(f"Approval Authority OK: {result.approval_authority_ok}")
    print(f"Sole Source Justified: {result.sole_source_justified}")
    print(f"Bid Threshold Met    : {result.bid_threshold_met}")
    print(f"Currency             : {result.currency}")
    print(f"Findings             : {len(result.findings)}")
    print(f"Policy References    : {len(result.policy_references)}")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")
        print(f"  🔧 {f.recommended_action}")

    print(f"\n── Policy References ──")
    for ref in result.policy_references:
        print(f"  📋 {ref}")

    # ── Assertions ───────────────────────────────────────────
    print(f"\n── Assertions ──")

    # Scenario must be EMERGENCY
    assert result.procurement_scenario.value == "EMERGENCY", \
        f"❌ Expected EMERGENCY, got {result.procurement_scenario.value}"
    print(f"✅ procurement_scenario = EMERGENCY (correct)")

    # Sole source justified — emergency exemption
    assert result.sole_source_justified is True, \
        f"❌ Expected sole_source_justified=True (emergency exempt)"
    print(f"✅ sole_source_justified = True (correct — emergency exempt)")

    # Bid threshold met — emergency waives bid
    assert result.bid_threshold_met is True, \
        f"❌ Expected bid_threshold_met=True (emergency waived)"
    print(f"✅ bid_threshold_met = True (correct — emergency waived)")

    # Approval authority OK
    assert result.approval_authority_ok is True, \
        f"❌ Expected approval_authority_ok=True"
    print(f"✅ approval_authority_ok = True (correct)")

    # Must have EMERGENCY finding
    emergency_findings = [
        f for f in result.findings
        if f.finding_id == "COMPLIANCE-EMERGENCY-001"
    ]
    assert len(emergency_findings) >= 1, \
        f"❌ Expected COMPLIANCE-EMERGENCY-001 finding"
    print(f"✅ COMPLIANCE-EMERGENCY-001 finding exists (correct)")

    # No BLOCK findings — emergency allows unapproved vendors
    block_findings = [
        f for f in result.findings
        if f.severity.value == "BLOCK"
    ]
    assert len(block_findings) == 0, \
        f"❌ Expected no BLOCK findings in emergency, got {len(block_findings)}"
    print(f"✅ no BLOCK findings (correct — emergency exemption)")

    # Policy references populated
    assert len(result.policy_references) >= 1, \
        f"❌ Expected at least 1 policy reference"
    print(f"✅ policy_references populated (correct)")

    # Currency from policy
    assert result.currency == "EUR", \
        f"❌ Expected currency=EUR"
    print(f"✅ currency = EUR (correct)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 004 (Agent E Emergency)!")


def test_agent_e_bundle_005():
    """
    Bundle 005 — Budget Borderline.
    Expected: COMPLIANT (only WARNING findings),
    COMPLIANCE-BUDGET-002 warning from Agent C integration.
    PR005: Dell Laptop x10 = $9,200 vs available $10,000 (BORDERLINE).
    """

    BUNDLE_PATH = "examples/pr_bundle_005_budget_borderline"

    # ── Setup run ────────────────────────────────────────────
    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    # ── Preload extracted_pr.json (Agent B simulated) ────────
    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    # ── Run Agent C ──────────────────────────────────────────
    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C — BORDERLINE")

    # ── Preload vendor_match.json (Agent D simulated) ────────
    # Dell is preferred vendor — no vendor issues
    vendor_match = VendorMatch(
        run_id         = run_id,
        overall_status = VendorStatus.MATCHED,
        line_matches   = [
            VendorLineMatch(
                line_number        = 1,
                item_name          = "Dell Latitude Laptop",
                matched_vendor     = "Dell",
                is_preferred       = True,
                catalogue_price    = 900.0,
                requested_price    = 920.0,
                price_variance_pct = 2.2,
                status             = VendorStatus.MATCHED,
                findings           = []
            )
        ]
    )
    save_artifact(run_id, "vendor_match.json", vendor_match.model_dump(mode="json"))
    print(f"✅ vendor_match.json preloaded (Agent D simulated — MATCHED)")

    # ── Create logger and tracker ────────────────────────────
    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    # ── Run Agent E ──────────────────────────────────────────
    print(f"\n🔄 Running Agent E...")
    result = run_agent_e(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    # ── Print results ────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"RESULT — AGENT E (Bundle 005)")
    print(f"{'='*50}")
    print(f"Overall Compliance   : {result.overall_compliance.value}")
    print(f"Procurement Scenario : {result.procurement_scenario.value}")
    print(f"Approval Authority OK: {result.approval_authority_ok}")
    print(f"Sole Source Justified: {result.sole_source_justified}")
    print(f"Bid Threshold Met    : {result.bid_threshold_met}")
    print(f"Currency             : {result.currency}")
    print(f"Findings             : {len(result.findings)}")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")
        print(f"  🔧 {f.recommended_action}")

    # ── Assertions ───────────────────────────────────────────
    print(f"\n── Assertions ──")

    # COMPLIANT — only WARNING findings, no BLOCK or EXCEPTION
    assert result.overall_compliance.value == "COMPLIANT", \
        f"❌ Expected COMPLIANT, got {result.overall_compliance.value}"
    print(f"✅ overall_compliance = COMPLIANT (correct — only WARNINGs)")

    # No BLOCK findings
    block_findings = [f for f in result.findings if f.severity.value == "BLOCK"]
    assert len(block_findings) == 0, \
        f"❌ Expected no BLOCK findings"
    print(f"✅ no BLOCK findings (correct)")

    # No EXCEPTION findings
    exception_findings = [f for f in result.findings if f.severity.value == "EXCEPTION"]
    assert len(exception_findings) == 0, \
        f"❌ Expected no EXCEPTION findings"
    print(f"✅ no EXCEPTION findings (correct)")

    # COMPLIANCE-BUDGET-002 warning from Agent C integration
    budget_warnings = [
        f for f in result.findings
        if f.finding_id == "COMPLIANCE-BUDGET-002"
    ]
    assert len(budget_warnings) >= 1, \
        f"❌ Expected COMPLIANCE-BUDGET-002 finding"
    print(f"✅ COMPLIANCE-BUDGET-002 warning exists (correct — budget borderline)")

    # Sole source OK — Dell is preferred
    assert result.sole_source_justified is True, \
        f"❌ Expected sole_source_justified=True (Dell is preferred)"
    print(f"✅ sole_source_justified = True (correct — Dell preferred)")

    # Bid threshold — 9,200 > 5,000 but justification exists
    assert result.bid_threshold_met is True, \
        f"❌ Expected bid_threshold_met=True"
    print(f"✅ bid_threshold_met = True (correct)")

    # Approval authority OK
    assert result.approval_authority_ok is True, \
        f"❌ Expected approval_authority_ok=True"
    print(f"✅ approval_authority_ok = True (correct)")

    # Currency
    assert result.currency == "EUR", \
        f"❌ Expected currency=EUR"
    print(f"✅ currency = EUR (correct)")

    # Scenario STANDARD
    assert result.procurement_scenario.value == "STANDARD", \
        f"❌ Expected STANDARD"
    print(f"✅ procurement_scenario = STANDARD (correct)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 005 (Agent E)!")


if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("❌ GROQ_API_KEY not set")
        exit(1)
    test_agent_e_bundle_002()
    print("\n" + "=" * 60 + "\n")
    test_agent_e_bundle_004()
    print("\n" + "=" * 60 + "\n")
    test_agent_e_bundle_005()