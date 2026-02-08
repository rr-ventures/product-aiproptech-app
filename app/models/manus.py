"""Manus agent client — long-running task dispatch (DD copilot).

Manus integration is designed as a pluggable stub:
- If MANUS_API_URL + MANUS_API_KEY are set → dispatch tasks via API.
- Otherwise → generate a structured job prompt that the user can
  manually paste into the Manus web UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import MANUS_API_KEY, MANUS_API_URL


def is_configured() -> bool:
    """Check if Manus API credentials are available."""
    return bool(MANUS_API_URL and MANUS_API_KEY)


def create_job_prompt(
    task_description: str,
    checklist_items: list[dict[str, Any]] | None = None,
    attachments_summary: str = "",
) -> str:
    """
    Build a structured Manus job prompt.

    This can be used directly (paste into Manus UI) or sent via API.
    """
    prompt_parts = [
        "# Manus Agent Job — Due Diligence",
        "",
        "## Task",
        task_description,
        "",
    ]

    if checklist_items:
        prompt_parts.append("## Checklist Items")
        for i, item in enumerate(checklist_items, 1):
            name = item.get("name", item.get("item", f"Item {i}"))
            source = item.get("source", "TBD")
            prompt_parts.append(f"{i}. **{name}** — Source: {source}")
        prompt_parts.append("")

    if attachments_summary:
        prompt_parts.append("## Attachments / Context")
        prompt_parts.append(attachments_summary)
        prompt_parts.append("")

    prompt_parts.extend([
        "## Output Requirements",
        "- For each checklist item: provide PASS / FAIL / UNKNOWN + evidence notes",
        "- Take screenshots where applicable and save to the evidence folder",
        "- Provide source URLs for each finding",
        "- Flag any items that need human verification",
        "",
        "## Compliance Note",
        "Use only public / licensed data sources. Do not scrape behind authentication "
        "unless credentials are explicitly provided. Prefer official government portals, "
        "council websites, and licensed property data providers.",
    ])

    return "\n".join(prompt_parts)


async def dispatch_job(prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Dispatch a job to Manus via API.
    Returns a job reference dict with id and status.

    If Manus is not configured, returns a stub response
    instructing the user to use the prompt manually.
    """
    if not is_configured():
        return {
            "status": "manual_required",
            "message": (
                "Manus API is not configured. "
                "Copy the generated prompt and paste it into the Manus web UI."
            ),
            "prompt": prompt,
        }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MANUS_API_URL}/jobs",
            headers={"Authorization": f"Bearer {MANUS_API_KEY}"},
            json={"prompt": prompt, "context": context or {}},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
