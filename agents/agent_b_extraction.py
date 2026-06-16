from pathlib import Path
from typing import Any

import fitz

from agents.llm_extractor import extract_pr_from_text
from models import ExtractedPR
from services.file_loader import load_manifest, load_requisition
from services.output_writer import write_extracted_pr
from services.run_manager import (
    create_run_dir,
    artifact_exists,
    load_artifact,
)
from services.audit_logger import AuditLogger
from services.metrics_tracker import MetricsTracker


def _validate_extracted_pr(extracted_pr: ExtractedPR) -> ExtractedPR:
    updated_lines = []
    notes = list(extracted_pr.aggregation_notes)
    confidence_scores = []
    calculated_total = 0.0

    for line in extracted_pr.line_items:
        expected_total = round(line.quantity * line.unit_price, 2)
        actual_total = round(line.total_price, 2)

        updates = {}

        if actual_total != expected_total:
            notes.append(
                f"Line {line.line_number}: corrected total_price from "
                f"{actual_total} to {expected_total}."
            )
            updates["total_price"] = expected_total

        is_ambiguous = line.is_ambiguous
        ambiguity_reason = line.ambiguity_reason
        confidence = line.confidence

        if not line.item_name or len(line.item_name.strip()) < 3:
            is_ambiguous = True
            ambiguity_reason = "Item description is missing or too short."
            confidence = min(confidence, 0.6)

        if not line.requested_vendor:
            is_ambiguous = True
            ambiguity_reason = "Requested vendor is missing."
            confidence = min(confidence, 0.7)

        updates["is_ambiguous"] = is_ambiguous
        updates["ambiguity_reason"] = ambiguity_reason
        updates["confidence"] = confidence

        updated_line = line.model_copy(update=updates)

        updated_lines.append(updated_line)
        confidence_scores.append(updated_line.confidence)
        calculated_total += updated_line.total_price

    calculated_total = round(calculated_total, 2)

    if round(extracted_pr.total_value, 2) != calculated_total:
        notes.append(
            f"Header total_value corrected from {extracted_pr.total_value} "
            f"to {calculated_total}."
        )

    overall_confidence = (
        round(sum(confidence_scores) / len(confidence_scores), 2)
        if confidence_scores
        else 0.0
    )

    return extracted_pr.model_copy(
        update={
            "line_items": updated_lines,
            "total_value": calculated_total,
            "overall_confidence": overall_confidence,
            "aggregation_notes": notes,
        }
    )


def _extract_pdf_text(pdf_path: Path) -> str:
    document = fitz.open(pdf_path)
    pages = []

    for page_number, page in enumerate(document, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"--- PAGE {page_number} ---\n{text}")

    if not pages:
        raise ValueError(
            "No extractable text found in PDF. "
            "This may be a scanned PDF and would require OCR."
        )

    return "\n\n".join(pages)


def _load_json_requisition(run_id: str, bundle_path: str) -> ExtractedPR:
    requisition_data = load_requisition(bundle_path)
    requisition_data["run_id"] = run_id

    extracted_pr = ExtractedPR.model_validate(requisition_data)
    return _validate_extracted_pr(extracted_pr)


def _load_pdf_requisition(run_id: str, requisition_path: Path) -> ExtractedPR:
    pdf_text = _extract_pdf_text(requisition_path)

    llm_data = extract_pr_from_text(
        text=pdf_text,
        run_id=run_id,
        source_file=requisition_path.name,
    )

    llm_data["run_id"] = run_id

    extracted_pr = ExtractedPR.model_validate(llm_data)
    return _validate_extracted_pr(extracted_pr)


def run_agent_b(
    run_id: str,
    bundle_path: str,
    audit_logger: AuditLogger,
    metrics_tracker: MetricsTracker,
) -> ExtractedPR:
    """
    Agent B — AI-enabled Item Extraction.

    Supports:
    - JSON requisition from PR Bundle
    - PDF requisition using PyMuPDF + Groq LLM

    Output:
    - runs/<run_id>/extracted_pr.json
    """

    create_run_dir(run_id)

    if artifact_exists(run_id, "extracted_pr.json"):
        return ExtractedPR.model_validate(
            load_artifact(run_id, "extracted_pr.json")
        )

    audit_logger.log_agent_start(
        "agent_b",
        "Extract requisition fields and line items into ExtractedPR."
    )
    metrics_tracker.start_agent("agent_b")

    manifest = load_manifest(bundle_path)
    requisition_path = Path(bundle_path) / manifest.requisition_file

    if not requisition_path.exists():
        raise FileNotFoundError(f"Requisition file not found: {requisition_path}")

    file_extension = requisition_path.suffix.lower()

    if file_extension == ".json":
        audit_logger.log_tool_call("load_requisition:requisition.json")
        extracted_pr = _load_json_requisition(run_id, bundle_path)

    elif file_extension == ".pdf":
        audit_logger.log_tool_call("pymupdf:extract_pdf_text")
        audit_logger.log_tool_call("groq_llm:extract_pr_from_text")
        extracted_pr = _load_pdf_requisition(run_id, requisition_path)

    else:
        raise ValueError(
            f"Unsupported requisition format: {file_extension}. "
            "Supported formats are .json and .pdf."
        )

    write_extracted_pr(run_id, extracted_pr)
    audit_logger.log_tool_call("write_extracted_pr:extracted_pr.json")

    metrics_tracker.end_agent(
        "agent_b",
        confidence=extracted_pr.overall_confidence,
    )

    audit_logger.log_agent_end(
        output_summary=(
            f"extraction_method={extracted_pr.extraction_method.value} | "
            f"line_items={len(extracted_pr.line_items)} | "
            f"total_value={extracted_pr.total_value:.2f} | "
            f"overall_confidence={extracted_pr.overall_confidence}"
        )
    )

    return extracted_pr


def run(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compatibility wrapper for LangGraph/manual state-based tests.
    """

    try:
        run_id = state["run_id"]
        bundle_path = state["bundle_path"]

        audit_logger = state.get("audit_logger") or AuditLogger(run_id, bundle_path)
        metrics_tracker = state.get("metrics_tracker") or MetricsTracker(run_id)

        extracted_pr = run_agent_b(
            run_id=run_id,
            bundle_path=bundle_path,
            audit_logger=audit_logger,
            metrics_tracker=metrics_tracker,
        )

        state["extracted_pr"] = extracted_pr.model_dump(mode="json")
        state["error"] = None
        return state

    except Exception as exc:
        state["error"] = f"Agent B extraction failed: {exc}"
        return state