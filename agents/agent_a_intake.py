from pathlib import Path
from typing import Any

from models.context_models import ContextPacket, LineItemRef
from models.shared_models import BundleManifest, PRType, RiskFlag
from services.file_loader import load_pr_bundle
from services.output_writer import write_context_packet
from services.run_manager import create_run_dir


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    return str(value).strip().lower() in {"true", "yes", "1", "y"}


def _add_risk_flag(flags: list[RiskFlag], flag: RiskFlag) -> None:
    if flag not in flags:
        flags.append(flag)


def _get_header(requisition: dict[str, Any]) -> dict[str, Any]:
    header = requisition.get("header")

    if isinstance(header, dict):
        return header

    return {}


def _get_requisition_field(
    requisition: dict[str, Any],
    field_name: str,
    default: str = "",
) -> str:
    root_value = requisition.get(field_name)

    if root_value not in (None, ""):
        return str(root_value).strip()

    header = _get_header(requisition)
    header_value = header.get(field_name)

    if header_value not in (None, ""):
        return str(header_value).strip()

    return default


def _get_requisition_items(requisition: dict[str, Any]) -> list[dict[str, Any]]:
    items = requisition.get("items")

    if isinstance(items, list):
        return items

    line_items = requisition.get("line_items")

    if isinstance(line_items, list):
        return line_items

    return []


def _get_item_name(item: dict[str, Any]) -> str:
    return str(
        item.get("item_name")
        or item.get("description")
        or item.get("name")
        or "UNKNOWN_ITEM"
    )


def _get_item_total(item: dict[str, Any]) -> float:
    if "total_price" in item:
        return _to_float(item.get("total_price"))

    quantity = _to_float(item.get("quantity"))
    unit_price = _to_float(item.get("unit_price"))

    return quantity * unit_price


def _calculate_total_estimated_value(requisition: dict[str, Any]) -> float:
    if "total_value" in requisition:
        return round(_to_float(requisition.get("total_value")), 2)

    items = _get_requisition_items(requisition)
    total = sum(_get_item_total(item) for item in items)

    return round(total, 2)


def _classify_pr_type(requisition: dict[str, Any]) -> PRType:
    explicit_type = str(requisition.get("pr_type", "")).strip().upper()

    if explicit_type in PRType.__members__:
        return PRType[explicit_type]

    header = _get_header(requisition)

    combined_text = " ".join(
        [
            str(requisition.get("justification", "")),
            str(requisition.get("description", "")),
            str(requisition.get("notes", "")),
            str(header.get("justification", "")),
            str(header.get("description", "")),
            str(header.get("notes", "")),
        ]
    ).lower()

    if "emergency" in combined_text or "urgent" in combined_text:
        return PRType.EMERGENCY

    if "sole" in combined_text or "single source" in combined_text:
        return PRType.SOLE_SOURCE

    if "blanket" in combined_text:
        return PRType.BLANKET_ORDER

    return PRType.STANDARD


def _get_evidence_page_number(item: dict[str, Any]) -> int:
    evidence_pointers = item.get("evidence_pointers")

    if isinstance(evidence_pointers, list) and evidence_pointers:
        first_evidence = evidence_pointers[0]

        if isinstance(first_evidence, dict):
            page_number = first_evidence.get("page_number")

            if page_number is not None:
                return int(page_number)

    return 1


def _build_evidence_index(
    requisition: dict[str, Any],
    requisition_file: str,
) -> list[LineItemRef]:
    evidence_index: list[LineItemRef] = []

    for item in _get_requisition_items(requisition):
        evidence_index.append(
            LineItemRef(
                item_name=_get_item_name(item),
                source_file=requisition_file,
                page_number=_get_evidence_page_number(item),
            )
        )

    return evidence_index


def _build_vendor_preference_map(
    approved_vendors: list[dict[str, str]],
) -> dict[str, bool]:
    vendor_map: dict[str, bool] = {}

    for vendor in approved_vendors:
        vendor_name = str(vendor.get("vendor_name", "")).strip().lower()

        if not vendor_name:
            continue

        is_approved = _to_bool(vendor.get("is_approved", vendor.get("approved", True)))
        is_preferred = _to_bool(vendor.get("is_preferred", vendor.get("preferred", False)))

        vendor_map[vendor_name] = is_approved and is_preferred

    return vendor_map


