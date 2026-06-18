from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum

from models.shared_models import Finding
from models.policy_models import ProcurementScenario


class JustificationQuality(str, Enum):
    """
    Quality level of sole-source justification.
    Assessed by LLM reasoning.
    """
    STRONG = "STRONG"
    ADEQUATE = "ADEQUATE"
    WEAK = "WEAK"
    MISSING = "MISSING"


class BidStatus(str, Enum):
    """
    Bid threshold enforcement status.
    Deterministic — based on policy thresholds.
    """
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    WAIVED = "WAIVED"
    MET = "MET"


class SoleSourceRiskLevel(str, Enum):
    """
    Overall risk level for sole-source procurement.
    Combines vendor status, value, and justification quality.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SoleSourceLineCheck(BaseModel):
    """
    Sole-source and bid check for a single PR line item.
    """
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    line_number: int
    item_name: str
    requested_vendor: Optional[str] = None
    is_preferred_vendor: bool
    total_price: float = Field(ge=0.0)

    sole_source_required: bool
    sole_source_justified: bool
    justification_quality: JustificationQuality
    justification_gaps: list[str] = Field(default_factory=list)

    bid_required: bool
    bid_status: BidStatus
    bid_required_above: float = Field(ge=0.0)

    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: SoleSourceRiskLevel

    findings: list[Finding] = Field(default_factory=list)


class SoleSourceCheck(BaseModel):
    """
    Complete sole-source and bid threshold check output.
    Written to runs/{run_id}/sole_source_check.json
    """
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    run_id: str

    # Overall assessment
    overall_sole_source_ok: bool
    overall_bid_ok: bool
    overall_risk_level: SoleSourceRiskLevel
    overall_risk_score: float = Field(ge=0.0, le=1.0)

    # Justification
    justification_text: Optional[str] = None
    justification_quality: JustificationQuality
    llm_reasoning: Optional[str] = None

    # Procurement context
    procurement_scenario: ProcurementScenario = ProcurementScenario.STANDARD
    total_value: float = Field(ge=0.0)

    # Line-level checks
    line_checks: list[SoleSourceLineCheck] = Field(default_factory=list)

    # Findings and policy
    findings: list[Finding] = Field(default_factory=list)
    policy_references: list[str] = Field(default_factory=list)