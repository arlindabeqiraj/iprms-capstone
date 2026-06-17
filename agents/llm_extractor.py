import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def extract_pr_from_text(text: str, run_id: str, source_file: str) -> dict:
    """
    Uses Groq LLM to convert raw requisition text
    into ExtractedPR-compatible JSON.
    """

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment.")

    client = Groq(api_key=api_key)

    prompt = f"""
You are Agent B in a procurement automation system.

Extract the purchase requisition information from the text below.

Return ONLY valid JSON.
No markdown.
No explanations.
No extra text.

The JSON MUST match this exact schema:

{{
  "run_id": "{run_id}",
  "pr_id": "PR-PDF-001",
  "header": {{
    "pr_number": "PR-PDF-001",
    "request_date": "2026-06-11T09:00:00",
    "required_by": "2026-06-20T17:00:00",
    "requester": "John Doe",
    "department": "IT",
    "cost_center": "CC100",
    "justification": "New laptops required for the development team."
  }},
  "line_items": [
    {{
      "line_number": 1,
      "item_name": "Dell Latitude Laptop",
      "quantity": 5,
      "unit_price": 900,
      "total_price": 4500,
      "cost_center": "CC100",
      "gl_account": "IT-HARDWARE",
      "currency": "EUR",
      "requested_vendor": "Dell",
      "confidence": 0.95,
      "evidence_pointers": [
        {{
          "source_file": "{source_file}",
          "page_number": 1,
          "field_name": "line_items[0]",
          "bounding_box": null
        }}
      ],
      "is_ambiguous": false,
      "ambiguity_reason": null
    }}
  ],
  "total_value": 4500,
  "extraction_method": "PDF_DIRECT",
  "overall_confidence": 0.95,
  "aggregation_notes": [
    "Extracted using Groq LLM from PDF text."
  ]
}}

Important rules:
- Return JSON only.
- Use "item_name", never "item".
- Use "total_price", never "total_cost".
- Every line item must include line_number, item_name, quantity, unit_price, total_price, cost_center, gl_account, currency, requested_vendor, confidence, evidence_pointers, is_ambiguous, and ambiguity_reason.
- If gl_account is missing from the source text, use "UNKNOWN".
- If currency is missing from the source text, use "EUR".
- Calculate total_price as quantity * unit_price.
- Calculate total_value as the sum of all line item total_price values.
- If a field is missing, use a reasonable placeholder and lower confidence.
- If item description is vague, set is_ambiguous to true and explain ambiguity_reason.
- Confidence values must be between 0 and 1.
- Use ISO datetime format for dates.
- Use bounding_box as null unless actual coordinates are available.

Source file:
{source_file}

Requisition text:
{text}
"""

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You extract procurement requisitions into strict JSON that matches a Pydantic schema.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except Exception as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\n\n{content}") from exc