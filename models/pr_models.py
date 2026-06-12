from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from enum import Enum
from models.shared_models import EvidencePointer

class ExtractionMethod(str, Enum):
    PDF_DIRECT = "PDF_DIRECT"
    SYNTHETIC_FALLBACK = "SYNTHETIC_FALLBACK"

class PRHeader(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    pr_number: str

    request_date: datetime
    required_by: datetime
    requester: str
    department: str
    cost_center: str
    justification: Optional[str] = None

class LineItem(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    line_number: int
    item_name: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0.0)
    total_price: float = Field(ge=0.0)
    cost_center: str
    requested_vendor: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_pointers: list[EvidencePointer] = Field(default_factory=list)
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None

class ExtractedPR(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    run_id: str
    pr_id: str
    header: PRHeader
    line_items: list[LineItem] = Field(default_factory=list)
    total_value: float = Field(ge=0.0)
    extraction_method: ExtractionMethod
    overall_confidence: float = Field(ge=0.0, le=1.0)
    aggregation_notes: list[str] = Field(default_factory=list)