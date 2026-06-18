from services.run_manager import save_artifact, save_markdown
from models import (
    ContextPacket, ExtractedPR, BudgetCheck, VendorMatch,
    ComplianceFindings, ApprovalPacket, PODraft, ExceptionsReport,SoleSourceCheck
)




def write_context_packet(run_id: str, packet: ContextPacket) -> None:
    save_artifact(run_id, 'context_packet.json', packet.model_dump(mode='json'))


def write_extracted_pr(run_id: str, extracted: ExtractedPR) -> None:
    save_artifact(run_id, 'extracted_pr.json', extracted.model_dump(mode='json'))


def write_budget_check(run_id: str, budget: BudgetCheck) -> None:
    save_artifact(run_id, 'budget_check.json', budget.model_dump(mode='json'))


def write_vendor_match(run_id: str, vendor: VendorMatch) -> None:
    save_artifact(run_id, 'vendor_match.json', vendor.model_dump(mode='json'))


def write_compliance_findings(run_id: str, compliance: ComplianceFindings) -> None:
    save_artifact(run_id, 'compliance_findings.json', compliance.model_dump(mode='json'))


def write_approval_packet(run_id: str, packet: ApprovalPacket) -> None:
    save_artifact(run_id, 'approval_packet.json', packet.model_dump(mode='json'))


def write_po_draft(run_id: str, po: PODraft) -> None:
    save_artifact(run_id, 'po_draft.json', po.model_dump(mode='json'))


def write_sole_source_check(run_id: str, check: SoleSourceCheck) -> None:
    save_artifact(run_id, 'sole_source_check.json', check.model_dump(mode='json'))
