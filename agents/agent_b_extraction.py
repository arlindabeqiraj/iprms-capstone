from pathlib import Path
from typing import Any

import fitz

from agents.llm_extractor import (
    extract_pr_from_text,
    assess_item_ambiguity,
    extract_text_from_page_image,
)
from services.file_loader import load_manifest, load_requisition, load_pr_bundle
from models import ExtractedPR
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


def _apply_llm_ambiguity_checks(extracted_pr: ExtractedPR) -> ExtractedPR:
    """
    Uses the LLM only for potentially vague items.

    This keeps costs low while improving ambiguity detection.
    """

    generic_terms = {
        "laptop",
        "monitor",
        "software",
        "equipment",
        "device",
        "accessory",
        "cable",
        "hardware",
        "office supplies",
    }

    updated_lines = []

    for line in extracted_pr.line_items:
        item_name = line.item_name.strip().lower()

        should_check = (
            item_name in generic_terms
            or len(item_name.split()) <= 2
            or line.confidence < 0.9
        )

        if not should_check:
            updated_lines.append(line)
            continue

        result = assess_item_ambiguity(
            {
                "item_name": line.item_name,
                "requested_vendor": line.requested_vendor,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
            }
        )

        is_ambiguous = result.get(
    "is_ambiguous",
    line.is_ambiguous,
)

        if is_ambiguous:
            confidence = min(
                line.confidence,
                result.get(
                    "confidence_adjustment",
                    line.confidence,
                ),
            )
        else:
            confidence = line.confidence

        updated_lines.append(
            line.model_copy(
                update={
                    "is_ambiguous": is_ambiguous,
                    "ambiguity_reason": result.get(
                        "ambiguity_reason",
                        line.ambiguity_reason,
                    ),
                    "confidence": confidence,
                }
            )
        )

    return extracted_pr.model_copy(
        update={
            "line_items": updated_lines,
        }
    )


def _extract_pdf_text_with_bbox(pdf_path: Path) -> tuple[str, list[dict]]:
    """
    Extracts text from a digital PDF and keeps best-effort bounding boxes.

    Note:
    - Works for digital/selectable-text PDFs.
    - Scanned PDFs still require OCR and are not handled here.
    """

    with fitz.open(pdf_path) as document:
        pages = []
        bbox_map = []

        for page_number, page in enumerate(document, start=1):
            blocks = page.get_text("dict").get("blocks", [])
            page_text_parts = []

            for block in blocks:
                if block.get("type") != 0:
                    continue

                for line in block.get("lines", []):
                    line_parts = []

                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        bbox = span.get("bbox")

                        if text:
                            line_parts.append(text)
                            bbox_map.append(
                                {
                                    "page_number": page_number,
                                    "text": text,
                                    "bounding_box": list(bbox) if bbox else None,
                                }
                            )

                    if line_parts:
                        page_text_parts.append(" ".join(line_parts))

            if page_text_parts:
                pages.append(
                    f"--- PAGE {page_number} ---\n"
                    + "\n".join(page_text_parts)
                )

        if not pages:
            raise ValueError(
                "No extractable text found in PDF. "
                "This may be a scanned PDF and would require OCR."
            )

        return "\n\n".join(pages), bbox_map


