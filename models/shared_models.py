from pydantic import BaseModel, Field, ConfigDict 
from typing import Optional 
from datetime import datetime 
from enum import Enum 
 
 
class Severity(str, Enum): 
    BLOCK     = "BLOCK" 
    EXCEPTION = "EXCEPTION" 
    WARNING   = "WARNING" 
 
 
class Decision(str, Enum): 
    AUTO_APPROVE      = "AUTO_APPROVE" 
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL" 
    MANUAL_REVIEW     = "MANUAL_REVIEW" 
    BLOCKED           = "BLOCKED" 
 
 
class PRType(str, Enum): 
    STANDARD      = "STANDARD" 
    EMERGENCY     = "EMERGENCY" 
    SOLE_SOURCE   = "SOLE_SOURCE" 
    BLANKET_ORDER = "BLANKET_ORDER" 
 
 
class RiskFlag(str, Enum):
    HIGH_VALUE_SOLE_SOURCE = "HIGH_VALUE_SOLE_SOURCE"
    MISSING_JUSTIFICATION = "MISSING_JUSTIFICATION"
    SPLIT_ORDER_RISK = "SPLIT_ORDER_RISK"
    BUDGET_NEAR_LIMIT = "BUDGET_NEAR_LIMIT"
    NON_PREFERRED_VENDOR = "NON_PREFERRED_VENDOR"
 
 
class InputType(str, Enum): 
    PDF_FORM  = "PDF_FORM" 
    WEB_FORM  = "WEB_FORM" 
    PR_BUNDLE = "PR_BUNDLE" 
 
 
class EvidencePointer(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    source_file:  str 
    page_number:  int 
    field_name:   str 
    bounding_box: Optional[list[float]] = None 
    # [x0, y0, x1, y1] — koordinatat në PDF 
 
 
class Finding(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    finding_id:             str 
    agent_source:           str 
    severity:               Severity 
    confidence:             float = Field(ge=0.0, le=1.0) 
    confidence_explanation: str 
    description:            str 
    evidence_pointers:      list[EvidencePointer] = Field(default_factory=list) 
    recommended_action:     str 
 
 
class BundleManifest(BaseModel): 
    bundle_id:         str 
    description:       str 
    expected_decision: Decision 
    requisition_file:  str 
    budget_file:       str 
    vendor_file:       str 
    catalogue_file:    str 
    policy_file:       str 
    cost_center_file:  str 
    created_at:        datetime 
 
 
class PRBundle(BaseModel): 
    run_id:      str 
    bundle_path: str 
    manifest:    BundleManifest 
 
 
class RequisitionInput(BaseModel): 
    input_type:  InputType 
    file_path:   Optional[str] = None 
    bundle_path: Optional[str] = None 
    web_data:    Optional[dict] = None