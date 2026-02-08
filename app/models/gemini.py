"""Gemini vision client — extracts structured data from listing photos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.config import GEMINI_MODEL, require_gemini


def _load_image_part(photo_path: Path) -> types.Part:
    """Load an image file as a Gemini-compatible inline data part."""
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    suffix = photo_path.suffix.lower()
    mime = mime_map.get(suffix, "image/jpeg")
    data = photo_path.read_bytes()
    return types.Part.from_bytes(data=data, mime_type=mime)


def extract_listing_facts(
    photos: list[Path],
    prompt_text: str,
    deal_address: str = "",
) -> dict[str, Any]:
    """
    Send listing photos to Gemini and extract structured property facts.

    Returns a dict with keys like:
      bedrooms, bathrooms, car_spaces, land_area_sqm, building_area_sqm,
      property_type, condition_overall, condition_notes, finish_level,
      features, rooms_identified, renovation_notes, uncertainty_flags
    """
    api_key = require_gemini()
    client = genai.Client(api_key=api_key)

    # Build the content parts: prompt + images
    parts: list[types.Part] = [types.Part.from_text(text=prompt_text)]
    if deal_address:
        parts.append(types.Part.from_text(text=f"\nProperty address: {deal_address}\n"))

    for photo in photos[:20]:  # cap at 20 photos to stay within limits
        parts.append(_load_image_part(photo))

    parts.append(types.Part.from_text(
        text="\nRespond ONLY with valid JSON matching the schema described above. "
        "No markdown fences, no commentary."
    ))

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Content(role="user", parts=parts)],
    )
    raw = response.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_response": raw, "parse_error": True}
