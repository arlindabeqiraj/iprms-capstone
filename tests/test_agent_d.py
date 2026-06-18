from pathlib import Path

from agents.agent_b_extraction import run as run_b
from agents.agent_d_vendor import run as run_d


def _run_b_then_d(bundle_path: str, run_id: str):
    state = {
        "run_id": run_id,
        "bundle_path": bundle_path,
        "context_packet": None,
        "extracted_pr": None,
        "budget_check": None,
        "vendor_match": None,
        "compliance_findings": None,
        "approval_packet": None,
        "po_draft": None,
        "metrics": None,
        "error": None,
    }

    state = run_b(state)
    assert state["error"] is None

    state = run_d(state)
    assert state["error"] is None

    return state


def test_agent_d_matches_approved_preferred_vendor_bundle_001():
    state = _run_b_then_d(
        "examples/pr_bundle_001_clean_auto_po",
        "TEST_AGENT_D_001",
    )

    vendor_match = state["vendor_match"]

    assert vendor_match["overall_status"] == "MATCHED"
    assert vendor_match["line_matches"][0]["matched_vendor"] == "Dell"
    assert vendor_match["line_matches"][0]["is_preferred"] is True
    assert vendor_match["line_matches"][0]["catalogue_price"] == 900.0
    assert vendor_match["line_matches"][0]["price_variance_pct"] == 0.0
    assert vendor_match["line_matches"][0]["findings"] == []


def test_agent_d_detects_non_approved_vendor_bundle_002():
    state = _run_b_then_d(
        "examples/pr_bundle_002_exception_vendor",
        "TEST_AGENT_D_002",
    )

    vendor_match = state["vendor_match"]
    line = vendor_match["line_matches"][0]

    assert vendor_match["overall_status"] == "NON_PREFERRED"
    assert line["matched_vendor"] == "Random Tech Supplier"
    assert line["is_preferred"] is False
    assert len(line["findings"]) >= 1

    finding_ids = [finding["finding_id"] for finding in line["findings"]]

    assert "VENDOR_NOT_APPROVED_LINE_1" in finding_ids


def test_agent_d_matches_bundle_003_even_if_budget_exceeded():
    state = _run_b_then_d(
        "examples/pr_bundle_003_budget_exceeded",
        "TEST_AGENT_D_003",
    )

    vendor_match = state["vendor_match"]
    line = vendor_match["line_matches"][0]

    assert vendor_match["overall_status"] == "MATCHED"
    assert line["matched_vendor"] == "Dell"
    assert line["catalogue_price"] == 900.0
    assert line["requested_price"] == 900.0
    assert line["price_variance_pct"] == 0.0


def test_agent_d_matches_clean_small_bundle_008():
    state = _run_b_then_d(
        "examples/pr_bundle_008_clean_small_auto_approve",
        "TEST_AGENT_D_008",
    )

    vendor_match = state["vendor_match"]
    line = vendor_match["line_matches"][0]

    assert vendor_match["overall_status"] == "MATCHED"
    assert line["matched_vendor"] == "Dell"
    assert line["item_name"] == "USB-C Cable"
    assert line["catalogue_price"] == 12.0
    assert line["requested_price"] == 12.0
    assert line["findings"] == []


def test_agent_d_creates_vendor_match_artifact():
    run_id = "TEST_AGENT_D_ARTIFACT"

    _run_b_then_d(
        "examples/pr_bundle_001_clean_auto_po",
        run_id,
    )

    output_path = Path("runs") / run_id / "vendor_match.json"

    assert output_path.exists()


def test_agent_d_finding_uses_correct_evidence_source_for_bundle_002():
    state = _run_b_then_d(
        "examples/pr_bundle_002_exception_vendor",
        "TEST_AGENT_D_EVIDENCE",
    )

    findings = state["vendor_match"]["line_matches"][0]["findings"]

    assert findings

    vendor_finding = next(
        finding
        for finding in findings
        if finding["finding_id"] == "VENDOR_NOT_APPROVED_LINE_1"
    )

    pointer = vendor_finding["evidence_pointers"][0]

    assert pointer["source_file"] == "approved_vendors.csv"
    assert pointer["field_name"] == "line_items[0].requested_vendor"