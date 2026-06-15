"""
Agent C — Budget Validation Tests
Covers: Bundle 003 (EXCEEDED) and Bundle 001 (AVAILABLE)

"""

import json
from services.run_manager import generate_run_id, create_run_dir, save_artifact
from services.file_loader import load_pr_bundle
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker
from agents.agent_c_budget import run_agent_c


def test_agent_c_bundle_003():
    """
    Bundle 003 — Budget Exceeded.
    Expected: overall_status=EXCEEDED, BLOCK finding, capex_required=True.
    PR003: Dell Latitude Laptop x20 = $18,000 vs available $10,000.
    """

    BUNDLE_PATH = "examples/pr_bundle_003_budget_exceeded"

    # ── Setup run ────────────────────────────────────────────
    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    # ── Load bundle data ─────────────────────────────────────
    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    # ── Integration test setup ───────────────────────────────
    # Agent B is not executed here.
    # We preload extracted_pr.json so Agent C can be tested in isolation.
    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    # ── Create logger and tracker ────────────────────────────
    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    # ── Run Agent C ──────────────────────────────────────────
    print(f"\n🔄 Running Agent C...")
    result = run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    # ── Print results ────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"RESULT — AGENT C (Bundle 003)")
    print(f"{'='*50}")
    print(f"Overall Status : {result.overall_status.value}")
    print(f"Total Requested: {result.total_requested:.2f}")
    print(f"Total Available: {result.total_available:.2f}")
    print(f"Lines Checked  : {len(result.line_checks)}")

    print(f"\n── Line Checks ──")
    for lc in result.line_checks:
        print(f"  Line {lc.line_number} | {lc.cost_center} | "
              f"requested={lc.requested_amount:.2f} | "
              f"available={lc.available_budget:.2f} | "
              f"status={lc.status.value} | "
              f"period_cap_ok={lc.period_cap_ok} | "
              f"capex={lc.capex_required}")
        for finding in lc.findings:
            print(f"    ⚠️  [{finding.severity.value}] {finding.finding_id}")
            print(f"    📝 {finding.description}")
            print(f"    🔧 {finding.recommended_action}")

    # ── Assertions ───────────────────────────────────────────
    print(f"\n── Assertions ──")

    # Overall status
    assert result.overall_status.value == "EXCEEDED", \
        f"❌ Expected EXCEEDED, got {result.overall_status.value}"
    print(f"✅ overall_status = EXCEEDED (correct)")

    # Budget logic: requested must exceed available
    assert result.total_requested > result.total_available, \
        f"❌ Expected requested > available"
    print(f"✅ total_requested > total_available (correct)")

    # Exact values for this specific bundle
    assert result.total_requested == 18000, \
        f"❌ Expected 18000, got {result.total_requested}"
    print(f"✅ total_requested = 18000 (correct)")

    assert result.total_available == 10000, \
        f"❌ Expected 10000, got {result.total_available}"
    print(f"✅ total_available = 10000 (correct)")

    # Line checks
    assert len(result.line_checks) == 1, \
        f"❌ Expected 1 line check, got {len(result.line_checks)}"
    print(f"✅ line_checks = 1 (correct)")

    # Finding exists and is BLOCK
    assert len(result.line_checks[0].findings) == 1, \
        f"❌ Expected 1 finding, got {len(result.line_checks[0].findings)}"
    print(f"✅ finding exists (correct)")

    assert result.line_checks[0].findings[0].severity.value == "BLOCK", \
        f"❌ Expected BLOCK severity"
    print(f"✅ severity = BLOCK (correct)")

    # Period cap: $18,000 > $15,000 period_cap → should be False
    assert result.line_checks[0].period_cap_ok is False, \
        f"❌ Expected period_cap_ok=False (18000 > 15000)"
    print(f"✅ period_cap_ok = False (correct — 18000 exceeds period cap 15000)")

    # Capex: $18,000 >= $5,001 threshold from approval_policy.yaml → True
    assert result.line_checks[0].capex_required is True, \
        f"❌ Expected capex_required=True (18000 >= 5001 threshold)"
    print(f"✅ capex_required = True (correct — exceeds capex threshold)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 003!")


