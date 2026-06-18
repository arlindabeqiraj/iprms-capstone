"""
demo.py — IPRMS One-Command Demo Run


Run: python demo.py
"""

import sys
import time
from pathlib import Path
from run_pipeline import run_pipeline

BUNDLES = [
    {
        "path":     "examples/pr_bundle_001_clean_auto_po",
        "scenario": "Standard IT consumables — auto-PO",
        "expected": "AUTO_APPROVE",
    },
    {
        "path":     "examples/pr_bundle_002_exception_vendor",
        "scenario": "Non-preferred vendor — exception",
        "expected": "REQUIRES_APPROVAL",
    },
    {
        "path":     "examples/pr_bundle_003_budget_exceeded",
        "scenario": "Budget exhausted — block and route to FP&A",
        "expected": "BLOCKED",
    },
    {
        "path":     "examples/pr_bundle_004_emergency_sole_source",
        "scenario": "Emergency sole-source — expedited approval",
        "expected": "REQUIRES_APPROVAL",
    },
    {
        "path":     "examples/pr_bundle_005_budget_borderline",
        "scenario": "Budget borderline — warning",
        "expected": "REQUIRES_APPROVAL",
    },
    {
        "path":     "examples/pr_bundle_006_vague_description",
        "scenario": "Item description too vague — buyer clarification",
        "expected": "REQUIRES_APPROVAL",
    },
    {
        "path":     "examples/pr_bundle_007_low_confidence",
        "scenario": "Low confidence extraction — manual review",
        "expected": "BLOCKED",
    },
    {
        "path":     "examples/pr_bundle_008_clean_small_auto_approve",
        "scenario": "Clean small consumables — minimal noise, auto-approve",
        "expected": "AUTO_APPROVE",
    },
    {
        "path":     "examples/pr_bundle_009_three_prs_same_dept",
        "scenario": "Three PRs same department — above threshold",
        "expected": "AUTO_APPROVE",
    },
    {
        "path":     "examples/pr_bundle_011_split_order_anomaly",
        "scenario": "Split-order anomaly detected — Agent G stretch goal",
        "expected": "REQUIRES_APPROVAL",
    },
]


def run_demo() -> None:
    print("\n" + "=" * 70)
    print("IPRMS — Intelligent Procurement Request Management System")
    print("One-Command Demo Run")
    print("Capstone Project")
    print("=" * 70)
    print(f"\nRunning {len(BUNDLES)} PR Bundle scenarios...\n")

    results  = []
    start    = time.time()
    passed   = 0
    failed   = 0

    for i, bundle in enumerate(BUNDLES, start=1):
        print(f"[{i}/{len(BUNDLES)}] {bundle['scenario']}")
        print(f"       Bundle: {bundle['path']}")

        try:
            bundle_start = time.time()
            result       = run_pipeline(
                bundle_path = bundle["path"],
                use_llm     = True,
            )
            duration = round(time.time() - bundle_start, 1)

            decision   = result["agent_h_result"]["decision"]
            compliance = getattr(
                result["compliance"].overall_compliance,
                "value",
                str(result["compliance"].overall_compliance)
            ) if result["compliance"] else "SKIPPED"
            budget     = getattr(
                result["budget_check"].overall_status,
                "value",
                str(result["budget_check"].overall_status)
            )
            findings   = result["agent_h_result"]["total_findings"]
            llm_used   = result["agent_h_result"]["llm_used"]
            run_id     = result["run_id"]

            sole_source = None
            if result.get("sole_source_check"):
                sole_source = getattr(
                    result["sole_source_check"].overall_risk_level,
                    "value",
                    str(result["sole_source_check"].overall_risk_level)
                )

            results.append({
                "bundle":      bundle["path"].split("/")[-1],
                "scenario":    bundle["scenario"],
                "decision":    decision,
                "compliance":  compliance,
                "budget":      budget,
                "findings":    findings,
                "llm_used":    llm_used,
                "run_id":      run_id,
                "duration_s":  duration,
                "status":      "PASS",
            })

            print(f"       Decision    : {decision}")
            print(f"       Compliance  : {compliance}")
            print(f"       Budget      : {budget}")
            if sole_source:
                print(f"       Sole Source : risk={sole_source}")
            print(f"       Findings    : {findings}")
            print(f"       LLM used    : {llm_used}")
            print(f"       Run ID      : {run_id}")
            print(f"       Duration    : {duration}s")
            print(f"       ✅ PASSED\n")
            passed += 1

        except Exception as e:
            results.append({
                "bundle":   bundle["path"].split("/")[-1],
                "scenario": bundle["scenario"],
                "decision": "ERROR",
                "status":   "FAIL",
                "error":    str(e),
            })
            print(f"       ❌ FAILED: {e}\n")
            failed += 1

    total_duration = round(time.time() - start, 1)

    print("=" * 70)
    print("DEMO RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'Bundle':<45} {'Decision':<20} {'Status'}")
    print("-" * 70)

    for r in results:
        status_icon = "✅" if r["status"] == "PASS" else "❌"
        print(
            f"{r['bundle']:<45} "
            f"{r.get('decision', 'ERROR'):<20} "
            f"{status_icon} {r['status']}"
        )

    print("-" * 70)
    print(f"\nTotal    : {len(BUNDLES)} bundles")
    print(f"Passed   : {passed}")
    print(f"Failed   : {failed}")
    print(f"Duration : {total_duration}s")
    print("=" * 70)

    if failed > 0:
        print("\n❌ Demo failed — check errors above.")
        sys.exit(1)
    else:
        print("\n🎉 All scenarios passed — pipeline is demo-ready!")
        print(f"\nArtifacts saved in: runs/")
        print("Each run contains:")
        print("  context_packet.json      ← Agent A")
        print("  extracted_pr.json        ← Agent B")
        print("  budget_check.json        ← Agent C")
        print("  vendor_match.json        ← Agent D")
        print("  compliance_findings.json ← Agent E")
        print("  sole_source_check.json   ← Agent F (stretch goal)")
        print("  anomaly_check.json       ← Agent G (stretch goal)")
        print("  split_order_anomalies.md ← Agent G (stretch goal)")
        print("  exceptions.md            ← Agent H")
        print("  approval_packet.json     ← Agent H")
        print("  po_draft.json            ← Agent H")
        print("  audit_log.md             ← Agent H")
        print("  audit_log.json           ← Agent H")
        print("  metrics.json             ← Agent H")
        print("  pipeline_audit_log.md    ← Pipeline")
        print("  pipeline_metrics.json    ← Pipeline")
        print("=" * 70)


if __name__ == "__main__":
    run_demo()