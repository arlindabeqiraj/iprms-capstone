import json
import shutil
from pathlib import Path

from agents.agent_h_orchestrator import run_agent_h


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def test_agent_h_generates_final_artifacts_for_vendor_exception():
    run_id = "TEST_AGENT_H_VENDOR_EXCEPTION"
    run_dir = Path("runs") / run_id

    if run_dir.exists():
        shutil.rmtree(run_dir)

    run_dir.mkdir(parents=True)

    _write_json(
        run_dir / "context_packet.json",
        {
            "run_id": run_id,
            "pr_type": "STANDARD",
            "requester": "Jane Smith",
            "department": "IT",
            "cost_center": "CC100",
            "total_estimated_value": 2550.0,
            "bundle_files": [
                "requisition.json",
                "budget_snapshot.csv",
                "approved_vendors.csv",
                "catalogue_pricing.csv",
                "approval_policy.yaml",
                "cost_center_mapping.csv",
            ],
            "evidence_index": [
                {
                    "item_name": "Dell Latitude Laptop",
                    "source_file": "requisition.json",
                    "page_number": 1,
                }
            ],
            "risk_flags": ["NON_PREFERRED_VENDOR"],
            "risk_score": 0.25,
            "classification_confidence": 1.0,
        },
    )

    _write_json(
        run_dir / "extracted_pr.json",
        {
            "run_id": run_id,
            "pr_id": "PR002",
            "requester": "Jane Smith",
            "department": "IT",
            "currency": "EUR",
            "line_items": [
                {
                    "line_number": 1,
                    "item_name": "Dell Latitude Laptop",
                    "quantity": 3,
                    "unit_price": 850,
                    "total_price": 2550,
                    "cost_center": "CC100",
                    "requested_vendor": "Random Tech Supplier",
                    "gl_account": "IT-EQUIPMENT",
                }
            ],
            "total_value": 2550,
            "overall_confidence": 0.96,
        },
    )

    _write_json(
        run_dir / "budget_check.json",
        {
            "run_id": run_id,
            "overall_status": "AVAILABLE",
            "line_checks": [],
            "total_requested": 2550,
            "total_available": 10000,
            "findings": [],
        },
    )

    _write_json(
        run_dir / "vendor_match.json",
        {
            "run_id": run_id,
            "overall_status": "NON_PREFERRED",
            "line_matches": [
                {
                    "line_number": 1,
                    "item_name": "Dell Latitude Laptop",
                    "matched_vendor": "Random Tech Supplier",
                    "is_preferred": False,
                    "requested_price": 850,
                    "catalogue_price": 850,
                    "price_variance_pct": 0,
                    "status": "NON_PREFERRED",
                    "findings": [
                        {
                            "finding_id": "VENDOR-001",
                            "agent_source": "Agent D",
                            "severity": "EXCEPTION",
                            "confidence": 0.95,
                            "confidence_explanation": "Requested vendor is not preferred.",
                            "description": "Requested vendor is non-preferred.",
                            "evidence_pointers": [
                                {
                                    "source_file": "approved_vendors.csv",
                                    "page_number": 1,
                                    "field_name": "vendor_name",
                                    "bounding_box": None,
                                }
                            ],
                            "recommended_action": "Route to procurement manager for approval.",
                        }
                    ],
                }
            ],
        },
    )

    result = run_agent_h(
        run_id=run_id,
        bundle_path="examples/pr_bundle_002_exception_vendor",
    )

    assert result["run_id"] == run_id
    assert result["decision"] == "REQUIRES_APPROVAL"
    assert result["total_findings"] >= 1

    assert (run_dir / "exceptions.md").exists()
    assert (run_dir / "approval_packet.json").exists()
    assert (run_dir / "po_draft.json").exists()
    assert (run_dir / "audit_log.md").exists()
    assert (run_dir / "audit_log.json").exists()
    assert (run_dir / "metrics.json").exists()

    approval_packet = json.loads((run_dir / "approval_packet.json").read_text())
    assert approval_packet["decision"] == "REQUIRES_APPROVAL"
    assert approval_packet["human_review_required"] is True

    po_draft = json.loads((run_dir / "po_draft.json").read_text())
    assert po_draft["status"] == "PENDING_APPROVAL"
    assert po_draft["currency"] == "EUR"