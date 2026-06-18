from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


RUNS_DIR = Path("runs")

REQUIRED_ARTIFACTS = [
    "context_packet.json",
    "extracted_pr.json",
    "budget_check.json",
    "vendor_match.json",
]

OPTIONAL_POLICY_ARTIFACTS = [
    "policy_check.json",
    "compliance_findings.json",
]

OPTIONAL_ANOMALY_ARTIFACTS = [
    "anomaly_check.json",
]


def _run_dir(run_id: str) -> Path:
    path = RUNS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _artifact_path(run_id: str, filename: str) -> Path:
    return _run_dir(run_id) / filename


def _read_json_if_exists(run_id: str, filename: str) -> dict[str, Any] | None:
    path = _artifact_path(run_id, filename)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_required_json(run_id: str, filename: str) -> dict[str, Any]:
    data = _read_json_if_exists(run_id, filename)

    if data is None:
        raise FileNotFoundError(
            f"Required artifact not found: runs/{run_id}/{filename}"
        )

    return data


def _write_json(run_id: str, filename: str, data: dict[str, Any]) -> Path:
    path = _artifact_path(run_id, filename)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False, default=str)

    return path


def _write_markdown(run_id: str, filename: str, content: str) -> Path:
    path = _artifact_path(run_id, filename)
    path.write_text(content, encoding="utf-8")
    return path


def _safe_audit_start(
    audit_logger: Any,
    agent_name: str,
    input_summary: str,
) -> None:
    if audit_logger is None:
        return

    if not hasattr(audit_logger, "log_agent_start"):
        return

    try:
        audit_logger.log_agent_start(
            agent_name=agent_name,
            input_summary=input_summary,
        )
    except TypeError:
        try:
            audit_logger.log_agent_start(agent_name, input_summary)
        except TypeError:
            audit_logger.log_agent_start(input_summary=input_summary)


def _safe_audit_end(
    audit_logger: Any,
    agent_name: str,
    output_summary: str,
    decision: str | None = None,
) -> None:
    if audit_logger is None:
        return

    if not hasattr(audit_logger, "log_agent_end"):
        return

    try:
        audit_logger.log_agent_end(
            agent_name=agent_name,
            output_summary=output_summary,
            decision=decision,
        )
    except TypeError:
        try:
            audit_logger.log_agent_end(
                agent_name=agent_name,
                output_summary=output_summary,
            )
        except TypeError:
            try:
                audit_logger.log_agent_end(agent_name, output_summary)
            except TypeError:
                audit_logger.log_agent_end(output_summary=output_summary)


def _safe_audit_error(
    audit_logger: Any,
    agent_name: str,
    error: str,
) -> None:
    if audit_logger is None:
        return

    if not hasattr(audit_logger, "log_agent_error"):
        return

    try:
        audit_logger.log_agent_error(
            agent_name=agent_name,
            error=error,
        )
    except TypeError:
        try:
            audit_logger.log_agent_error(agent_name, error)
        except TypeError:
            audit_logger.log_agent_error(error=error)


def _safe_audit_tool_call(
    audit_logger: Any,
    tool_name: str,
) -> None:
    if audit_logger is None:
        return

    if not hasattr(audit_logger, "log_tool_call"):
        return

    try:
        audit_logger.log_tool_call(tool_name=tool_name)
    except TypeError:
        audit_logger.log_tool_call(tool_name)


def _safe_metrics_start(
    metrics_tracker: Any,
    agent_name: str,
) -> None:
    if metrics_tracker is None:
        return

    if not hasattr(metrics_tracker, "start_agent"):
        return

    try:
        metrics_tracker.start_agent(agent_name=agent_name)
    except TypeError:
        metrics_tracker.start_agent(agent_name)


def _safe_metrics_end(
    metrics_tracker: Any,
    agent_name: str,
    confidence: float = 1.0,
) -> None:
    if metrics_tracker is None:
        return

    if not hasattr(metrics_tracker, "end_agent"):
        return

    try:
        metrics_tracker.end_agent(
            agent_name=agent_name,
            confidence=confidence,
        )
    except TypeError:
        try:
            metrics_tracker.end_agent(agent_name, confidence)
        except TypeError:
            metrics_tracker.end_agent(agent_name)


def _safe_metrics_log_exception_rate(
    metrics_tracker: Any,
    rate: float,
    agent_name: str = "Agent H",
) -> None:
    if metrics_tracker is None:
        return

    if not hasattr(metrics_tracker, "log_exception_rate"):
        return

    try:
        metrics_tracker.log_exception_rate(rate=rate, agent_name=agent_name)
    except TypeError:
        try:
            metrics_tracker.log_exception_rate(rate)
        except TypeError:
            return


def _safe_metrics_log_confidence_avg(
    metrics_tracker: Any,
    confidence_avg: float,
) -> None:
    if metrics_tracker is None:
        return

    if not hasattr(metrics_tracker, "log_confidence_avg"):
        return

    try:
        metrics_tracker.log_confidence_avg(confidence_avg)
    except TypeError:
        try:
            metrics_tracker.log_confidence_avg(avg=confidence_avg)
        except TypeError:
            return


