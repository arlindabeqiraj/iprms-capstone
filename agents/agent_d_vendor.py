from typing import Any, Optional

from models import (
    ExtractedPR,
    VendorMatch,
    VendorLineMatch,
    VendorStatus,
    Finding,
    EvidencePointer,
    Severity,
)
from services.file_loader import load_approved_vendors, load_catalogue_pricing
from services.output_writer import write_vendor_match


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _normalize(value: Any) -> str:
    return str(value).strip().lower()


def _find_vendor(vendors: list[dict], vendor_name: Optional[str]) -> Optional[dict]:
    if not vendor_name:
        return None

    target = _normalize(vendor_name)

    for vendor in vendors:
        if _normalize(vendor.get("vendor_name")) == target:
            return vendor

    return None


def _find_catalogue_price(
    catalogue_rows: list[dict],
    item_name: str,
    vendor_name: Optional[str],
) -> Optional[float]:
    if not vendor_name:
        return None

    target_item = _normalize(item_name)
    target_vendor = _normalize(vendor_name)

    for row in catalogue_rows:
        if (
            _normalize(row.get("item_name")) == target_item
            and _normalize(row.get("vendor_name")) == target_vendor
        ):
            try:
                return float(row.get("unit_price"))
            except (TypeError, ValueError):
                return None

    return None


def _price_variance_pct(requested_price: float, catalogue_price: Optional[float]) -> float:
    if catalogue_price is None or catalogue_price == 0:
        return 0.0

    return round(((requested_price - catalogue_price) / catalogue_price) * 100, 2)


def _make_finding(
    finding_id: str,
    severity: Severity,
    description: str,
    field_name: str,
    recommended_action: str,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        agent_source="Agent D - Vendor Matching",
        severity=severity,
        confidence=1.0,
        confidence_explanation="Deterministic vendor and catalogue validation based on PR bundle CSV files.",
        description=description,
        evidence_pointers=[
            EvidencePointer(
                source_file="approved_vendors.csv",
                page_number=1,
                field_name=field_name,
                bounding_box=None,
            )
        ],
        recommended_action=recommended_action,
    )


def run(state: dict[str, Any]) -> dict[str, Any]:
    """
    Agent D - Vendor Matching

    Checks:
    - Whether requested vendor exists
    - Whether vendor is approved/preferred
    - Whether catalogue pricing exists
    - Whether requested price matches catalogue price
    """

    try:
        run_id = state["run_id"]
        bundle_path = state["bundle_path"]

        if not state.get("extracted_pr"):
            raise ValueError("Missing extracted_pr in pipeline state. Agent B must run before Agent D.")

        extracted_pr = ExtractedPR.model_validate(state["extracted_pr"])

        vendors = load_approved_vendors(bundle_path)
        catalogue = load_catalogue_pricing(bundle_path)

        line_matches: list[VendorLineMatch] = []

        for line in extracted_pr.line_items:
            findings: list[Finding] = []

            requested_vendor = line.requested_vendor
            vendor_record = _find_vendor(vendors, requested_vendor)
            catalogue_price = _find_catalogue_price(
                catalogue,
                line.item_name,
                requested_vendor,
            )

            if vendor_record is None:
                status = VendorStatus.NOT_FOUND
                matched_vendor = None
                is_preferred = False

                findings.append(
                    _make_finding(
                        finding_id=f"VENDOR_NOT_FOUND_LINE_{line.line_number}",
                        severity=Severity.EXCEPTION,
                        description=f"Requested vendor '{requested_vendor}' was not found in the approved vendor list.",
                        field_name=f"line_items[{line.line_number - 1}].requested_vendor",
                        recommended_action="Route to buyer review and select an approved vendor.",
                    )
                )

            else:
                matched_vendor = vendor_record.get("vendor_name")
                is_approved = _to_bool(
                    vendor_record.get("is_approved", vendor_record.get("approved", False))
                )
                is_preferred = _to_bool(
                    vendor_record.get("is_preferred", vendor_record.get("preferred", False))
                )

                if not is_approved:
                    status = VendorStatus.NON_PREFERRED
                    findings.append(
                        _make_finding(
                            finding_id=f"VENDOR_NOT_APPROVED_LINE_{line.line_number}",
                            severity=Severity.EXCEPTION,
                            description=f"Requested vendor '{matched_vendor}' is not approved.",
                            field_name=f"line_items[{line.line_number - 1}].requested_vendor",
                            recommended_action="Route to buyer review and use an approved vendor.",
                        )
                    )

                elif not is_preferred:
                    status = VendorStatus.NON_PREFERRED
                    findings.append(
                        _make_finding(
                            finding_id=f"NON_PREFERRED_VENDOR_LINE_{line.line_number}",
                            severity=Severity.WARNING,
                            description=f"Requested vendor '{matched_vendor}' is approved but not preferred.",
                            field_name=f"line_items[{line.line_number - 1}].requested_vendor",
                            recommended_action="Review whether a preferred vendor should be used.",
                        )
                    )

                else:
                    status = VendorStatus.MATCHED

            if catalogue_price is None:
                findings.append(
                    _make_finding(
                        finding_id=f"CATALOGUE_PRICE_MISSING_LINE_{line.line_number}",
                        severity=Severity.WARNING,
                        description=f"No catalogue price found for item '{line.item_name}' and vendor '{requested_vendor}'.",
                        field_name=f"line_items[{line.line_number - 1}].item_name",
                        recommended_action="Buyer should verify catalogue pricing manually.",
                    )
                )

                if status == VendorStatus.MATCHED:
                    status = VendorStatus.NON_PREFERRED

            line_match = VendorLineMatch(
                line_number=line.line_number,
                item_name=line.item_name,
                matched_vendor=matched_vendor,
                is_preferred=is_preferred,
                catalogue_price=catalogue_price,
                requested_price=line.unit_price,
                price_variance_pct=_price_variance_pct(line.unit_price, catalogue_price),
                status=status,
                findings=findings,
            )

            line_matches.append(line_match)

        if any(match.status == VendorStatus.NOT_FOUND for match in line_matches):
            overall_status = VendorStatus.NOT_FOUND
        elif any(match.status == VendorStatus.NON_PREFERRED for match in line_matches):
            overall_status = VendorStatus.NON_PREFERRED
        else:
            overall_status = VendorStatus.MATCHED

        vendor_match = VendorMatch(
            run_id=run_id,
            overall_status=overall_status,
            line_matches=line_matches,
        )

        write_vendor_match(run_id, vendor_match)

        state["vendor_match"] = vendor_match.model_dump(mode="json")
        state["error"] = None
        return state

    except Exception as exc:
        state["error"] = f"Agent D vendor matching failed: {exc}"
        return state