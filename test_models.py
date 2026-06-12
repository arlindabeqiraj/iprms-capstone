"""
IPRMS — Test Suite për të gjitha modelet Pydantic + LangGraph pipeline
Run: python test_models.py
"""
import sys
from datetime import datetime

# ─── helpers ──────────────────────────────────────────────────
PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"
HEAD = "\033[94m"
END  = "\033[0m"

def section(title: str):
    print(f"\n{HEAD}{'─'*55}{END}")
    print(f"{HEAD}  {title}{END}")
    print(f"{HEAD}{'─'*55}{END}")

def ok(msg: str):
    print(f"  {PASS}  {msg}")

def fail(msg: str, err):
    print(f"  {FAIL}  {msg}: {err}")
    sys.exit(1)

# ─── 1. Import test ───────────────────────────────────────────
section("1 · Import — models package")
try:
    from models import (
        Severity, Decision, PRType, RiskFlag, InputType,
        EvidencePointer, Finding, BundleManifest, PRBundle, RequisitionInput,
        LineItemRef, ContextPacket,
        ExtractionMethod, PRHeader, LineItem, ExtractedPR,
        BudgetStatus, BudgetLineCheck, BudgetCheck,
        VendorStatus, VendorLineMatch, VendorMatch,
        ComplianceStatus, ProcurementScenario, ComplianceFindings,
        POStatus, ExceptionItem, ExceptionsReport,
        AuditStep, AuditLog,
        ApprovalRoute, ApprovalPacket,
        POLineItem, PODraft, Metrics,
    )
    ok("Të gjitha modelet importohen me sukses")
except Exception as e:
    fail("Import dështoi", e)

# ─── 2. EvidencePointer ───────────────────────────────────────
section("2 · EvidencePointer")
try:
    ep = EvidencePointer(
        source_file="requisition.pdf",
        page_number=1,
        field_name="total_value",
        bounding_box=[10.0, 20.0, 100.0, 30.0],
    )
    ok(f"Krijuar: {ep.source_file} | page {ep.page_number}")
except Exception as e:
    fail("EvidencePointer krijimi", e)

# extra='forbid' test
try:
    EvidencePointer(source_file="x.pdf", page_number=1, field_name="f", unknown_field="oops")
    fail("Duhet të kishte refuzuar fushë të panjohur", "nuk refuzoi")
except Exception:
    ok("extra='forbid' punon — fushat e panjohura refuzohen")

# ─── 3. Finding + validation ──────────────────────────────────
section("3 · Finding — confidence validation")
try:
    Finding(
        finding_id="test",
        agent_source="agent_a",
        severity=Severity.WARNING,
        confidence=1.5,           # duhet të refuzohet
        confidence_explanation="test",
        description="test",
        evidence_pointers=[],
        recommended_action="test",
    )
    fail("Confidence 1.5 duhej refuzuar", "nuk refuzoi")
except Exception as e:
    ok(f"Validation OK — confidence 1.5 refuzua: {type(e).__name__}")

f = Finding(
    finding_id="F001",
    agent_source="agent_budget",
    severity=Severity.BLOCK,
    confidence=0.95,
    confidence_explanation="Budget tejkalon me 20%",
    description="Cost center CC-100 tejkalon buxhetin",
    evidence_pointers=[ep],
    recommended_action="Kthe tek menaxheri financiar",
)
ok(f"Finding valid: {f.finding_id} | severity={f.severity}")

# ─── 4. ContextPacket (Agent A) ───────────────────────────────
section("4 · ContextPacket — Agent A")
try:
    cp = ContextPacket(
        run_id="run-001",
        pr_type=PRType.STANDARD,
        requester="Arlinda Krasniqi",
        department="IT",
        cost_center="CC-100",
        total_estimated_value=12500.0,
        bundle_files=["req.pdf", "budget.xlsx"],
        evidence_index=[LineItemRef(item_name="Laptop", source_file="req.pdf", page_number=2)],
        risk_flags=[RiskFlag.BUDGET_NEAR_LIMIT],
        risk_score=0.4,
        classification_confidence=0.92,
    )
    ok(f"ContextPacket: run={cp.run_id} | value={cp.total_estimated_value} | flags={cp.risk_flags}")
except Exception as e:
    fail("ContextPacket", e)