def _get_available_budget_for_cost_center(
    budget_snapshot: list[dict[str, str]],
    cost_center: str,
) -> float:
    for row in budget_snapshot:
        row_cost_center = str(row.get("cost_center", "")).strip()

        if row_cost_center == cost_center:
            return _to_float(row.get("available_budget"))

    return 0.0


def _detect_risk_flags(
    requisition: dict[str, Any],
    bundle_data: dict[str, Any],
    pr_type: PRType,
    total_estimated_value: float,
) -> list[RiskFlag]:
    flags: list[RiskFlag] = []

    items = _get_requisition_items(requisition)
    approved_vendors = bundle_data.get("approved_vendors", [])
    vendor_preference_map = _build_vendor_preference_map(approved_vendors)

    for item in items:
        requested_vendor = str(item.get("requested_vendor", "")).strip().lower()

        if not requested_vendor:
            continue

        is_preferred = vendor_preference_map.get(requested_vendor)

        if is_preferred is not True:
            _add_risk_flag(flags, RiskFlag.NON_PREFERRED_VENDOR)

    approval_policy = bundle_data.get("approval_policy", {})
    sole_source_threshold = _to_float(
        approval_policy.get("sole_source_threshold"),
        default=3000.0,
    )

    justification = _get_requisition_field(requisition, "justification")

    if pr_type == PRType.SOLE_SOURCE and total_estimated_value >= sole_source_threshold:
        _add_risk_flag(flags, RiskFlag.HIGH_VALUE_SOLE_SOURCE)

        if not justification:
            _add_risk_flag(flags, RiskFlag.MISSING_JUSTIFICATION)

    cost_center = _get_requisition_field(requisition, "cost_center")
    available_budget = _get_available_budget_for_cost_center(
        bundle_data.get("budget_snapshot", []),
        cost_center,
    )

    if available_budget > 0:
        budget_usage = total_estimated_value / available_budget

        if budget_usage >= 0.90:
            _add_risk_flag(flags, RiskFlag.BUDGET_NEAR_LIMIT)

    return flags


def _calculate_risk_score(risk_flags: list[RiskFlag]) -> float:
    if not risk_flags:
        return 0.0

    return min(round(len(risk_flags) * 0.25, 2), 1.0)


def _validate_required_requisition_fields(requisition: dict[str, Any]) -> None:
    required_fields = ["requester", "department", "cost_center"]

    for field in required_fields:
        value = _get_requisition_field(requisition, field)

        if not value:
            raise ValueError(f"Missing required field in requisition: {field}")


def run_intake(bundle_path: str | Path) -> ContextPacket:
    bundle_path = Path(bundle_path)

    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle folder not found: {bundle_path}")

    bundle_data = load_pr_bundle(bundle_path)

    manifest = BundleManifest.model_validate(bundle_data["manifest"])
    requisition = bundle_data["requisition"]

    _validate_required_requisition_fields(requisition)

    run_id = manifest.bundle_id

    create_run_dir(run_id)

    requester = _get_requisition_field(requisition, "requester")
    department = _get_requisition_field(requisition, "department")
    cost_center = _get_requisition_field(requisition, "cost_center")

    pr_type = _classify_pr_type(requisition)
    total_estimated_value = _calculate_total_estimated_value(requisition)

    evidence_index = _build_evidence_index(
        requisition=requisition,
        requisition_file=manifest.requisition_file,
    )

    risk_flags = _detect_risk_flags(
        requisition=requisition,
        bundle_data=bundle_data,
        pr_type=pr_type,
        total_estimated_value=total_estimated_value,
    )

    context_packet = ContextPacket(
        run_id=run_id,
        pr_type=pr_type,
        requester=requester,
        department=department,
        cost_center=cost_center,
        total_estimated_value=total_estimated_value,
        bundle_files=[
            manifest.requisition_file,
            manifest.budget_file,
            manifest.vendor_file,
            manifest.catalogue_file,
            manifest.policy_file,
            manifest.cost_center_file,
        ],
        evidence_index=evidence_index,
        risk_flags=risk_flags,
        risk_score=_calculate_risk_score(risk_flags),
        classification_confidence=1.0,
    )

    write_context_packet(run_id, context_packet)

    return context_packet