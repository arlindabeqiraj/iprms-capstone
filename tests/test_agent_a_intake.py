from pathlib import Path

from agents.agent_a_intake import run_intake
from models.shared_models import PRType, RiskFlag


def test_agent_a_creates_context_packet_for_bundle_002():
    bundle_path = Path("examples/pr_bundle_002_exception_vendor")

    context_packet = run_intake(bundle_path)

    assert context_packet.run_id == "PRBUNDLE002"
    assert context_packet.pr_type == PRType.STANDARD
    assert context_packet.requester == "Jane Smith"
    assert context_packet.department == "IT"
    assert context_packet.cost_center == "CC100"
    assert context_packet.total_estimated_value == 2550
    assert context_packet.classification_confidence == 1.0

    output_path = Path("runs") / context_packet.run_id / "context_packet.json"
    assert output_path.exists()


def test_agent_a_detects_vendor_risk_for_bundle_002():
    bundle_path = Path("examples/pr_bundle_002_exception_vendor")

    context_packet = run_intake(bundle_path)

    assert RiskFlag.NON_PREFERRED_VENDOR in context_packet.risk_flags
    assert context_packet.risk_score > 0


def test_agent_a_builds_evidence_index_for_bundle_002():
    bundle_path = Path("examples/pr_bundle_002_exception_vendor")

    context_packet = run_intake(bundle_path)

    assert len(context_packet.evidence_index) == 1
    assert context_packet.evidence_index[0].item_name == "Dell Latitude Laptop"
    assert context_packet.evidence_index[0].source_file == "requisition.json"
    assert context_packet.evidence_index[0].page_number == 1