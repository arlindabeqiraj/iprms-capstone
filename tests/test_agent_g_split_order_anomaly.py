"""
Agent G — Split-Order & Anomaly Detection Tests
Covers:
  - Cross-bundle split order detection
  - Different cost centers (no grouping)
  - Low confidence line item detection
  - Stable finding IDs (determinism)
Run: python tests/test_agent_g.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from agents.agent_g_split_order_anomaly import run_agent_g
from models.anomaly_models import AnomalyStatus, AnomalyType


def _write_bundle(
    root: Path,
    bundle_name: str,
    pr_id: str,
    department: str,
    cost_center: str,
    request_date: str,
    item_name: str,
    total_price: float,
    confidence: float = 0.96,
) -> Path:
    bundle_path = root / bundle_name
    bundle_path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "bundle_id": bundle_name.upper(),
        "description": "Synthetic bundle for Agent G test",
        "expected_decision": "REQUIRES_APPROVAL",
        "requisition_file": "requisition.json",
        "budget_file": "budget_snapshot.csv",
        "vendor_file": "approved_vendors.csv",
        "catalogue_file": "catalogue_pricing.csv",
        "policy_file": "approval_policy.yaml",
        "cost_center_file": "cost_center_mapping.csv",
        "created_at": request_date,
    }

    requisition = {
        "pr_id": pr_id,
        "currency": "EUR",
        "header": {
            "pr_number": pr_id,
            "request_date": request_date,
            "requester": "Test User",
            "department": department,
            "cost_center": cost_center,
            "justification": "Synthetic test data",
        },
        "line_items": [
            {
                "line_number": 1,
                "item_name": item_name,
                "quantity": 1,
                "unit_price": total_price,
                "total_price": total_price,
                "cost_center": cost_center,
                "gl_account": "IT-EQUIPMENT",
                "requested_vendor": "Approved Vendor",
                "confidence": confidence,
            }
        ],
        "total_value": total_price,
        "overall_confidence": confidence,
    }

    policy = {
        "procurement_scenario": "STANDARD",
        "currency": "EUR",
        "sourcing_rules": {
            "bid_required_above": 5000,
        },
    }

    (bundle_path / "manifest.yaml").write_text(
        yaml.safe_dump(manifest),
        encoding="utf-8",
    )
    (bundle_path / "requisition.json").write_text(
        json.dumps(requisition, indent=2),
        encoding="utf-8",
    )
    (bundle_path / "approval_policy.yaml").write_text(
        yaml.safe_dump(policy),
        encoding="utf-8",
    )

    return bundle_path


def test_agent_g_detects_cross_bundle_split_order():
    """
    Dy bundle me të njëjtin item, të njëjtin department dhe cost center,
    brenda 7 ditëve — duhet të detektohet split order.
    Expected: overall_status=EXCEPTION, split_order_detected=True.
    """
    tmp_path = Path(tempfile.mkdtemp())
    try:
        examples_root = tmp_path / "examples"

        current_bundle = _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_current",
            pr_id="PR100",
            department="IT",
            cost_center="CC100",
            request_date="2026-06-10T10:00:00",
            item_name="Dell Latitude Laptop",
            total_price=3000,
        )

        _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_peer",
            pr_id="PR101",
            department="IT",
            cost_center="CC100",
            request_date="2026-06-12T10:00:00",
            item_name="Dell Latitude Laptop",
            total_price=2500,
        )

        result = run_agent_g(
            run_id="TEST_AGENT_G_SPLIT_ORDER",
            bundle_path=current_bundle,
            examples_root=examples_root,
        )

        print(f"\n{'='*50}")
        print(f"RESULT — AGENT G (Cross-Bundle Split Order)")
        print(f"{'='*50}")
        print(f"Overall Status      : {result.overall_status.value}")
        print(f"Split Order Detected: {result.split_order_detected}")
        print(f"Anomaly Score       : {result.anomaly_score}")
        print(f"Findings            : {len(result.findings)}")
        for f in result.findings:
            print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
            print(f"  📝 {f.description[:100]}")

        print(f"\n── Assertions ──")

        assert result.overall_status == AnomalyStatus.EXCEPTION, \
            f"❌ Expected EXCEPTION, got {result.overall_status.value}"
        print(f"✅ overall_status = EXCEPTION (correct)")

        assert result.split_order_detected is True, \
            f"❌ Expected split_order_detected=True"
        print(f"✅ split_order_detected = True (correct)")

        assert result.findings, \
            f"❌ Expected at least 1 finding"
        print(f"✅ findings >= 1 (correct)")

        assert any(
            group.anomaly_type == AnomalyType.SPLIT_ORDER_CROSS_BUNDLE
            for group in result.anomaly_groups
        ), f"❌ Expected SPLIT_ORDER_CROSS_BUNDLE anomaly group"
        print(f"✅ SPLIT_ORDER_CROSS_BUNDLE detected (correct)")

        output_path = Path("runs") / "TEST_AGENT_G_SPLIT_ORDER" / "anomaly_check.json"
        assert output_path.exists(), f"❌ anomaly_check.json not written"
        print(f"✅ anomaly_check.json written (correct)")

        print(f"\n🎉 ALL TESTS PASSED — Cross-Bundle Split Order!")

    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_agent_g_does_not_group_different_cost_centers():
    """
    Dy bundle me të njëjtin item dhe department, por cost center të ndryshëm.
    Expected: split_order_detected=False — cost center i ndryshëm nuk grupohet.
    """
    tmp_path = Path(tempfile.mkdtemp())
    try:
        examples_root = tmp_path / "examples"

        current_bundle = _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_current_cc100",
            pr_id="PR110",
            department="IT",
            cost_center="CC100",
            request_date="2026-06-10T10:00:00",
            item_name="Dell Latitude Laptop",
            total_price=3000,
        )

        _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_peer_cc200",
            pr_id="PR111",
            department="IT",
            cost_center="CC200",
            request_date="2026-06-12T10:00:00",
            item_name="Dell Latitude Laptop",
            total_price=3000,
        )

        result = run_agent_g(
            run_id="TEST_AGENT_G_DIFFERENT_CC",
            bundle_path=current_bundle,
            examples_root=examples_root,
        )

        print(f"\n{'='*50}")
        print(f"RESULT — AGENT G (Different Cost Centers)")
        print(f"{'='*50}")
        print(f"Overall Status      : {result.overall_status.value}")
        print(f"Split Order Detected: {result.split_order_detected}")
        print(f"Findings            : {len(result.findings)}")

        print(f"\n── Assertions ──")

        assert result.split_order_detected is False, \
            f"❌ Expected split_order_detected=False (different cost centers)"
        print(f"✅ split_order_detected = False (correct — different cost centers)")

        assert not any(
            group.anomaly_type == AnomalyType.SPLIT_ORDER_CROSS_BUNDLE
            for group in result.anomaly_groups
        ), f"❌ Expected no SPLIT_ORDER_CROSS_BUNDLE"
        print(f"✅ no SPLIT_ORDER_CROSS_BUNDLE (correct)")

        print(f"\n🎉 ALL TESTS PASSED — Different Cost Centers!")

    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_agent_g_detects_low_confidence_line_item():
    """
    Bundle me confidence=0.55 — nën threshold 0.70.
    Expected: overall_status=WARNING, LOW_CONFIDENCE_EXTRACTION detected.
    """
    tmp_path = Path(tempfile.mkdtemp())
    try:
        examples_root = tmp_path / "examples"

        current_bundle = _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_low_confidence",
            pr_id="PR200",
            department="IT",
            cost_center="CC100",
            request_date="2026-06-10T10:00:00",
            item_name="Network Switch",
            total_price=800,
            confidence=0.55,
        )

        result = run_agent_g(
            run_id="TEST_AGENT_G_LOW_CONFIDENCE",
            bundle_path=current_bundle,
            examples_root=examples_root,
        )

        print(f"\n{'='*50}")
        print(f"RESULT — AGENT G (Low Confidence)")
        print(f"{'='*50}")
        print(f"Overall Status      : {result.overall_status.value}")
        print(f"Split Order Detected: {result.split_order_detected}")
        print(f"Anomaly Score       : {result.anomaly_score}")
        print(f"Findings            : {len(result.findings)}")
        for f in result.findings:
            print(f"  ⚠️  [{f.severity.value}] {f.finding_id}")
            print(f"  📝 {f.description[:100]}")

        print(f"\n── Assertions ──")

        assert result.overall_status == AnomalyStatus.WARNING, \
            f"❌ Expected WARNING, got {result.overall_status.value}"
        print(f"✅ overall_status = WARNING (correct)")

        assert result.split_order_detected is False, \
            f"❌ Expected split_order_detected=False"
        print(f"✅ split_order_detected = False (correct)")

        assert any(
            group.anomaly_type == AnomalyType.LOW_CONFIDENCE_EXTRACTION
            for group in result.anomaly_groups
        ), f"❌ Expected LOW_CONFIDENCE_EXTRACTION"
        print(f"✅ LOW_CONFIDENCE_EXTRACTION detected (correct)")

        print(f"\n🎉 ALL TESTS PASSED — Low Confidence Line Item!")

    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_agent_g_finding_ids_are_stable():
    """
    I njëjti bundle ekzekutuar dy herë — finding IDs duhet të jenë identike.
    Verifikон determinizmin e hashlib.sha1.
    """
    tmp_path = Path(tempfile.mkdtemp())
    try:
        examples_root = tmp_path / "examples"

        current_bundle = _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_stable_current",
            pr_id="PR300",
            department="IT",
            cost_center="CC100",
            request_date="2026-06-10T10:00:00",
            item_name="Dell Latitude Laptop",
            total_price=3000,
        )

        _write_bundle(
            root=examples_root,
            bundle_name="pr_bundle_stable_peer",
            pr_id="PR301",
            department="IT",
            cost_center="CC100",
            request_date="2026-06-12T10:00:00",
            item_name="Dell Latitude Laptop",
            total_price=2500,
        )

        first = run_agent_g(
            run_id="TEST_AGENT_G_STABLE_1",
            bundle_path=current_bundle,
            examples_root=examples_root,
        )

        second = run_agent_g(
            run_id="TEST_AGENT_G_STABLE_2",
            bundle_path=current_bundle,
            examples_root=examples_root,
        )

        first_ids  = [f.finding_id for f in first.findings]
        second_ids = [f.finding_id for f in second.findings]

        print(f"\n{'='*50}")
        print(f"RESULT — AGENT G (Stable Finding IDs)")
        print(f"{'='*50}")
        print(f"Run 1 finding IDs: {first_ids}")
        print(f"Run 2 finding IDs: {second_ids}")

        print(f"\n── Assertions ──")

        assert first_ids == second_ids, \
            f"❌ Finding IDs not stable: {first_ids} != {second_ids}"
        print(f"✅ finding IDs identical across runs (correct — hashlib.sha1)")

        print(f"\n🎉 ALL TESTS PASSED — Stable Finding IDs!")

    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Agent G — Test Suite (4 skenarë)")
    print("=" * 60)

    tests = [
        ("Cross-bundle split order",     test_agent_g_detects_cross_bundle_split_order),
        ("Different cost centers",       test_agent_g_does_not_group_different_cost_centers),
        ("Low confidence line item",     test_agent_g_detects_low_confidence_line_item),
        ("Stable finding IDs",           test_agent_g_finding_ids_are_stable),
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