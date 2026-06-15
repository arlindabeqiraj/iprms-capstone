from typing import Any

from models import ExtractedPR
from services.file_loader import load_requisition
from services.output_writer import write_extracted_pr
from services.run_manager import create_run_dir


def _validate_extracted_pr(extracted_pr: ExtractedPR) -> ExtractedPR:
    """
    Adds lightweight validation for synthetic PR bundle extraction.

    Checks:
    - line total = quantity * unit_price
    - total_value = sum of line totals
    - missing vendor
    - ambiguous item names
    - overall confidence recalculation
    """

    updated_lines = []
    notes = list(extracted_pr.aggregation_notes)
    confidence_scores = []
    calculated_total = 0.0

    for line in extracted_pr.line_items:
        expected_line_total = round(line.quantity * line.unit_price, 2)
        actual_line_total = round(line.total_price, 2)

        line_updates = {}

        if actual_line_total != expected_line_total:
            notes.append(
                f"Line {line.line_number}: corrected total_price from "
                f"{actual_line_total} to {expected_line_total}."
            )
            line_updates["total_price"] = expected_line_total

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

        line_updates["is_ambiguous"] = is_ambiguous
        line_updates["ambiguity_reason"] = ambiguity_reason
        line_updates["confidence"] = confidence

        updated_line = line.model_copy(update=line_updates)

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


def run(state: dict[str, Any]) -> dict[str, Any]:
    """
    Agent B - Item Extraction

    Current implemented path:
    - Uses requisition.json from the PR Bundle.
    - Validates it against the ExtractedPR Pydantic model.
    - Checks item totals, total PR value, ambiguity, and confidence.
    - Writes extracted_pr.json.

    Requirement coverage:
    - Structured item extraction: supported through ExtractedPR.
    - Confidence scoring: supported through line confidence and overall confidence.
    - Validation: supported through Pydantic + custom total/ambiguity checks.
    - Multi-line aggregation: supported by summing all line_items.
    - Bounding boxes: supported by EvidencePointer model; JSON bundles use null bounding_box.
    - PDF/web input: planned extension point. The output must still be ExtractedPR.
    """

    try:
        run_id = state["run_id"]
        bundle_path = state["bundle_path"]

        create_run_dir(run_id)

        requisition_data = load_requisition(bundle_path)

        # Pipeline run_id is the source of truth.
        requisition_data["run_id"] = run_id

        extracted_pr = ExtractedPR.model_validate(requisition_data)
        extracted_pr = _validate_extracted_pr(extracted_pr)

        write_extracted_pr(run_id, extracted_pr)

        state["extracted_pr"] = extracted_pr.model_dump(mode="json")
        state["error"] = None
        return state

    except Exception as exc:
        state["error"] = f"Agent B extraction failed: {exc}"
        return state