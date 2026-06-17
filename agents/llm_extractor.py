import json
import os
import base64
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def extract_pr_from_text(text: str, run_id: str, source_file: str) -> dict:
    """
    Uses Groq LLM to convert raw requisition text
    into ExtractedPR-compatible JSON.
    """

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
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
    

def assess_item_ambiguity(item: dict) -> dict:
    """
    Uses Groq LLM to decide whether a line item description is too vague
    for reliable procurement pricing.
    """

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment.")

    client = Groq(api_key=api_key)

    prompt = f"""
You are Agent B in a procurement automation system.

Assess whether this purchase requisition line item is specific enough for reliable procurement pricing.

Return ONLY valid JSON in this exact format:

{{
  "is_ambiguous": false,
  "ambiguity_reason": null,
  "confidence_adjustment": 0.95
}}

Rules:
- If the item is too generic, set is_ambiguous=true.
- Examples of vague items: "laptop", "monitor", "software", "equipment", "device", "accessory", "cable", "hardware", "office supplies".
- A specific item includes enough detail for pricing, such as brand, model, size, type, specs, or catalogue-identifiable name.
- confidence_adjustment must be between 0 and 1.
- If ambiguous, explain briefly in ambiguity_reason.
- Return JSON only. No markdown.

Line item:
{json.dumps(item, indent=2)}
"""

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You assess procurement item ambiguity and return strict JSON.",
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
        raise ValueError(f"LLM returned invalid ambiguity JSON: {exc}\n\n{content}") from exc  
    

def extract_text_from_page_image(
    image_path: Path,
    page_number: int,
) -> str:
    """
    OCR-style fallback using Groq vision.

    Used when a PDF page has no reliable selectable text.
    Converts a rendered PDF page image into plain text.
    """

    api_key = os.getenv("GROQ_API_KEY")
    vision_model = os.getenv(
        "GROQ_VISION_MODEL",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    )

    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment.")

    client = Groq(api_key=api_key)

    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

    response = client.chat.completions.create(
        model=vision_model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an OCR assistant for procurement documents. "
                    "Read the image and return only the visible text. "
                    "Do not summarize. Do not add explanations."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Extract all readable text from this purchase "
                            f"requisition page. Page number: {page_number}. "
                            "Return plain text only."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded_image}"
                        },
                    },
                ],
            },
        ],
    )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise ValueError(
            f"Groq vision OCR returned empty text for page {page_number}."
        )

    return content.strip()