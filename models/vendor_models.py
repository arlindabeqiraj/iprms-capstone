from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum
from models.shared_models import Finding

class VendorStatus(str, Enum):
    MATCHED = "MATCHED"
    NON_PREFERRED = "NON_PREFERRED"
    NOT_FOUND = "NOT_FOUND"

class VendorLineMatch(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    line_number: int
    item_name: str
    matched_vendor: Optional[str] = None
    is_preferred: bool
    catalogue_price: Optional[float] = Field(default=None, ge=0.0)
    requested_price: float = Field(ge=0.0)
    price_variance_pct: float = Field(ge=-100.0, le=100.0)
    status: VendorStatus
    findings: list[Finding] = Field(default_factory=list)

class VendorMatch(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    run_id: str

    overall_status: VendorStatus
    line_matches: list[VendorLineMatch] = Field(default_factory=list)