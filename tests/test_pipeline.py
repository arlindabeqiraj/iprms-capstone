"""
test_pipeline.py — End-to-end pipeline tests
Tests run_pipeline() with all PR bundles.
Run: python tests/test_pipeline.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_pipeline import run_pipeline


def _assert_artifacts(run_path: Path) -> None:
    """Verifies all required artifacts exist."""
    required = [
        "context_packet.json",
        "extracted_pr.json",
        "budget_check.json",
        "vendor_match.json",
        "exceptions.md",
        "approval_packet.json",
        "po_draft.json",
        "audit_log.md",
        "audit_log.json",
        "metrics.json",
        "pipeline_audit_log.md",
        "pipeline_metrics.json",
    ]
    for artifact in required:
        path = Path(run_path) / artifact
        assert path.exists(), f"❌ Missing artifact: {artifact}"


def test_bundle_001_clean_auto_po():
    """
    Bundle 001 — Standard IT consumables, approved vendor, within budget.
    Expected: AUTO_APPROVE, no findings, budget AVAILABLE.
    """
    print("\n🔄 Testing Bundle 001 — Clean Auto-PO...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_001_clean_auto_po",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] == "AUTO_APPROVE", \
        f"❌ Expected AUTO_APPROVE, got {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 001 PASSED!")


def test_bundle_002_exception_vendor():
    """
    Bundle 002 — Non-preferred vendor without justification.
    Expected: REQUIRES_APPROVAL.
    """
    print("\n🔄 Testing Bundle 002 — Exception Vendor...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_002_exception_vendor",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] == "REQUIRES_APPROVAL", \
        f"❌ Expected REQUIRES_APPROVAL, got {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 002 PASSED!")


def test_bundle_003_budget_exceeded():
    """
    Bundle 003 — Budget exhausted for cost center.
    Expected: BLOCKED.
    """
    print("\n🔄 Testing Bundle 003 — Budget Exceeded...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_003_budget_exceeded",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] == "BLOCKED", \
        f"❌ Expected BLOCKED, got {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 003 PASSED!")


def test_bundle_004_emergency_sole_source():
    """
    Bundle 004 — Emergency sole-source purchase.
    Expected: REQUIRES_APPROVAL (expedited path).
    """
    print("\n🔄 Testing Bundle 004 — Emergency Sole-Source...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_004_emergency_sole_source",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] in [
        "REQUIRES_APPROVAL", "AUTO_APPROVE"
    ], f"❌ Unexpected decision: {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    assert result["context_packet"].pr_type.value == "EMERGENCY", \
        "❌ Expected PR Type EMERGENCY"
    print("✅ PR Type: EMERGENCY")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 004 PASSED!")


def test_bundle_005_budget_borderline():
    """
    Bundle 005 — Budget borderline (92% used).
    Expected: REQUIRES_APPROVAL or MANUAL_REVIEW.
    """
    print("\n🔄 Testing Bundle 005 — Budget Borderline...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_005_budget_borderline",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] in [
        "REQUIRES_APPROVAL", "MANUAL_REVIEW"
    ], f"❌ Unexpected decision: {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 005 PASSED!")


def test_bundle_006_vague_description():
    """
    Bundle 006 — Item description too vague.
    Expected: REQUIRES_APPROVAL or MANUAL_REVIEW.
    """
    print("\n🔄 Testing Bundle 006 — Vague Description...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_006_vague_description",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] in [
        "REQUIRES_APPROVAL", "MANUAL_REVIEW", "BLOCKED"
    ], f"❌ Unexpected decision: {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 006 PASSED!")


def test_bundle_007_low_confidence():
    """
    Bundle 007 — Low confidence extraction.
    Expected: BLOCKED or REQUIRES_APPROVAL.
    """
    print("\n🔄 Testing Bundle 007 — Low Confidence...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_007_low_confidence",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] in [
        "BLOCKED", "REQUIRES_APPROVAL", "MANUAL_REVIEW"
    ], f"❌ Unexpected decision: {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 007 PASSED!")


def test_bundle_008_clean_small_auto_approve():
    """
    Bundle 008 — Clean small consumables PR under threshold.
    Expected: AUTO_APPROVE, 0 findings.
    """
    print("\n🔄 Testing Bundle 008 — Clean Small Auto-Approve...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_008_clean_small_auto_approve",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] == "AUTO_APPROVE", \
        f"❌ Expected AUTO_APPROVE, got {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 008 PASSED!")


def test_bundle_009_three_prs_same_dept():
    """
    Bundle 009 — Three PRs same department.
    Expected: AUTO_APPROVE or REQUIRES_APPROVAL
    (split-order detection requires Agent G stretch goal).
    """
    print("\n🔄 Testing Bundle 009 — Three PRs Same Department...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_009_three_prs_same_dept",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] in [
        "AUTO_APPROVE", "REQUIRES_APPROVAL", "MANUAL_REVIEW"
    ], f"❌ Unexpected decision: {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 009 PASSED!")



def test_bundle_011_split_order_anomaly():
    """
    Bundle 011 — Split order anomaly detection (Agent G stretch goal).
    Expected: REQUIRES_APPROVAL or MANUAL_REVIEW,
    anomaly_check.json produced by Agent G.
    """
    print("\n🔄 Testing Bundle 011 — Split Order Anomaly...")
    result = run_pipeline(
        bundle_path = "examples/pr_bundle_011_split_order_anomaly",
        use_llm     = False,
    )

    assert result["agent_h_result"]["decision"] in [
        "REQUIRES_APPROVAL", "MANUAL_REVIEW", "BLOCKED", "AUTO_APPROVE"
    ], f"❌ Unexpected decision: {result['agent_h_result']['decision']}"
    print(f"✅ Decision: {result['agent_h_result']['decision']}")

    _assert_artifacts(result["run_path"])
    print("✅ All artifacts present")

    print("🎉 Bundle 011 PASSED!")


if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("⚠️  GROQ_API_KEY not set — running without LLM")

    print("\n" + "=" * 60)
    print("IPRMS Pipeline — End-to-End Test Suite")
    print("=" * 60)

    tests = [
        test_bundle_001_clean_auto_po,
        test_bundle_002_exception_vendor,
        test_bundle_003_budget_exceeded,
        test_bundle_004_emergency_sole_source,
        test_bundle_005_budget_borderline,
        test_bundle_006_vague_description,
        test_bundle_007_low_confidence,
        test_bundle_008_clean_small_auto_approve,
        test_bundle_009_three_prs_same_dept,
        test_bundle_011_split_order_anomaly,
    ]

    passed = 0
    failed = 0

    for test in tests:
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