def _extract_pdf_text_with_ocr_fallback(pdf_path: Path) -> tuple[str, list[dict]]:
    """
    First tries normal digital PDF text extraction with bounding boxes.
    If no usable text is found, renders each page as an image and uses
    Groq vision as an OCR fallback.

    OCR fallback returns text but not exact bounding boxes.
    """

    try:
        text, bbox_map = _extract_pdf_text_with_bbox(pdf_path)

        if len(text.strip()) >= 50:
            return text, bbox_map

    except ValueError:
        pass

    
    with fitz.open(pdf_path) as document:
        ocr_pages = []

        temp_dir = pdf_path.parent / "_ocr_temp"
        temp_dir.mkdir(exist_ok=True)

        try:
            for page_number, page in enumerate(document, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                image_path = temp_dir / f"{pdf_path.stem}_page_{page_number}.png"
                pix.save(image_path)

                page_text = extract_text_from_page_image(
                    image_path=image_path,
                    page_number=page_number,
                )

                if page_text:
                    ocr_pages.append(f"--- PAGE {page_number} OCR ---\n{page_text}")

        finally:
            for file in temp_dir.glob("*.png"):
                try:
                    file.unlink()
                except OSError:
                    pass

            try:
                temp_dir.rmdir()
            except OSError:
                pass

        if not ocr_pages:
            raise ValueError(
                "No text could be extracted from PDF using digital extraction or OCR fallback."
            )

        return "\n\n".join(ocr_pages), []



def _inject_bounding_boxes(extracted_data: dict, bbox_map: list[dict]) -> dict:
    """
    Adds best-effort bounding boxes to line item evidence pointers.

    If no reliable match is found, bounding_box remains null.
    """

    for item in extracted_data.get("line_items", []):
        item_name = str(item.get("item_name", "")).strip().lower()

        for pointer in item.get("evidence_pointers", []):
            if pointer.get("bounding_box") is not None:
                continue

            pointer_page = pointer.get("page_number", 1)

            match = next(
                (
                    b
                    for b in bbox_map
                    if b.get("page_number") == pointer_page
                    and item_name
                    and item_name in str(b.get("text", "")).strip().lower()
                ),
                None,
            )

            if match:
                pointer["bounding_box"] = match.get("bounding_box")

    return extracted_data


def _enrich_line_items_from_bundle(
    requisition_data: dict,
    bundle_path: str,
) -> dict:
    """
    Ensures every line item has gl_account and currency.

    Source of truth:
    - budget_snapshot.csv by matching cost_center
    - approval_policy.yaml currency fallback
    - final defaults: gl_account='UNKNOWN', currency='EUR'
    """
    from services.file_loader import load_budget_snapshot, load_approval_policy

    # bundle_data = load_pr_bundle(bundle_path)
    budget_rows = load_budget_snapshot(bundle_path)
    approval_policy = load_approval_policy(bundle_path)

    default_currency = approval_policy.get("currency", "EUR")

    for item in requisition_data.get("line_items", []):
        item.setdefault("gl_account", "UNKNOWN")
        item.setdefault("currency", default_currency)

        item_cost_center = item.get("cost_center")

        for row in budget_rows:
            if row.get("cost_center") == item_cost_center:
                item["gl_account"] = row.get("gl_account", item["gl_account"])
                item["currency"] = row.get("currency", item["currency"])
                break

    return requisition_data


def _load_json_requisition(run_id: str, bundle_path: str) -> ExtractedPR:
    requisition_data = load_requisition(bundle_path)
    requisition_data["run_id"] = run_id

    requisition_data = _enrich_line_items_from_bundle(
        requisition_data,
        bundle_path,
    )

    extracted_pr = ExtractedPR.model_validate(requisition_data)
    extracted_pr = _validate_extracted_pr(extracted_pr)
    extracted_pr = _apply_llm_ambiguity_checks(extracted_pr)
    return extracted_pr


def _load_pdf_requisition(run_id: str, pdf_path: Path) -> ExtractedPR:
    """
    Loads PDF requisition through:
    PDF text + bbox extraction → Groq LLM → bbox injection → Pydantic validation.
    """

    text, bbox_map = _extract_pdf_text_with_ocr_fallback(pdf_path)

    extracted_data = extract_pr_from_text(
        text=text,
        run_id=run_id,
        source_file=pdf_path.name,
    )

    extracted_data["run_id"] = run_id
    extracted_data = _inject_bounding_boxes(extracted_data, bbox_map)
    extracted_data = _enrich_line_items_from_bundle(
        extracted_data,
        str(pdf_path.parent),
    )

    extracted_pr = ExtractedPR.model_validate(extracted_data)
    extracted_pr = _validate_extracted_pr(extracted_pr)
    extracted_pr = _apply_llm_ambiguity_checks(extracted_pr)
    return extracted_pr


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
        audit_logger.log_tool_call("pymupdf:extract_pdf_text_with_bbox")
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