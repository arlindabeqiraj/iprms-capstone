from typing import TypedDict, Optional 
from langgraph.graph import StateGraph, END 
 
 
class PRMSState(TypedDict): 
    run_id:              str 
    bundle_path:         str 
    context_packet:      Optional[dict]   # ContextPacket.model_dump() 
    extracted_pr:        Optional[dict]   # ExtractedPR.model_dump() 
    budget_check:        Optional[dict]   # BudgetCheck.model_dump() 
    vendor_match:        Optional[dict]   # VendorMatch.model_dump() 
    compliance_findings: Optional[dict]   # ComplianceFindings.model_dump() 
    approval_packet:     Optional[dict]   # ApprovalPacket.model_dump() 
    po_draft:            Optional[dict]   # PODraft.model_dump() 
    metrics:             Optional[dict]   # Metrics.model_dump() 
    error:               Optional[str] 
 
 
def create_pipeline(): 
    graph = StateGraph(PRMSState) 
 
    graph.add_node('intake',       lambda state: state) 
    graph.add_node('extraction',   lambda state: state) 
    graph.add_node('budget',       lambda state: state) 
    graph.add_node('vendor',       lambda state: state) 
    graph.add_node('compliance',   lambda state: state) 
    graph.add_node('orchestrator', lambda state: state) 
 
    graph.set_entry_point('intake') 
    graph.add_edge('intake',     'extraction') 
    graph.add_edge('extraction', 'budget') 
    graph.add_edge('budget',     'vendor') 
    graph.add_edge('vendor',     'compliance') 
    graph.add_edge('compliance', 'orchestrator') 
    graph.add_edge('orchestrator', END) 
 
    return graph.compile() 
 
 
# ── Pattern i çdo agjenti ──────────────────────────────────── 
# Lexim:  model = ContextPacket.model_validate(state['context_packet']) 
# Shkrim: state['context_packet'] = packet.model_dump(mode='json')