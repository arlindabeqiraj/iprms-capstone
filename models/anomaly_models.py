from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from models.shared_models import Finding


class AnomalyStatus(str, Enum):
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    EXCEPTION = "EXCEPTION"
    BLOCK = "BLOCK"


class AnomalyType(str, Enum):
    SPLIT_ORDER_WITHIN_PR = "SPLIT_ORDER_WITHIN_PR"
    SPLIT_ORDER_CROSS_BUNDLE = "SPLIT_ORDER_CROSS_BUNDLE"
    LOW_CONFIDENCE_EXTRACTION = "LOW_CONFIDENCE_EXTRACTION"
    VAGUE_ITEM_DESCRIPTION = "VAGUE_ITEM_DESCRIPTION"


class AnomalyGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    anomaly_type: AnomalyType
    item_key: str
    department: str
    cost_center: str | None = None
    occurrence_count: int = Field(ge=1)
    cumulative_value: float = Field(ge=0.0)
    involved_pr_ids: list[str] = Field(default_factory=list)
    involved_bundles: list[str] = Field(default_factory=list)
    severity: str
    explanation: str


class AnomalyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    run_id: str
    bundle_id: str
    overall_status: AnomalyStatus
    split_order_detected: bool
    anomaly_score: float = Field(ge=0.0, le=1.0)
    scanned_bundles: list[str] = Field(default_factory=list)
    rules_applied: list[str] = Field(default_factory=list)
    anomaly_groups: list[AnomalyGroup] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)