def _safe_string(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default

        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    return str(value).strip().lower() in {"true", "yes", "1", "y"}


def _normalize_severity(value: Any) -> str:
    raw = _safe_string(value).upper()

    if raw in {"BLOCK", "BLOCKED", "CRITICAL", "ERROR", "FAILED"}:
        return "BLOCK"

    if raw in {"EXCEPTION", "ESCALATE", "ESCALATION", "NON_COMPLIANT"}:
        return "EXCEPTION"

    if raw in {"WARNING", "WARN", "REVIEW", "MANUAL_REVIEW"}:
        return "WARNING"

    return "WARNING"


def _normalize_decision(value: Any) -> str:
    raw = _safe_string(value).upper()

    if raw in {"AUTO_APPROVE", "AUTO_APPROVED", "APPROVED"}:
        return "AUTO_APPROVE"

    if raw in {"REQUIRES_APPROVAL", "APPROVAL_REQUIRED"}:
        return "REQUIRES_APPROVAL"

    if raw in {"MANUAL_REVIEW", "REVIEW_REQUIRED"}:
        return "MANUAL_REVIEW"

    if raw in {"BLOCKED", "BLOCK"}:
        return "BLOCKED"

    return "MANUAL_REVIEW"


def _default_evidence(source_file: str, field_name: str) -> dict[str, Any]:
    return {
        "source_file": source_file,
        "page_number": 1,
        "field_name": field_name,
        "bounding_box": None,
    }


def _normalize_evidence_list(raw_evidence: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_evidence, list):
        return []

    normalized: list[dict[str, Any]] = []

    for item in raw_evidence:
        if not isinstance(item, dict):
            continue

        normalized.append(
            {
                "source_file": _safe_string(item.get("source_file"), "unknown"),
                "page_number": _to_int(item.get("page_number"), 1),
                "field_name": _safe_string(item.get("field_name"), "unknown"),
                "bounding_box": item.get("bounding_box"),
            }
        )

    return normalized


def _normalize_finding(raw: dict[str, Any], fallback_agent: str) -> dict[str, Any]:
    description = _safe_string(
        raw.get("description")
        or raw.get("message")
        or raw.get("reason")
        or raw.get("summary")
        or "Finding generated by upstream agent."
    )

    evidence = (
        raw.get("evidence_pointers")
        or raw.get("evidence")
        or raw.get("evidence_links")
        or []
    )

    finding_id = _safe_string(
        raw.get("finding_id")
        or raw.get("id")
        or _stable_id(
            fallback_agent.upper().replace(" ", "-"),
            description,
    )
)

    return {
        "finding_id": finding_id,
        "agent_source": _safe_string(raw.get("agent_source") or fallback_agent),
        "severity": _normalize_severity(raw.get("severity")),
        "confidence": _to_float(raw.get("confidence"), 0.80),
        "confidence_explanation": _safe_string(
            raw.get("confidence_explanation")
            or "Normalized by Agent H from upstream artifact."
        ),
        "description": description,
        "evidence_pointers": _normalize_evidence_list(evidence),
        "recommended_action": _safe_string(
            raw.get("recommended_action")
            or raw.get("next_action")
            or "Review this finding before final approval."
        ),
    }


def _collect_findings_recursive(data: Any, fallback_agent: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    if isinstance(data, dict):
        if isinstance(data.get("findings"), list):
            for raw_finding in data["findings"]:
                if isinstance(raw_finding, dict):
                    findings.append(_normalize_finding(raw_finding, fallback_agent))

        for value in data.values():
            findings.extend(_collect_findings_recursive(value, fallback_agent))

    elif isinstance(data, list):
        for item in data:
            findings.extend(_collect_findings_recursive(item, fallback_agent))

    return findings


def _finding_from_context_risk_flag(flag: str) -> dict[str, Any]:
    normalized_flag = flag.upper()

    severity = "WARNING"

    if normalized_flag in {"NON_PREFERRED_VENDOR", "HIGH_VALUE_SOLE_SOURCE"}:
        severity = "EXCEPTION"

    if normalized_flag in {"MISSING_REQUIRED_FIELD", "INVALID_REQUISITION"}:
        severity = "BLOCK"

    return {
        "finding_id": f"AGENT-A-{normalized_flag}",
        "agent_source": "Agent A",
        "severity": severity,
        "confidence": 0.90,
        "confidence_explanation": "Risk flag detected during intake and context processing.",
        "description": f"Agent A detected early risk flag: {normalized_flag}.",
        "evidence_pointers": [
            _default_evidence("context_packet.json", "risk_flags")
        ],
        "recommended_action": (
            "Route to downstream validation agents and review before final approval."
        ),
    }


def _derive_budget_findings(budget_check: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    status = _safe_string(
        budget_check.get("overall_status")
        or budget_check.get("status")
    ).upper()

    if status in {"EXCEEDED", "OVER_BUDGET", "BUDGET_EXCEEDED", "FAILED", "BLOCKED"}:
        findings.append(
            {
                "finding_id": "AGENT-C-BUDGET-EXCEEDED",
                "agent_source": "Agent C",
                "severity": "BLOCK",
                "confidence": 0.95,
                "confidence_explanation": f"Budget overall status is {status}.",
                "description": "Requested amount exceeds available budget.",
                "evidence_pointers": [
                    _default_evidence("budget_check.json", "overall_status")
                ],
                "recommended_action": (
                    "Block PO creation and route to Finance for budget review."
                ),
            }
        )

    elif status in {"BORDERLINE", "NEAR_LIMIT", "WARNING"}:
        findings.append(
            {
                "finding_id": "AGENT-C-BUDGET-BORDERLINE",
                "agent_source": "Agent C",
                "severity": "WARNING",
                "confidence": 0.85,
                "confidence_explanation": f"Budget overall status is {status}.",
                "description": "Requested amount is close to available budget or period cap.",
                "evidence_pointers": [
                    _default_evidence("budget_check.json", "overall_status")
                ],
                "recommended_action": (
                    "Request finance confirmation before approval."
                ),
            }
        )

    return findings


def _derive_vendor_findings(vendor_match: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    status = _safe_string(
        vendor_match.get("overall_status")
        or vendor_match.get("status")
    ).upper()

    if status in {
        "NON_PREFERRED",
        "NOT_PREFERRED",
        "NOT_APPROVED",
        "NOT_FOUND",
        "EXCEPTION",
        "FAILED",
    }:
        findings.append(
            {
                "finding_id": "AGENT-D-VENDOR-ISSUE",
                "agent_source": "Agent D",
                "severity": "EXCEPTION",
                "confidence": 0.90,
                "confidence_explanation": f"Vendor overall status is {status}.",
                "description": (
                    "Vendor matching detected a non-preferred, missing, or problematic vendor."
                ),
                "evidence_pointers": [
                    _default_evidence("vendor_match.json", "overall_status")
                ],
                "recommended_action": (
                    "Route to Procurement Manager for vendor validation."
                ),
            }
        )

    return findings


def _derive_policy_findings(policy_check: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not policy_check:
        return []

    findings: list[dict[str, Any]] = []

    compliance = _safe_string(
        policy_check.get("overall_compliance")
        or policy_check.get("overall_status")
        or policy_check.get("status")
    ).upper()

    if compliance in {"NON_COMPLIANT", "FAILED", "BLOCKED", "POLICY_VIOLATION"}:
        findings.append(
            {
                "finding_id": "AGENT-E-POLICY-NON-COMPLIANT",
                "agent_source": "Agent E",
                "severity": "BLOCK",
                "confidence": 0.95,
                "confidence_explanation": f"Policy overall compliance is {compliance}.",
                "description": "Policy engine detected a non-compliant procurement request.",
                "evidence_pointers": [
                    _default_evidence("compliance_findings.json", "overall_compliance")
                ],
                "recommended_action": (
                    "Block or escalate until the policy issue is resolved."
                ),
            }
        )

    elif compliance in {"PARTIAL", "EXCEPTION", "REQUIRES_APPROVAL", "WARNING"}:
        findings.append(
            {
                "finding_id": "AGENT-E-POLICY-EXCEPTION",
                "agent_source": "Agent E",
                "severity": "EXCEPTION",
                "confidence": 0.90,
                "confidence_explanation": f"Policy overall compliance is {compliance}.",
                "description": "Policy engine detected a compliance exception condition.",
                "evidence_pointers": [
                    _default_evidence("compliance_findings.json", "overall_compliance")
                ],
                "recommended_action": (
                    "Route to compliance or procurement approval."
                ),
            }
        )

    return findings


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for finding in findings:
        key = (
            _safe_string(finding.get("agent_source")).lower(),
            _safe_string(finding.get("severity")).upper(),
            _safe_string(finding.get("description")).lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(finding)

    return deduped


def _severity_priority(finding: dict[str, Any]) -> int:
    severity = _safe_string(finding.get("severity")).upper()

    if severity == "BLOCK":
        return 0

    if severity == "EXCEPTION":
        return 1

    return 2


def _prioritize_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda item: (
            _severity_priority(item),
            _safe_string(item.get("agent_source")),
            _safe_string(item.get("finding_id")),
        ),
    )


def _decide(findings: list[dict[str, Any]]) -> str:
    severities = {
        _safe_string(finding.get("severity")).upper()
        for finding in findings
    }

    if "BLOCK" in severities:
        return "BLOCKED"

    if "EXCEPTION" in severities:
        return "REQUIRES_APPROVAL"

    if "WARNING" in severities:
        return "MANUAL_REVIEW"

    return "AUTO_APPROVE"


def _responsible_for_finding(finding: dict[str, Any]) -> str:
    text = (
        _safe_string(finding.get("agent_source"))
        + " "
        + _safe_string(finding.get("description"))
    ).lower()

    if "budget" in text or "finance" in text:
        return "Finance Controller"

    if "vendor" in text or "supplier" in text or "catalogue" in text:
        return "Procurement Manager"

    if "policy" in text or "compliance" in text or "sole" in text or "bid" in text:
        return "Compliance Officer"

    if _safe_string(finding.get("severity")).upper() == "BLOCK":
        return "Procurement Lead"

    return "Requester or Buyer"


def _approval_role_for_finding(finding: dict[str, Any]) -> str:
    responsible = _responsible_for_finding(finding)

    if responsible == "Finance Controller":
        return "Finance Approver"

    if responsible == "Procurement Manager":
        return "Procurement Approver"

    if responsible == "Compliance Officer":
        return "Compliance Approver"

    if responsible == "Procurement Lead":
        return "Procurement Lead"

    return "Department Manager"


def _fallback_decision_summary(decision: str, findings: list[dict[str, Any]]) -> str:
    if decision == "AUTO_APPROVE":
        return "No findings were detected. The PR can be auto-approved."

    if decision == "BLOCKED":
        return "At least one blocking finding was detected. PO creation must be blocked until the issue is resolved."

    if decision == "REQUIRES_APPROVAL":
        return "Exception findings were detected. The PR requires approval routing before PO creation."

    return "Warning findings were detected. The PR requires manual review."


def _fallback_final_reasoning(decision: str, findings: list[dict[str, Any]]) -> str:
    counts = {
        "BLOCK": 0,
        "EXCEPTION": 0,
        "WARNING": 0,
    }

    for finding in findings:
        severity = _safe_string(finding.get("severity")).upper()

        if severity in counts:
            counts[severity] += 1

    return (
        f"Agent H selected {decision} using deterministic severity priority. "
        f"Counts: BLOCK={counts['BLOCK']}, "
        f"EXCEPTION={counts['EXCEPTION']}, WARNING={counts['WARNING']}."
    )


def _fallback_open_questions(decision: str, findings: list[dict[str, Any]]) -> list[str]:
    if decision == "AUTO_APPROVE":
        return []

    questions: list[str] = []

    for finding in findings:
        severity = _safe_string(finding.get("severity")).upper()
        description = _safe_string(finding.get("description"))

        if severity == "BLOCK":
            questions.append(f"Resolve blocking issue: {description}")
        elif severity == "EXCEPTION":
            questions.append(f"Approval required: {description}")
        else:
            questions.append(f"Review warning: {description}")

    return questions


def _safe_json_from_text(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1).strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end > start:
        possible_json = cleaned[start : end + 1]

        try:
            return json.loads(possible_json)
        except json.JSONDecodeError:
            return None

    return None


def _generate_llm_explanation(
    decision: str,
    findings: list[dict[str, Any]],
    context_packet: dict[str, Any],
    budget_check: dict[str, Any],
    vendor_match: dict[str, Any],
    policy_check: dict[str, Any] | None,
    use_llm: bool,
    llm_provider: str,
    llm_model: str | None,
) -> dict[str, Any]:
    fallback = {
        "summary": _fallback_decision_summary(decision, findings),
        "final_reasoning": _fallback_final_reasoning(decision, findings),
        "open_questions": _fallback_open_questions(decision, findings),
        "executive_summary": _fallback_decision_summary(decision, findings),
        "llm_used": False,
        "llm_provider": None,
        "llm_model": None,
    }

    if not use_llm:
        return fallback

    prompt_payload = {
        "decision": decision,
        "context_packet": context_packet,
        "budget_status": budget_check.get("overall_status") or budget_check.get("status"),
        "vendor_status": vendor_match.get("overall_status") or vendor_match.get("status"),
        "policy_status": (
            policy_check.get("overall_compliance")
            or policy_check.get("overall_status")
            or policy_check.get("status")
            if policy_check
            else "NOT_PROVIDED"
        ),
        "findings": findings,
    }

    system_prompt = (
        "You are Agent H in an intelligent procurement review system. "
        "Do not change the final decision. The decision is already calculated by deterministic rules. "
        "Your job is only to write a concise procurement explanation. "
        "Return valid JSON only with keys: summary, final_reasoning, open_questions, executive_summary."
    )

    user_prompt = (
        "Create a human-readable explanation for the following procurement decision. "
        "Do not invent facts. Do not change the decision.\n\n"
        f"{json.dumps(prompt_payload, indent=2, default=str)}"
    )

    try:
        provider = llm_provider.lower().strip()

        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")

            if not api_key:
                return fallback

            from langchain_groq import ChatGroq

            model = llm_model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            llm = ChatGroq(
                model=model,
                temperature=0,
                groq_api_key=api_key,
            )

            response = llm.invoke(
                [
                    ("system", system_prompt),
                    ("human", user_prompt),
                ]
            )

            text = response.content

        elif provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

            if not api_key:
                return fallback

            import google.generativeai as genai

            model_name = llm_model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            response = model.generate_content(
                f"{system_prompt}\n\n{user_prompt}"
            )

            text = response.text or ""
            model = model_name

        else:
            return fallback

        parsed = _safe_json_from_text(text)

        if parsed is None:
            return {
                "summary": _safe_string(text[:800], fallback["summary"]),
                "final_reasoning": fallback["final_reasoning"],
                "open_questions": fallback["open_questions"],
                "executive_summary": _safe_string(text[:1200], fallback["executive_summary"]),
                "llm_used": True,
                "llm_provider": provider,
                "llm_model": model,
            }

        return {
            "summary": _safe_string(parsed.get("summary"), fallback["summary"]),
            "final_reasoning": _safe_string(
                parsed.get("final_reasoning"),
                fallback["final_reasoning"],
            ),
            "open_questions": (
                parsed.get("open_questions")
                if isinstance(parsed.get("open_questions"), list)
                else fallback["open_questions"]
            ),
            "executive_summary": _safe_string(
                parsed.get("executive_summary"),
                fallback["executive_summary"],
            ),
            "llm_used": True,
            "llm_provider": provider,
            "llm_model": model,
        }

    except Exception as exc:
        if os.getenv("AGENT_H_LLM_DEBUG") == "1":
            print(f"LLM explanation failed: {exc}")

        return fallback


def _extract_line_items(extracted_pr: dict[str, Any]) -> list[dict[str, Any]]:
    line_items = extracted_pr.get("line_items")

    if isinstance(line_items, list):
        return line_items

    items = extracted_pr.get("items")

    if isinstance(items, list):
        return items

    return []


def _extract_currency(
    context_packet: dict[str, Any],
    extracted_pr: dict[str, Any],
) -> str:
    for artifact in [extracted_pr, context_packet]:
        currency = artifact.get("currency")

        if currency:
            return _safe_string(currency)

        header = artifact.get("header")

        if isinstance(header, dict) and header.get("currency"):
            return _safe_string(header["currency"])

    return "UNKNOWN"


def _po_status_from_decision(decision: str) -> str:
    mapping = {
        "AUTO_APPROVE": "READY",
        "REQUIRES_APPROVAL": "PENDING_APPROVAL",
        "MANUAL_REVIEW": "UNDER_REVIEW",
        "BLOCKED": "BLOCKED",
    }

    return mapping.get(decision, "UNDER_REVIEW")

def _build_po_draft(
    run_id: str,
    decision: str,
    context_packet: dict[str, Any],
    extracted_pr: dict[str, Any],
) -> dict[str, Any]:
    status = _po_status_from_decision(decision)
    requester = _safe_string(
        extracted_pr.get("requester")
        or context_packet.get("requester")
        or (extracted_pr.get("header") or {}).get("requester")
    )

    department = _safe_string(
        extracted_pr.get("department")
        or context_packet.get("department")
        or (extracted_pr.get("header") or {}).get("department")
    )

    currency = _extract_currency(context_packet, extracted_pr)

    po_items: list[dict[str, Any]] = []

    for index, item in enumerate(_extract_line_items(extracted_pr), start=1):
        quantity = _to_int(item.get("quantity"), 1)
        unit_price = _to_float(item.get("unit_price"), 0.0)
        total_price = _to_float(
            item.get("total_price"),
            quantity * unit_price,
        )

        po_items.append(
            {
                "line_number": _to_int(item.get("line_number"), index),
                "item_name": _safe_string(
                    item.get("item_name")
                    or item.get("description")
                    or item.get("name"),
                    "UNKNOWN_ITEM",
                ),
                "quantity": max(quantity, 1),
                "unit_price": max(unit_price, 0.0),
                "total_price": max(total_price, 0.0),
                "vendor": _safe_string(
                    item.get("requested_vendor")
                    or item.get("vendor")
                    or item.get("matched_vendor"),
                    "UNKNOWN_VENDOR",
                ),
                "cost_center": _safe_string(
                    item.get("cost_center")
                    or context_packet.get("cost_center"),
                    "UNKNOWN_CC",
                ),
                "gl_account": _safe_string(
                    item.get("gl_account"),
                    "UNKNOWN_GL",
                ),
            }
        )

    total_value = _to_float(
        extracted_pr.get("total_value")
        or context_packet.get("total_estimated_value"),
        0.0,
    )

    return {
        "run_id": run_id,
        "po_number": f"PO-DRAFT-{run_id}",
        "requester": requester,
        "department": department,
        "line_items": po_items,
        "total_value": total_value,
        "currency": currency,
        "status": status,
    }


def _build_exceptions_report(
    run_id: str,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    exceptions: list[dict[str, Any]] = []

    for finding in findings:
        exceptions.append(
            {
                "exception_id": f"EX-{finding['finding_id']}",
                "severity": finding["severity"],
                "agent_source": finding["agent_source"],
                "description": finding["description"],
                "next_action": finding["recommended_action"],
                "responsible": _responsible_for_finding(finding),
                "evidence": finding.get("evidence_pointers", []),
            }
        )

    return {
        "run_id": run_id,
        "total_exceptions": len(exceptions),
        "exceptions": exceptions,
    }


def _build_approval_packet(
    run_id: str,
    decision: str,
    findings: list[dict[str, Any]],
    llm_explanation: dict[str, Any],
) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, int]] = set()

    if decision != "AUTO_APPROVE":
        for finding in findings:
            severity = _safe_string(finding.get("severity")).upper()

            if severity in {"BLOCK", "EXCEPTION", "WARNING"}:
                role = _approval_role_for_finding(finding)
                deadline_hours = 24 if severity == "BLOCK" else 48
                route_key = (role, deadline_hours)

                if route_key in seen_routes:
                    continue

                seen_routes.add(route_key)

                routes.append(
                    {
                        "approver_role": role,
                        "approver_name": None,
                        "reason": finding["description"],
                        "evidence_pointers": finding.get("evidence_pointers", []),
                        "deadline_hours": deadline_hours,
                    }
                )

    return {
        "run_id": run_id,
        "decision": decision,
        "approval_routes": routes,
        "all_findings": findings,
        "summary": llm_explanation["summary"],
        "final_reasoning": llm_explanation["final_reasoning"],
        "open_questions": llm_explanation["open_questions"],
        "human_review_required": decision != "AUTO_APPROVE",
        "confidence_score": _overall_confidence(findings),
        "po_draft_reference": "po_draft.json",
        "llm_used": llm_explanation["llm_used"],
        "llm_provider": llm_explanation["llm_provider"],
        "llm_model": llm_explanation["llm_model"],
    }


def _build_audit_log(
    run_id: str,
    bundle_path: str,
    decision: str,
    loaded_artifacts: list[str],
    findings: list[dict[str, Any]],
    start_time: float,
    llm_explanation: dict[str, Any],
) -> dict[str, Any]:
    completed_at = datetime.now().isoformat()
    started_at = datetime.fromtimestamp(start_time).isoformat()
    duration_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "run_id": run_id,
        "bundle_path": bundle_path,
        "started_at": started_at,
        "completed_at": completed_at,
        "final_decision": decision,
        "llm_used": llm_explanation["llm_used"],
        "steps": [
            {
                "timestamp": completed_at,
                "agent_name": "Agent H",
                "action": "Loaded upstream artifacts",
                "input_summary": f"Loaded artifacts: {', '.join(loaded_artifacts)}",
                "output_summary": "Artifacts loaded for final orchestration.",
                "tools_called": ["json_loader"],
                "decision": None,
                "duration_ms": duration_ms,
            },
            {
                "timestamp": completed_at,
                "agent_name": "Agent H",
                "action": "Merged and deduplicated findings",
                "input_summary": (
                    f"Findings were collected from {len(loaded_artifacts)} artifacts."
                ),
                "output_summary": f"{len(findings)} unique findings prioritized.",
                "tools_called": [
                    "collect_findings",
                    "dedupe_findings",
                    "prioritize_findings",
                ],
                "decision": None,
                "duration_ms": duration_ms,
            },
            {
                "timestamp": completed_at,
                "agent_name": "Agent H",
                "action": "Applied final decision matrix",
                "input_summary": "Priority order: BLOCK, EXCEPTION, WARNING, clean.",
                "output_summary": f"Final decision: {decision}",
                "tools_called": ["decision_matrix"],
                "decision": decision,
                "duration_ms": duration_ms,
            },
            {
                "timestamp": completed_at,
                "agent_name": "Agent H",
                "action": "Generated explanation",
                "input_summary": "Structured decision and findings.",
                "output_summary": (
                    "LLM explanation generated."
                    if llm_explanation["llm_used"]
                    else "Fallback deterministic explanation generated."
                ),
                "tools_called": (
                    ["llm"]
                    if llm_explanation["llm_used"]
                    else ["fallback_reasoning"]
                ),
                "decision": decision,
                "duration_ms": duration_ms,
            },
        ],
    }


def _overall_confidence(findings: list[dict[str, Any]]) -> float:
    if not findings:
        return 1.0

    values = [_to_float(finding.get("confidence"), 0.80) for finding in findings]
    return round(sum(values) / len(values), 2)


def _confidence_per_agent(findings: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}

    for finding in findings:
        agent = _safe_string(finding.get("agent_source"), "Unknown Agent")
        grouped.setdefault(agent, []).append(
            _to_float(finding.get("confidence"), 0.80)
        )

    return {
        agent: round(sum(values) / len(values), 2)
        for agent, values in grouped.items()
        if values
    }


def _derive_vendor_match_rate(vendor_match: dict[str, Any]) -> float:
    matches = vendor_match.get("line_matches") or vendor_match.get("matches") or []

    if not isinstance(matches, list) or not matches:
        status = _safe_string(
            vendor_match.get("overall_status") or vendor_match.get("status")
        ).upper()

        if status in {"MATCHED", "OK", "AVAILABLE", "COMPLIANT"}:
            return 1.0

        if status:
            return 0.0

        return 0.0

    successful = 0

    for match in matches:
        if not isinstance(match, dict):
            continue

        status = _safe_string(match.get("status")).upper()
        is_preferred = _to_bool(match.get("is_preferred"))

        if status in {"MATCHED", "OK", "PREFERRED"} or is_preferred:
            successful += 1

    return round(successful / len(matches), 2)


def _build_metrics(
    run_id: str,
    start_time: float,
    extracted_pr: dict[str, Any],
    vendor_match: dict[str, Any],
    findings: list[dict[str, Any]],
    decision: str,
) -> dict[str, Any]:
    total_seconds = round(time.time() - start_time, 2)
    line_items = _extract_line_items(extracted_pr)
    total_line_items = len(line_items)

    exception_count = len(
        [
            finding
            for finding in findings
            if _safe_string(finding.get("severity")).upper() in {"BLOCK", "EXCEPTION"}
        ]
    )

    if total_line_items > 0:
        exception_rate = min(round(exception_count / total_line_items, 2), 1.0)
    else:
        exception_rate = 0.0

    items_excepted = min(exception_count, total_line_items)

    extraction_accuracy = _to_float(
        extracted_pr.get("overall_confidence"),
        1.0 if total_line_items > 0 else 0.0,
    )

    return {
        "run_id": run_id,
        "total_time_seconds": total_seconds,
        "extraction_accuracy": extraction_accuracy,
        "vendor_match_rate": _derive_vendor_match_rate(vendor_match),
        "exception_rate": exception_rate,
        "confidence_avg": _overall_confidence(findings),
        "confidence_per_agent": _confidence_per_agent(findings),
        "agents_timing": {
            "Agent H": round(total_seconds * 1000, 2),
        },
        "total_line_items": total_line_items,
        "items_auto_approved": total_line_items if decision == "AUTO_APPROVE" else 0,
        "items_excepted": items_excepted,
        "items_blocked": total_line_items if decision == "BLOCKED" else 0,
        "throughput_prs_per_hour": (
            round(3600 / total_seconds, 2) if total_seconds > 0 else 0.0
        ),
    }


def _exceptions_markdown(report: dict[str, Any], decision: str) -> str:
    lines = [
        f"# Exceptions Report - {report['run_id']}",
        "",
        f"Final decision: {decision}",
        f"Total exceptions/findings: {report['total_exceptions']}",
        "",
        "---",
        "",
    ]

    if not report["exceptions"]:
        lines.append("No exceptions found.")
        lines.append("")

    for exception in report["exceptions"]:
        lines.extend(
            [
                f"## [{exception['severity']}] {exception['exception_id']}",
                "",
                f"- Agent: {exception['agent_source']}",
                f"- Description: {exception['description']}",
                f"- Next action: {exception['next_action']}",
                f"- Responsible: {exception['responsible']}",
            ]
        )

        if exception.get("evidence"):
            lines.append("- Evidence:")

            for evidence in exception["evidence"]:
                lines.append(
                    f"  - {evidence.get('source_file')} | "
                    f"page={evidence.get('page_number')} | "
                    f"field={evidence.get('field_name')}"
                )

        lines.append("")

    return "\n".join(lines)


def _audit_markdown(audit_log: dict[str, Any]) -> str:
    lines = [
        f"# Audit Log - {audit_log['run_id']}",
        "",
        f"Final decision: {audit_log['final_decision']}",
        f"Started at: {audit_log['started_at']}",
        f"Completed at: {audit_log['completed_at']}",
        f"LLM used: {audit_log['llm_used']}",
        "",
        "---",
        "",
    ]

    for step in audit_log["steps"]:
        lines.extend(
            [
                f"## {step['agent_name']} - {step['action']}",
                "",
                f"- Timestamp: {step['timestamp']}",
                f"- Input: {step['input_summary']}",
                f"- Output: {step['output_summary']}",
                f"- Tools: {', '.join(step['tools_called'])}",
                f"- Decision: {step['decision'] or 'N/A'}",
                f"- Duration: {step['duration_ms']}ms",
                "",
            ]
        )

    return "\n".join(lines)


def _load_policy_artifact(run_id: str) -> tuple[dict[str, Any] | None, str | None]:
    for filename in OPTIONAL_POLICY_ARTIFACTS:
        data = _read_json_if_exists(run_id, filename)

        if data is not None:
            return data, filename

    return None, None


def _load_all_artifacts(
    run_id: str,
    require_policy: bool,
) -> tuple[dict[str, Any], list[str]]:
    artifacts: dict[str, Any] = {}
    loaded_files: list[str] = []

    for filename in REQUIRED_ARTIFACTS:
        data = _read_required_json(run_id, filename)
        key = filename.replace(".json", "")
        artifacts[key] = data
        loaded_files.append(filename)

    policy_data, policy_filename = _load_policy_artifact(run_id)

    if policy_data is not None:
        artifacts["policy_check"] = policy_data
        loaded_files.append(policy_filename or "policy_check.json")
    elif require_policy:
        raise FileNotFoundError(
            f"Policy artifact not found for run_id={run_id}"
        )

    for filename in OPTIONAL_ANOMALY_ARTIFACTS:
        anomaly_data = _read_json_if_exists(run_id, filename)

        if anomaly_data is not None:
            artifacts["anomaly_check"] = anomaly_data
            loaded_files.append(filename)
            break

    return artifacts, loaded_files


def _collect_all_findings(
    context_packet: dict[str, Any],
    extracted_pr: dict[str, Any],
    budget_check: dict[str, Any],
    vendor_match: dict[str, Any],
    policy_check: dict[str, Any] | None,
    anomaly_check: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for flag in context_packet.get("risk_flags", []):
        findings.append(_finding_from_context_risk_flag(_safe_string(flag)))

    findings.extend(_collect_findings_recursive(extracted_pr, "Agent B"))
    findings.extend(_collect_findings_recursive(budget_check, "Agent C"))
    findings.extend(_collect_findings_recursive(vendor_match, "Agent D"))

    if policy_check is not None:
        findings.extend(_collect_findings_recursive(policy_check, "Agent E"))

    if anomaly_check is not None:
        findings.extend(_collect_findings_recursive(anomaly_check, "Agent G"))

    findings.extend(_derive_budget_findings(budget_check))
    findings.extend(_derive_vendor_findings(vendor_match))
    findings.extend(_derive_policy_findings(policy_check))

    return _prioritize_findings(_dedupe_findings(findings))


def run_agent_h(
    run_id: str,
    bundle_path: str = "",
    require_policy: bool = False,
    use_llm: bool = False,
    llm_provider: str = "groq",
    llm_model: str | None = None,
    audit_logger: Any = None,
    metrics_tracker: Any = None,
) -> dict[str, Any]:
    """
    Agent H - Final orchestration, exception triage, approval routing, and PO draft.

    Required input artifacts from runs/{run_id}/:
    - context_packet.json
    - extracted_pr.json
    - budget_check.json
    - vendor_match.json

    Optional policy artifact:
    - policy_check.json
    - compliance_findings.json

    Output artifacts:
    - exceptions.md
    - approval_packet.json
    - po_draft.json
    - audit_log.md
    - audit_log.json
    - metrics.json
    """
    agent_name = "Agent H"

    _safe_audit_start(
        audit_logger,
        agent_name,
        f"Starting Agent H final orchestration for run_id={run_id}",
    )
    _safe_metrics_start(metrics_tracker, agent_name)

    start_time = time.time()

    try:
        artifacts, loaded_files = _load_all_artifacts(
            run_id=run_id,
            require_policy=require_policy,
        )

        _safe_audit_tool_call(audit_logger, "load_upstream_artifacts")

        context_packet = artifacts["context_packet"]
        extracted_pr = artifacts["extracted_pr"]
        budget_check = artifacts["budget_check"]
        vendor_match = artifacts["vendor_match"]
        policy_check = artifacts.get("policy_check")
        anomaly_check = artifacts.get("anomaly_check")

        findings = _collect_all_findings(
            context_packet=context_packet,
            extracted_pr=extracted_pr,
            budget_check=budget_check,
            vendor_match=vendor_match,
            policy_check=policy_check,
            anomaly_check=anomaly_check,
        )

        decision = _decide(findings)

        _safe_audit_tool_call(audit_logger, "decision_matrix")

        llm_explanation = _generate_llm_explanation(
            decision=decision,
            findings=findings,
            context_packet=context_packet,
            budget_check=budget_check,
            vendor_match=vendor_match,
            policy_check=policy_check,
            use_llm=use_llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )

        if llm_explanation["llm_used"]:
            _safe_audit_tool_call(audit_logger, "llm_explanation")
        else:
            _safe_audit_tool_call(audit_logger, "fallback_reasoning")

        po_draft = _build_po_draft(
            run_id=run_id,
            decision=decision,
            context_packet=context_packet,
            extracted_pr=extracted_pr,
        )

        approval_packet = _build_approval_packet(
            run_id=run_id,
            decision=decision,
            findings=findings,
            llm_explanation=llm_explanation,
        )

        exceptions_report = _build_exceptions_report(
            run_id=run_id,
            findings=findings,
        )

        audit_log = _build_audit_log(
            run_id=run_id,
            bundle_path=bundle_path,
            decision=decision,
            loaded_artifacts=loaded_files,
            findings=findings,
            start_time=start_time,
            llm_explanation=llm_explanation,
        )

        metrics = _build_metrics(
            run_id=run_id,
            start_time=start_time,
            extracted_pr=extracted_pr,
            vendor_match=vendor_match,
            findings=findings,
            decision=decision,
        )

        _write_json(run_id, "approval_packet.json", approval_packet)
        _write_json(run_id, "po_draft.json", po_draft)
        _write_json(run_id, "audit_log.json", audit_log)
        _write_json(run_id, "metrics.json", metrics)

        _write_markdown(
            run_id,
            "exceptions.md",
            _exceptions_markdown(exceptions_report, decision),
        )

        _write_markdown(
            run_id,
            "audit_log.md",
            _audit_markdown(audit_log),
        )

        confidence_avg = _overall_confidence(findings)
        exception_rate = _to_float(metrics.get("exception_rate"), 0.0)

        _safe_metrics_log_exception_rate(
            metrics_tracker,
            rate=exception_rate,
            agent_name=agent_name,
        )
        _safe_metrics_log_confidence_avg(metrics_tracker, confidence_avg)

        result = {
            "run_id": run_id,
            "decision": decision,
            "total_findings": len(findings),
            "llm_used": llm_explanation["llm_used"],
            "artifacts_written": [
                "exceptions.md",
                "approval_packet.json",
                "po_draft.json",
                "audit_log.md",
                "audit_log.json",
                "metrics.json",
            ],
        }

        _safe_audit_end(
            audit_logger,
            agent_name,
            (
                f"Agent H completed. decision={decision}, "
                f"total_findings={len(findings)}, "
                f"llm_used={llm_explanation['llm_used']}"
            ),
            decision=decision,
        )

        _safe_metrics_end(
            metrics_tracker,
            agent_name,
            confidence=confidence_avg,
        )

        return result

    except Exception as exc:
        _safe_audit_error(
            audit_logger,
            agent_name,
            str(exc),
        )

        _safe_metrics_end(
            metrics_tracker,
            agent_name,
            confidence=0.0,
        )

        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Agent H final orchestration"
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID, for example PRBUNDLE002 or run_20260616_120000_abc123",
    )

    parser.add_argument(
        "--bundle-path",
        default="",
        help="Original PR bundle path",
    )

    parser.add_argument(
        "--require-policy",
        action="store_true",
        help="Require policy_check.json or compliance_findings.json",
    )

    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use optional LLM explanation layer",
    )

    parser.add_argument(
        "--llm-provider",
        default="groq",
        choices=["groq", "gemini"],
        help="LLM provider for explanation layer",
    )

    parser.add_argument(
        "--llm-model",
        default=None,
        help="Optional LLM model name",
    )

    args = parser.parse_args()

    result = run_agent_h(
        run_id=args.run_id,
        bundle_path=args.bundle_path,
        require_policy=args.require_policy,
        use_llm=args.use_llm,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
    )

    print("Agent H completed successfully.")
    print(f"Run ID: {result['run_id']}")
    print(f"Decision: {result['decision']}")
    print(f"Total findings: {result['total_findings']}")
    print(f"LLM used: {result['llm_used']}")
    print("Artifacts written:")

    for artifact in result["artifacts_written"]:
        print(f"- runs/{result['run_id']}/{artifact}")


if __name__ == "__main__":
    main()