def test_agent_c_bundle_001():
    """
    Bundle 001 — Clean Auto-PO.
    Expected: overall_status=AVAILABLE, no findings, all lines clean.
    PR001: Logitech Keyboard x5 + Mouse x5 = $650 vs available $10,000.
    """

    BUNDLE_PATH = "examples/pr_bundle_001_clean_auto_po"

    # ── Setup run ────────────────────────────────────────────
    run_id = generate_run_id()
    create_run_dir(run_id)
    print(f"\n✅ Run ID: {run_id}")

    # ── Load bundle data ─────────────────────────────────────
    bundle_data = load_pr_bundle(BUNDLE_PATH)
    print(f"✅ Bundle loaded: {BUNDLE_PATH}")

    # ── Integration test setup ───────────────────────────────
    # Agent B is not executed here.
    # We preload extracted_pr.json so Agent C can be tested in isolation.
    with open(f"{BUNDLE_PATH}/requisition.json", encoding="utf-8") as f:
        extracted_pr = json.load(f)
    save_artifact(run_id, "extracted_pr.json", extracted_pr)
    print(f"✅ extracted_pr.json preloaded (Agent B simulated)")

    # ── Create logger and tracker ────────────────────────────
    audit_logger    = AuditLogger(run_id, BUNDLE_PATH)
    metrics_tracker = MetricsTracker(run_id)

    # ── Run Agent C ──────────────────────────────────────────
    print(f"\n🔄 Running Agent C...")
    result = run_agent_c(
        run_id          = run_id,
        bundle_data     = bundle_data,
        audit_logger    = audit_logger,
        metrics_tracker = metrics_tracker,
    )

    # ── Print results ────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"RESULT — AGENT C (Bundle 001)")
    print(f"{'='*50}")
    print(f"Overall Status : {result.overall_status.value}")
    print(f"Total Requested: {result.total_requested:.2f}")
    print(f"Total Available: {result.total_available:.2f}")
    print(f"Lines Checked  : {len(result.line_checks)}")

    print(f"\n── Line Checks ──")
    for lc in result.line_checks:
        print(f"  Line {lc.line_number} | {lc.cost_center} | "
              f"requested={lc.requested_amount:.2f} | "
              f"available={lc.available_budget:.2f} | "
              f"status={lc.status.value} | "
              f"findings={len(lc.findings)}")

    # ── Assertions ───────────────────────────────────────────
    print(f"\n── Assertions ──")

    # Overall status
    assert result.overall_status.value == "AVAILABLE", \
        f"❌ Expected AVAILABLE, got {result.overall_status.value}"
    print(f"✅ overall_status = AVAILABLE (correct)")

    # Budget logic: requested must be within available
    assert result.total_requested < result.total_available, \
        f"❌ Expected requested < available"
    print(f"✅ total_requested < total_available (correct)")

    # Exact values for this specific bundle
    assert result.total_requested == 4500, \
        f"❌ Expected 4500, got {result.total_requested}"
    print(f"✅ total_requested = 4500 (correct)")

    assert result.total_available == 10000, \
        f"❌ Expected 10000, got {result.total_available}"
    print(f"✅ total_available = 10000 (correct)")

    assert len(result.line_checks) == 1, \
        f"❌ Expected 1 line check, got {len(result.line_checks)}"
    print(f"✅ line_checks = 1 (correct)")

    # No findings for clean PR
    assert all(len(lc.findings) == 0 for lc in result.line_checks), \
        f"❌ Expected no findings for AVAILABLE status"
    print(f"✅ no findings produced (correct)")

    # All lines AVAILABLE
    assert all(lc.status.value == "AVAILABLE" for lc in result.line_checks), \
        f"❌ Expected all lines AVAILABLE"
    print(f"✅ all lines = AVAILABLE (correct)")

    # Period cap: $400 and $250 both < $15,000 period_cap → True
    assert all(lc.period_cap_ok is True for lc in result.line_checks), \
        f"❌ Expected period_cap_ok=True for all lines"
    print(f"✅ period_cap_ok = True for all lines (correct)")

    # Capex: $400 and $250 both < $5,001 threshold → False
    assert all(lc.capex_required is False for lc in result.line_checks), \
        f"❌ Expected capex_required=False (below capex threshold)"
    print(f"✅ capex_required = False for all lines (correct)")

    print(f"\n🎉 ALL TESTS PASSED — Bundle 001!")


if __name__ == "__main__":
    test_agent_c_bundle_003()
    print("\n" + "=" * 60 + "\n")
    test_agent_c_bundle_001()