# ─── 5. ExtractedPR (Agent B) ─────────────────────────────────
section("5 · ExtractedPR — Agent B")
try:
    header = PRHeader(
        pr_number="PR-2025-0042",
        request_date=datetime(2025, 6, 1),
        required_by=datetime(2025, 6, 15),
        requester="Arlinda Krasniqi",
        department="IT",
        cost_center="CC-100",
        justification="Zëvendësim pajisje të vjetruara",
    )
    item = LineItem(
        line_number=1,
        item_name="Laptop Dell XPS 15",
        quantity=5,
        unit_price=1200.0,
        total_price=6000.0,
        cost_center="CC-100",
        requested_vendor="Dell",
        confidence=0.88,
        evidence_pointers=[ep],
    )
    pr = ExtractedPR(
        run_id="run-001",
        pr_id="PR-2025-0042",
        header=header,
        line_items=[item],
        total_value=6000.0,
        extraction_method=ExtractionMethod.PDF_DIRECT,
        overall_confidence=0.88,
    )
    ok(f"ExtractedPR: {pr.pr_id} | items={len(pr.line_items)} | total={pr.total_value}")
except Exception as e:
    fail("ExtractedPR", e)

# quantity <= 0 test
try:
    LineItem(
        line_number=1, item_name="X", quantity=0,
        unit_price=10.0, total_price=0.0, cost_center="CC-1", confidence=0.5,
    )
    fail("quantity=0 duhej refuzuar", "nuk refuzoi")
except Exception:
    ok("quantity=0 refuzua — Field(gt=0) punon")

# ─── 6. BudgetCheck (Agent C) ─────────────────────────────────
section("6 · BudgetCheck — Agent C")
try:
    blc = BudgetLineCheck(
        line_number=1,
        cost_center="CC-100",
        gl_account="GL-5100",
        requested_amount=6000.0,
        available_budget=5000.0,
        status=BudgetStatus.EXCEEDED,
        period_cap_ok=False,
        capex_required=True,
        findings=[f],
    )
    bc = BudgetCheck(
        run_id="run-001",
        overall_status=BudgetStatus.EXCEEDED,
        line_checks=[blc],
        total_requested=6000.0,
        total_available=5000.0,
    )
    ok(f"BudgetCheck: status={bc.overall_status} | requested={bc.total_requested} > available={bc.total_available}")
except Exception as e:
    fail("BudgetCheck", e)

# ─── 7. VendorMatch (Agent D) ─────────────────────────────────
section("7 · VendorMatch — Agent D")
try:
    vlm = VendorLineMatch(
        line_number=1,
        item_name="Laptop Dell XPS 15",
        matched_vendor="Dell",
        is_preferred=True,
        catalogue_price=1150.0,
        requested_price=1200.0,
        price_variance_pct=4.35,
        status=VendorStatus.MATCHED,
    )
    vm = VendorMatch(run_id="run-001", overall_status=VendorStatus.MATCHED, line_matches=[vlm])
    ok(f"VendorMatch: {vm.overall_status} | variance={vlm.price_variance_pct}%")
except Exception as e:
    fail("VendorMatch", e)

# price_variance_pct out of range
try:
    VendorLineMatch(
        line_number=1, item_name="X", is_preferred=False,
        requested_price=100.0, price_variance_pct=150.0,  # > 100 → invalid
        status=VendorStatus.NOT_FOUND,
    )
    fail("price_variance_pct=150 duhej refuzuar", "nuk refuzoi")
except Exception:
    ok("price_variance_pct=150 refuzua — Field(le=100) punon")

# ─── 8. ComplianceFindings (Agent E) ──────────────────────────
section("8 · ComplianceFindings — Agent E")
try:
    cf = ComplianceFindings(
        run_id="run-001",
        overall_compliance=ComplianceStatus.NON_COMPLIANT,
        procurement_scenario=ProcurementScenario.STANDARD,
        approval_authority_ok=False,
        sole_source_justified=False,
        bid_threshold_met=True,
        currency="EUR",
        findings=[f],
        policy_references=["POL-2024-001", "POL-2024-005"],
    )
    ok(f"ComplianceFindings: {cf.overall_compliance} | scenario={cf.procurement_scenario}")
except Exception as e:
    fail("ComplianceFindings", e)

