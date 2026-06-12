from pydantic import BaseModel, Field, ConfigDict 
from models.shared_models import PRType, RiskFlag 
 
 
class LineItemRef(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    item_name:   str 
    source_file: str 
    page_number: int 
 
 
class ContextPacket(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    run_id:                    str 
    pr_type:                   PRType 
    requester:                 str 
    department:                str 
    cost_center:               str 
    total_estimated_value:     float 
    bundle_files:              list[str] = Field(default_factory=list) 
    evidence_index:            list[LineItemRef] = Field(default_factory=list) 
    risk_flags:                list[RiskFlag] = Field(default_factory=list) 
    risk_score:                float = Field(ge=0.0, le=1.0) 
    classification_confidence: float = Field(ge=0.0, le=1.0)