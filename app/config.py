"""Global configuration — loads .env and exposes settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── paths ────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DEALS_DIR = ROOT_DIR / "deals"
PROMPTS_DIR = ROOT_DIR / "prompts"
TEMPLATES_DIR = ROOT_DIR / "templates"

# ── env ──────────────────────────────────────────────────────────────────
load_dotenv(ROOT_DIR / ".env")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MANUS_API_URL: str = os.getenv("MANUS_API_URL", "")
MANUS_API_KEY: str = os.getenv("MANUS_API_KEY", "")
DOMAIN_API_KEY: str = os.getenv("DOMAIN_API_KEY", "")

CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── validation helpers ───────────────────────────────────────────────────

def require_anthropic() -> str:
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY.startswith("sk-ant-..."):
        raise SystemExit(
            "❌  ANTHROPIC_API_KEY is not set. "
            "Copy .env.example → .env and add your key."
        )
    return ANTHROPIC_API_KEY


def require_gemini() -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("AIza..."):
        raise SystemExit(
            "❌  GEMINI_API_KEY is not set. "
            "Copy .env.example → .env and add your key."
        )
    return GEMINI_API_KEY
