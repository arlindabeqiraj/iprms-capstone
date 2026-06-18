"""
Agent F — Standalone Sole-Source & Bid Threshold Tests
Covers:
  - Bundle 002 (Non-preferred vendor — exception)
  - Bundle 004 (Emergency sole-source — expedited approval)
  - Bundle 001 (Clean auto-PO — preferred vendor, low value band)
  - Bundle BID  (NON_PREFERRED + total_value > 2000 — bid threshold exceeded)

"""

import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.run_manager import generate_run_id, create_run_dir, save_artifact
from services.file_loader import load_pr_bundle
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker
from agents.agent_c_budget import run_agent_c
from agents.agent_f_sole_source import run_agent_f
from models import VendorMatch, VendorLineMatch, VendorStatus
from models.sole_source_models import (
    JustificationQuality, BidStatus, SoleSourceRiskLevel
)
from models.policy_models import ProcurementScenario


def _create_vendor_match_bundle_002(run_id: str) -> None:
    """
    Simulates Agent D output for Bundle 002.
    Random Tech Supplier is NON_PREFERRED.
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


def test_agent_f_bundle_002():
    """
    Bundle 002 — Non-preferred vendor without sole-source justification.
    Expected:
    - overall_sole_source_ok = False
    - justification_quality = WEAK
    - risk_level = MEDIUM or HIGH
    - findings >= 1
    PR002: Dell Laptop x3 = $2,550 — Random Tech Supplier (NON_PREFERRED).
    """

    BUNDLE_PATH = "examples/pr_bundle_002_exception_vendor"

    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C")

    _create_vendor_match_bundle_002(run_id)

    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    print(f"\n🔄 Running Agent F...")
    result = run_agent_f(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    print(f"\n{'='*50}")
    print(f"RESULT — AGENT F (Bundle 002)")
    print(f"{'='*50}")
    print(f"Overall Sole Source OK : {result.overall_sole_source_ok}")
    print(f"Overall Bid OK         : {result.overall_bid_ok}")
    print(f"Risk Level             : {result.overall_risk_level.value}")
    print(f"Risk Score             : {result.overall_risk_score}")
    print(f"Justification Quality  : {result.justification_quality.value}")
    print(f"Procurement Scenario   : {result.procurement_scenario.value}")
    print(f"Total Value            : ${result.total_value:.2f}")
    print(f"Findings               : {len(result.findings)}")
    print(f"Policy References      : {len(result.policy_references)}")

    print(f"\n── Line Checks ──")
    for lc in result.line_checks:
        print(f"  Line {lc.line_number} | {lc.item_name} | "
              f"preferred={lc.is_preferred_vendor} | "
              f"sole_source_required={lc.sole_source_required} | "
              f"justified={lc.sole_source_justified} | "
              f"quality={lc.justification_quality.value} | "
              f"bid={lc.bid_status.value} | "
              f"risk={lc.risk_level.value} ({lc.risk_score})")
        if lc.justification_gaps:
            for gap in lc.justification_gaps:
                print(f"    ⚠️  Gap: {gap}")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")
        print(f"  🔧 {f.recommended_action}")

    print(f"\n── Policy References ──")
    for ref in result.policy_references:
        print(f"  📋 {ref}")

    if result.llm_reasoning:
        print(f"\n── LLM Reasoning (first 200 chars) ──")
        print(f"  {result.llm_reasoning[:200]}")

    print(f"\n── Assertions ──")

    assert result.overall_sole_source_ok is False, \
        f"❌ Expected sole_source_ok=False"
    print(f"✅ overall_sole_source_ok = False (correct)")

    assert result.overall_bid_ok is True, \
        f"❌ Expected bid_ok=True (2550 < 5000)"
    print(f"✅ overall_bid_ok = True (correct — 2550 < 5000)")

    assert result.overall_risk_level.value in ["MEDIUM", "HIGH"], \
        f"❌ Expected MEDIUM or HIGH risk, got {result.overall_risk_level.value}"
    print(f"✅ risk_level = {result.overall_risk_level.value} (correct)")

    assert result.justification_quality.value == "WEAK", \
        f"❌ Expected WEAK, got {result.justification_quality.value}"
    print(f"✅ justification_quality = WEAK (correct — non-preferred, no sole-source keywords)")

    assert len(result.findings) >= 1, \
        f"❌ Expected at least 1 finding"
    print(f"✅ findings >= 1 (correct)")

    assert len(result.policy_references) >= 1, \
        f"❌ Expected at least 1 policy reference"
    print(f"✅ policy_references populated (correct)")

    assert len(result.line_checks) == 1, \
        f"❌ Expected 1 line check, got {len(result.line_checks)}"
    print(f"✅ line_checks = 1 (correct)")

    assert result.line_checks[0].is_preferred_vendor is False, \
        f"❌ Expected is_preferred_vendor=False"
    print(f"✅ is_preferred_vendor = False (correct)")

    assert result.line_checks[0].sole_source_required is True, \
        f"❌ Expected sole_source_required=True"
    print(f"✅ sole_source_required = True (correct)")

    assert result.line_checks[0].bid_status == BidStatus.NOT_REQUIRED, \
        f"❌ Expected bid_status=NOT_REQUIRED"
    print(f"✅ bid_status = NOT_REQUIRED (correct — 2550 < 5000)")

    assert result.total_value == 2550.0, \
        f"❌ Expected total_value=2550.0, got {result.total_value}"
    print(f"✅ total_value = 2550.0 (correct)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 002 (Agent F)!")


def test_agent_f_bundle_004():
    """
    Bundle 004 — Emergency Sole-Source.
    Expected: sole_source_ok=True (emergency exempt),
    bid_ok=True (waived), risk MEDIUM or LOW (emergency reduces risk),
    SOLE-EMERGENCY-001 WARNING finding.
    PR004: Dell Server $8,500 — Emergency Tech Solutions (NOT_FOUND).
    """

    BUNDLE_PATH = "examples/pr_bundle_004_emergency_sole_source"

    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C")

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

    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    print(f"\n🔄 Running Agent F...")
    result = run_agent_f(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    print(f"\n{'='*50}")
    print(f"RESULT — AGENT F (Bundle 004)")
    print(f"{'='*50}")
    print(f"Overall Sole Source OK : {result.overall_sole_source_ok}")
    print(f"Overall Bid OK         : {result.overall_bid_ok}")
    print(f"Risk Level             : {result.overall_risk_level.value}")
    print(f"Risk Score             : {result.overall_risk_score}")
    print(f"Justification Quality  : {result.justification_quality.value}")
    print(f"Procurement Scenario   : {result.procurement_scenario.value}")
    print(f"Total Value            : ${result.total_value:.2f}")
    print(f"Findings               : {len(result.findings)}")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")
        print(f"  🔧 {f.recommended_action}")

    print(f"\n── Assertions ──")

    assert result.overall_sole_source_ok is True, \
        f"❌ Expected sole_source_ok=True (emergency exempt)"
    print(f"✅ overall_sole_source_ok = True (correct — emergency exempt)")

    assert result.overall_bid_ok is True, \
        f"❌ Expected bid_ok=True (emergency waived)"
    print(f"✅ overall_bid_ok = True (correct — emergency waived)")

    assert result.procurement_scenario.value == "EMERGENCY", \
        f"❌ Expected EMERGENCY, got {result.procurement_scenario.value}"
    print(f"✅ procurement_scenario = EMERGENCY (correct)")

    emergency_findings = [
        f for f in result.findings
        if f.finding_id == "SOLE-EMERGENCY-001"
    ]
    assert len(emergency_findings) >= 1, \
        f"❌ Expected SOLE-EMERGENCY-001 finding"
    print(f"✅ SOLE-EMERGENCY-001 finding exists (correct)")

    block_findings = [
        f for f in result.findings
        if f.severity.value == "BLOCK"
    ]
    assert len(block_findings) == 0, \
        f"❌ Expected no BLOCK findings in emergency"
    print(f"✅ no BLOCK findings (correct — emergency exemption)")

    assert result.total_value == 8500.0, \
        f"❌ Expected 8500.0, got {result.total_value}"
    print(f"✅ total_value = 8500.0 (correct)")

    assert result.justification_quality.value in ["ADEQUATE", "STRONG"], \
        f"❌ Expected ADEQUATE or STRONG (emergency), got {result.justification_quality.value}"
    print(f"✅ justification_quality = {result.justification_quality.value} (correct — emergency)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 004 (Agent F Emergency)!")


def test_agent_f_bundle_001():
    """
    Bundle 001 — Clean Auto-PO, preferred vendor, low value band.
    Expected: sole_source_ok=True (Dell preferred),
    bid_ok=True (4,500 < 5,000), risk=LOW, justification=STRONG,
    zero EXCEPTION/BLOCK findings.
    PR001: Dell Laptop x5 = $4,500 — Dell (PREFERRED).
    """

    BUNDLE_PATH = "examples/pr_bundle_001_clean_auto_po"

    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C")

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
                requested_price    = 900.0,
                price_variance_pct = 0.0,
                status             = VendorStatus.MATCHED,
                findings           = []
            )
        ]
    )
    save_artifact(run_id, "vendor_match.json", vendor_match.model_dump(mode="json"))
    print(f"✅ vendor_match.json preloaded (Agent D simulated — PREFERRED)")

    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    print(f"\n🔄 Running Agent F...")
    result = run_agent_f(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    print(f"\n{'='*50}")
    print(f"RESULT — AGENT F (Bundle 001)")
    print(f"{'='*50}")
    print(f"Overall Sole Source OK : {result.overall_sole_source_ok}")
    print(f"Overall Bid OK         : {result.overall_bid_ok}")
    print(f"Risk Level             : {result.overall_risk_level.value}")
    print(f"Risk Score             : {result.overall_risk_score}")
    print(f"Justification Quality  : {result.justification_quality.value}")
    print(f"Procurement Scenario   : {result.procurement_scenario.value}")
    print(f"Total Value            : ${result.total_value:.2f}")
    print(f"Findings               : {len(result.findings)}")

    print(f"\n── Line Checks ──")
    for lc in result.line_checks:
        print(f"  Line {lc.line_number} | {lc.item_name} | "
              f"preferred={lc.is_preferred_vendor} | "
              f"sole_source_required={lc.sole_source_required} | "
              f"justified={lc.sole_source_justified} | "
              f"quality={lc.justification_quality.value} | "
              f"bid={lc.bid_status.value} | "
              f"risk={lc.risk_level.value} ({lc.risk_score})")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")

    print(f"\n── Assertions ──")

    assert result.overall_sole_source_ok is True, \
        f"❌ Expected sole_source_ok=True (Dell preferred)"
    print(f"✅ overall_sole_source_ok = True (correct — Dell preferred)")

    assert result.overall_bid_ok is True, \
        f"❌ Expected bid_ok=True (4500 < 5000)"
    print(f"✅ overall_bid_ok = True (correct — 4500 < 5000)")

    assert result.overall_risk_level.value == "LOW", \
        f"❌ Expected LOW risk, got {result.overall_risk_level.value}"
    print(f"✅ risk_level = LOW (correct — preferred vendor, no risk penalty)")

    assert result.justification_quality.value == "STRONG", \
        f"❌ Expected STRONG, got {result.justification_quality.value}"
    print(f"✅ justification_quality = STRONG (correct — preferred vendor)")

    bad_findings = [
        f for f in result.findings
        if f.severity.value in ["BLOCK", "EXCEPTION"]
    ]
    assert len(bad_findings) == 0, \
        f"❌ Expected no BLOCK/EXCEPTION findings"
    print(f"✅ no BLOCK/EXCEPTION findings (correct)")

    assert result.line_checks[0].is_preferred_vendor is True, \
        f"❌ Expected is_preferred_vendor=True"
    print(f"✅ is_preferred_vendor = True (correct)")

    assert result.line_checks[0].sole_source_required is False, \
        f"❌ Expected sole_source_required=False (preferred vendor)"
    print(f"✅ sole_source_required = False (correct — Dell preferred)")

    assert result.line_checks[0].bid_status == BidStatus.NOT_REQUIRED, \
        f"❌ Expected bid_status=NOT_REQUIRED"
    print(f"✅ bid_status = NOT_REQUIRED (correct — 4500 < 5000)")

    assert result.total_value == 4500.0, \
        f"❌ Expected 4500.0, got {result.total_value}"
    print(f"✅ total_value = 4500.0 (correct — low value band)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 001 (Agent F — Low Value Band)!")


def test_agent_f_bid_threshold_exceeded():
    """
     Scenario: NON_PREFERRED vendor with total_value > 2000 and no justification.

     Expected:
       - overall_bid_ok = False (bid is REQUIRED but not satisfied)
       - overall_sole_source_ok = False (non-preferred vendor with no justification)
       - bid_status = REQUIRED
       - SOLE-BID-001 finding is present
       - risk_level = HIGH (NON_PREFERRED vendor + high procurement value + no justification)
    """

    BUNDLE_PATH = "examples/pr_bundle_002_exception_vendor"

    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    bundle_data = load_pr_bundle(BUNDLE_PATH)
    bundle_data["approval_policy"]["sourcing_rules"]["bid_required_above"] = 2000.0
    print(f"✅ Bundle loaded: {BUNDLE_PATH} (bid_required_above=2000)")

    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    extracted_pr["header"]["justification"] = ""
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (justification='' — bid REQUIRED)")

    audit_logger_c    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker_c = MetricsTracker(run_id)
    run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger_c,
        metrics_tracker = metrics_tracker_c,
    )
    print(f"✅ budget_check.json produced by Agent C")

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
    print(f"✅ vendor_match.json preloaded (NON_PREFERRED, 2550 > 2000 → bid REQUIRED)")

    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    print(f"\n🔄 Running Agent F...")
    result = run_agent_f(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    print(f"\n{'='*50}")
    print(f"RESULT — AGENT F (Bid Threshold Exceeded)")
    print(f"{'='*50}")
    print(f"Overall Sole Source OK : {result.overall_sole_source_ok}")
    print(f"Overall Bid OK         : {result.overall_bid_ok}")
    print(f"Risk Level             : {result.overall_risk_level.value}")
    print(f"Risk Score             : {result.overall_risk_score}")
    print(f"Justification Quality  : {result.justification_quality.value}")
    print(f"Procurement Scenario   : {result.procurement_scenario.value}")
    print(f"Total Value            : ${result.total_value:.2f}")
    print(f"Findings               : {len(result.findings)}")

    print(f"\n── Line Checks ──")
    for lc in result.line_checks:
        print(f"  Line {lc.line_number} | {lc.item_name} | "
              f"preferred={lc.is_preferred_vendor} | "
              f"bid={lc.bid_status.value} | "
              f"risk={lc.risk_level.value} ({lc.risk_score})")

    print(f"\n── Findings ──")
    for f in result.findings:
        print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
        print(f"  📝 {f.description}")
        print(f"  🔧 {f.recommended_action}")

    print(f"\n── Assertions ──")

    assert result.overall_bid_ok is False, \
        f"❌ Expected bid_ok=False (bid REQUIRED, nuk plotësohet)"
    print(f"✅ overall_bid_ok = False (correct — bid REQUIRED)")

    assert result.overall_sole_source_ok is False, \
        f"❌ Expected sole_source_ok=False (non-preferred, pa justifikim)"
    print(f"✅ overall_sole_source_ok = False (correct)")

    assert result.overall_risk_level.value == "HIGH", \
        f"❌ Expected HIGH risk, got {result.overall_risk_level.value}"
    print(f"✅ risk_level = HIGH (correct — NON_PREFERRED + high value + no justification)")

    bid_findings = [
        f for f in result.findings
        if f.finding_id == "SOLE-BID-001"
    ]
    assert len(bid_findings) >= 1, \
        f"❌ Expected SOLE-BID-001 finding"
    print(f"✅ SOLE-BID-001 finding exists (correct)")

    assert result.line_checks[0].bid_status == BidStatus.REQUIRED, \
        f"❌ Expected bid_status=REQUIRED, got {result.line_checks[0].bid_status}"
    print(f"✅ bid_status = REQUIRED (correct — 2550 > 2000)")

    assert result.total_value == 2550.0, \
        f"❌ Expected 2550.0, got {result.total_value}"
    print(f"✅ total_value = 2550.0 (correct)")

    print(f"\n🎉 ALL TESTS PASSED — Bid Threshold Exceeded (Agent F)!")


if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("❌ GROQ_API_KEY not set — export GROQ_API_KEY=your_key")
        exit(1)

    print("\n" + "=" * 60)
    print("Agent F — Test Suite (4 skenarë)")
    print("=" * 60)

    tests = [
        ("Bundle 002 — Non-preferred vendor",    test_agent_f_bundle_002),
        ("Bundle 004 — Emergency sole-source",   test_agent_f_bundle_004),
        ("Bundle 001 — Preferred vendor",        test_agent_f_bundle_001),
        ("Bid threshold exceeded",               test_agent_f_bid_threshold_exceeded),
    ]

    passed = 0
    failed = 0

    for name, test in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)