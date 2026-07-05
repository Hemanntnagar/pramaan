"""
ai_extract.py — server-side call to Claude for reading an invoice / e-way bill /
weighbridge slip and pulling out structured fields.

Doing this on the backend (instead of straight from the browser, as the
earlier demo did) means the API key never has to live in client-side code,
and this now works in any browser, not just inside Claude.ai.
"""

import base64
import json
import os
import re

import httpx

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You extract structured data from a single recycling/waste-management invoice, "
    "e-way bill, or weighbridge slip for an environmental compliance audit tool. "
    "Respond with ONLY a raw JSON object — no markdown formatting, no code fences, "
    "no commentary before or after it. Fields: invoice_no (string or null), "
    "date (string in YYYY-MM-DD format, or null), quantity_kg (number or null), "
    "rate_per_kg (number or null), facility_name (string or null). If a field is "
    "not clearly and confidently visible in the document, set it to null — never "
    "guess or invent a value."
)


class ExtractionError(Exception):
    pass


async def extract_fields(file_bytes: bytes, content_type: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ExtractionError(
            "No ANTHROPIC_API_KEY is set on the server. Add one to your .env file to enable "
            "AI document reading (see README.md) — manual entry still works without it."
        )

    media_type = content_type or "application/octet-stream"
    block_type = "document" if media_type == "application/pdf" else "image"
    b64 = base64.b64encode(file_bytes).decode("ascii")

    body = {
        "model": MODEL,
        "max_tokens": 1000,
        "system": SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": [
                {"type": block_type, "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": "Extract the fields from this document as instructed."},
            ],
        }],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)

    if resp.status_code != 200:
        raise ExtractionError(f"Claude API request failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    text_block = next((b for b in data.get("content", []) if b.get("type") == "text"), None)
    if not text_block:
        raise ExtractionError("No text content returned by the model.")

    cleaned = re.sub(r"```json|```", "", text_block["text"]).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Could not parse the model's response as JSON: {e}")
