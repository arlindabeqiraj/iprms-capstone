from pydantic import BaseModel, Field, ConfigDict 
from typing import Optional 
from datetime import datetime 
from enum import Enum 
from models.shared_models import Decision, Severity, Finding, EvidencePointer 
 
 
class POStatus(str, Enum): 
    READY   = "READY" 
    BLOCKED = "BLOCKED" 
 
 
# ── exceptions.md ──────────────────────────────────────────── 
class ExceptionItem(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    exception_id: str 
    severity:     Severity 
    agent_source: str 
    description:  str 
    next_action:  str 
    responsible:  str 
    evidence:     list[EvidencePointer] = Field(default_factory=list) 
 
class ExceptionsReport(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    run_id:           str 
    total_exceptions: int = Field(ge=0) 
    exceptions:       list[ExceptionItem] = Field(default_factory=list) 
 
 
# ── audit_log.md ───────────────────────────────────────────── 
class AuditStep(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    timestamp:      datetime 
    agent_name:     str 
    action:         str 
    input_summary:  str 
    output_summary: str 
    tools_called:   list[str] = Field(default_factory=list) 
    decision:       Optional[str] = None 
    duration_ms:    float = Field(ge=0.0) 
 
class AuditLog(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    run_id:         str 
    bundle_path:    str 
    started_at:     datetime 
    completed_at:   datetime 
    final_decision: Decision 
    steps:          list[AuditStep] = Field(default_factory=list) 
 
 
# ── approval_packet.json ───────────────────────────────────── 
class ApprovalRoute(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    approver_role:     str 
    approver_name:     Optional[str] = None 
    reason:            str 
    evidence_pointers: list[EvidencePointer] = Field(default_factory=list) 
    deadline_hours:    Optional[int] = Field(default=None, gt=0) 
 
class ApprovalPacket(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    run_id:                str 
    decision:              Decision 
    approval_routes:       list[ApprovalRoute] = Field(default_factory=list) 
    all_findings:          list[Finding] = Field(default_factory=list) 
    summary:               str 
    final_reasoning:       str 
    open_questions:        list[str] = Field(default_factory=list) 
    human_review_required: bool = False 
    confidence_score:      float = Field(ge=0.0, le=1.0) 
    po_draft_reference:    Optional[str] = None 
 
 
# ── po_draft.json ──────────────────────────────────────────── 
class POLineItem(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    line_number: int 
    item_name:   str 
    quantity:    int   = Field(gt=0) 
    unit_price:  float = Field(ge=0.0) 
    total_price: float = Field(ge=0.0) 
    vendor:      str 
    cost_center: str 
    gl_account:  str 
 
class PODraft(BaseModel): 
    run_id:      str 
    po_number:   str 
    requester:   str 
    department:  str 
    line_items:  list[POLineItem] 
    total_value: float = Field(ge=0.0)   # ← validation 
    currency:    str = "USD" 
    status:      POStatus 
 
 
# ── metrics.json ───────────────────────────────────────────── 
class Metrics(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    run_id:                  str 
    total_time_seconds:      float = Field(ge=0.0) 
    extraction_accuracy:     float = Field(ge=0.0, le=1.0) 
    vendor_match_rate:       float = Field(ge=0.0, le=1.0) 
    exception_rate:          float = Field(ge=0.0, le=1.0) 
    confidence_avg:          float = Field(ge=0.0, le=1.0) 
    confidence_per_agent:    dict[str, float] 
    agents_timing:           dict[str, float] 
    total_line_items:        int   = Field(ge=0) 
    items_auto_approved:     int   = Field(ge=0) 
    items_excepted:          int   = Field(ge=0) 
    items_blocked:           int   = Field(ge=0) 
    throughput_prs_per_hour: float = Field(ge=0.0)