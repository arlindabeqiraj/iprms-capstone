from pydantic import BaseModel, Field, ConfigDict 
from enum import Enum 
from models.shared_models import Finding 
 
 
class BudgetStatus(str, Enum): 
    AVAILABLE  = "AVAILABLE" 
    EXCEEDED   = "EXCEEDED" 
    BORDERLINE = "BORDERLINE" 
 
 
class BudgetLineCheck(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    line_number:      int 
    cost_center:      str 
    gl_account:       str 
    requested_amount: float = Field(ge=0.0) 
    available_budget: float = Field(ge=0.0) 
    status:           BudgetStatus 
    period_cap_ok:    bool 
    capex_required:   bool 
    findings:         list[Finding] = Field(default_factory=list) 
 
 
class BudgetCheck(BaseModel): 
    model_config = ConfigDict(extra='forbid', validate_assignment=True) 
    run_id:          str 
    overall_status:  BudgetStatus 
    line_checks:     list[BudgetLineCheck] = Field(default_factory=list) 
    total_requested: float = Field(ge=0.0) 
    total_available: float = Field(ge=0.0) 