# ─── 9. ApprovalPacket + PODraft + Metrics (Agent H) ──────────
section("9 · Decision models — Agent H")
try:
    route = ApprovalRoute(
        approver_role="CFO",
        approver_name="Besnik Gashi",
        reason="Budget exceeded by 20%",
        evidence_pointers=[ep],
        deadline_hours=48,
    )
    ap = ApprovalPacket(
        run_id="run-001",
        decision=Decision.REQUIRES_APPROVAL,
        approval_routes=[route],
        all_findings=[f],
        summary="PR tejkalon buxhetin e disponueshëm",
        final_reasoning="Kërkohet aprovim nga CFO",
        open_questions=["A është aprovuar CAPEX?"],
        human_review_required=True,
        confidence_score=0.85,
    )
    ok(f"ApprovalPacket: {ap.decision} | routes={len(ap.approval_routes)} | human_review={ap.human_review_required}")
except Exception as e:
    fail("ApprovalPacket", e)

try:
    po_item = POLineItem(
        line_number=1, item_name="Laptop Dell XPS 15",
        quantity=5, unit_price=1200.0, total_price=6000.0,
        vendor="Dell", cost_center="CC-100", gl_account="GL-5100",
    )
    po = PODraft(
        run_id="run-001", po_number="PO-2025-0001",
        requester="Arlinda Krasniqi", department="IT",
        line_items=[po_item], total_value=6000.0,
        status=POStatus.BLOCKED,
    )
    ok(f"PODraft: {po.po_number} | status={po.status} | total={po.total_value}")
except Exception as e:
    fail("PODraft", e)

try:
    m = Metrics(
        run_id="run-001",
        total_time_seconds=4.2,
        extraction_accuracy=0.88,
        vendor_match_rate=1.0,
        exception_rate=0.2,
        confidence_avg=0.87,
        confidence_per_agent={"agent_a": 0.92, "agent_b": 0.88, "agent_c": 0.81},
        agents_timing={"agent_a": 0.8, "agent_b": 1.2, "agent_c": 0.9},
        total_line_items=5,
        items_auto_approved=3,
        items_excepted=1,
        items_blocked=1,
        throughput_prs_per_hour=12.5,
    )
    ok(f"Metrics: avg_confidence={m.confidence_avg} | throughput={m.throughput_prs_per_hour}/hr")
except Exception as e:
    fail("Metrics", e)

# ─── 10. model_dump / model_validate round-trip ───────────────
section("10 · Round-trip: model_dump() → model_validate()")
try:
    dumped = cp.model_dump(mode="json")
    restored = ContextPacket.model_validate(dumped)
    assert restored.run_id == cp.run_id
    assert restored.total_estimated_value == cp.total_estimated_value
    ok(f"ContextPacket round-trip OK: run_id='{restored.run_id}'")
except Exception as e:
    fail("Round-trip ContextPacket", e)

try:
    dumped_pr = pr.model_dump(mode="json")
    restored_pr = ExtractedPR.model_validate(dumped_pr)
    assert restored_pr.pr_id == pr.pr_id
    ok(f"ExtractedPR round-trip OK: pr_id='{restored_pr.pr_id}'")
except Exception as e:
    fail("Round-trip ExtractedPR", e)

# ─── 11. LangGraph pipeline ───────────────────────────────────
section("11 · LangGraph — create_pipeline()")
try:
    from graph.pipeline_graph import create_pipeline, PRMSState
    pipeline = create_pipeline()
    ok("Pipeline kompajluar me sukses")

    # Test run me state minimal
    test_state: PRMSState = {
        "run_id": "test-001",
        "bundle_path": "/bundles/test",
        "context_packet": None,
        "extracted_pr": None,
        "budget_check": None,
        "vendor_match": None,
        "compliance_findings": None,
        "approval_packet": None,
        "po_draft": None,
        "metrics": None,
        "error": None,
    }
    result = pipeline.invoke(test_state)
    assert result["run_id"] == "test-001"
    ok(f"Pipeline invoke OK: run_id='{result['run_id']}'")
except Exception as e:
    fail("LangGraph pipeline", e)

# ─── Summary ──────────────────────────────────────────────────
print(f"\n{HEAD}{'═'*55}{END}")
print(f"{HEAD}  🎉  Të gjitha testet kaluan me sukses!{END}")
print(f"{HEAD}{'═'*55}{END}\n")
