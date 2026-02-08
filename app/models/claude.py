"""Claude reasoning client — structured report generation."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from app.config import CLAUDE_MODEL, require_anthropic


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=require_anthropic())


def reason(
    system_prompt: str,
    user_message: str,
    expect_json: bool = True,
    max_tokens: int = 8192,
) -> dict[str, Any] | str:
    """
    Send a reasoning request to Claude.

    If expect_json is True, attempts to parse response as JSON.
    Falls back to returning raw text on parse failure.
    """
    client = _get_client()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()

    if not expect_json:
        return raw

    # Strip markdown code fences if present
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_response": raw, "parse_error": True}


def chat(
    system_prompt: str,
    messages: list[dict[str, str]],
    max_tokens: int = 4096,
) -> str:
    """
    Multi-turn chat with Claude (used for reno interview).
    messages should be [{"role": "user"/"assistant", "content": "..."}]
    """
    client = _get_client()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text.strip()
