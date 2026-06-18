from pathlib import Path

import pytest

from agents.agent_b_extraction import run_agent_b
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker


def _run_agent_b(bundle_path: str, run_id: str):
    audit_logger = AuditLogger(run_id, bundle_path)
    metrics_tracker = MetricsTracker(run_id)

    return run_agent_b(
        run_id=run_id,
        bundle_path=bundle_path,
        audit_logger=audit_logger,
        metrics_tracker=metrics_tracker,
    )


@pytest.mark.parametrize(
    "bundle_path,run_id,expected_item,expected_vendor,expected_total",
    [
        (
            "examples/pr_bundle_001_clean_auto_po",
            "TEST_AGENT_B_001",
            "Dell Latitude Laptop",
            "Dell",
            4500,
        ),
        (
            "examples/pr_bundle_002_exception_vendor",
            "TEST_AGENT_B_002",
            "Dell Latitude Laptop",
            "Random Tech Supplier",
            2550,
        ),
        (
            "examples/pr_bundle_003_budget_exceeded",
            "TEST_AGENT_B_003",
            "Dell Latitude Laptop",
            "Dell",
            18000,
        ),
        (
            "examples/pr_bundle_008_clean_small_auto_approve",
            "TEST_AGENT_B_008",
            "USB-C Cable",
            "Dell",
            120,
        ),
    ],
)
def test_agent_b_extracts_json_bundles(
    bundle_path,
    run_id,
    expected_item,
    expected_vendor,
    expected_total,
):
    extracted_pr = _run_agent_b(bundle_path, run_id)

    assert extracted_pr.total_value == expected_total
    assert len(extracted_pr.line_items) == 1

    line = extracted_pr.line_items[0]

    assert line.item_name == expected_item
    assert line.requested_vendor == expected_vendor
    assert line.total_price == expected_total
    assert line.currency == "EUR"
    assert line.gl_account


def test_agent_b_digital_pdf_extraction_has_bounding_box():
    extracted_pr = _run_agent_b(
        "examples/pr_bundle_004_pdf_extraction",
        "TEST_AGENT_B_004_DIGITAL_PDF",
    )

    assert extracted_pr.extraction_method.value == "PDF_DIRECT"

    line = extracted_pr.line_items[0]
    pointer = line.evidence_pointers[0]

    assert line.item_name == "Dell Latitude Laptop"
    assert line.currency == "EUR"
    assert line.gl_account == "GL-IT-HARDWARE"
    assert pointer.source_file == "requisition.pdf"
    assert pointer.page_number == 1
    assert pointer.bounding_box is not None


def test_agent_b_scanned_pdf_ocr_fallback_extracts_text():
    extracted_pr = _run_agent_b(
        "examples/pr_bundle_010_scanned_pdf_ocr",
        "TEST_AGENT_B_010_OCR",
    )

    assert extracted_pr.extraction_method.value == "PDF_DIRECT"

    line = extracted_pr.line_items[0]
    pointer = line.evidence_pointers[0]

    assert line.item_name == "Dell Latitude Laptop"
    assert line.quantity == 5
    assert line.unit_price == 900
    assert line.total_price == 4500
    assert line.requested_vendor == "Dell"
    assert line.currency == "EUR"
    assert line.gl_account == "GL-IT-HARDWARE"

    # Scanned PDFs use OCR/vision fallback, so exact text coordinates are not expected.
    assert pointer.source_file == "requisition.pdf"
    assert pointer.page_number == 1
    assert pointer.bounding_box is None


def test_agent_b_bundle_008_is_not_ambiguous():
    extracted_pr = _run_agent_b(
        "examples/pr_bundle_008_clean_small_auto_approve",
        "TEST_AGENT_B_008_AMBIGUITY",
    )

    line = extracted_pr.line_items[0]

    assert line.item_name == "USB-C Cable"
    assert line.is_ambiguous is False
    assert line.confidence >= 0.9


def test_agent_b_creates_extracted_pr_artifact():
    run_id = "TEST_AGENT_B_ARTIFACT"

    _run_agent_b(
        "examples/pr_bundle_001_clean_auto_po",
        run_id,
    )

    output_path = Path("runs") / run_id / "extracted_pr.json"

    assert output_path.exists()