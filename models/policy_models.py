from pydantic import BaseModel, Field, ConfigDict 
from typing import Optional 
from enum import Enum 
from models.shared_models import Finding 
 
 
class ComplianceStatus(str, Enum): 
    COMPLIANT     = "COMPLIANT" 
    NON_COMPLIANT = "NON_COMPLIANT" 
    PARTIAL       = "PARTIAL" 
 
 
class ProcurementScenario(str, Enum): 
    STANDARD            = "STANDARD" 
    FRAMEWORK_AGREEMENT = "FRAMEWORK_AGREEMENT" 
    BLANKET_ORDER       = "BLANKET_ORDER" 
    EMERGENCY           = "EMERGENCY" 
    MULTI_CURRENCY      = "MULTI_CURRENCY" 
 
 
class ComplianceFindings(BaseModel): 
    run_id:                str 
    overall_compliance:    ComplianceStatus 
    procurement_scenario:  ProcurementScenario 
    approval_authority_ok: bool 
    sole_source_justified: bool 
    bid_threshold_met:     bool 
    framework_agreement:   Optional[str] = None 
    currency:              str = "USD" 
    findings:              list[Finding] 
    policy_references:     list[str] 