"""Deal folder management — every deal gets its own directory tree."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DEALS_DIR


def _slugify(text: str) -> str:
    """Turn an address into a safe folder name."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def create_deal(address: str, listing_url: str = "", notes: str = "") -> Path:
    """Create a new deal folder and return its path."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(address)
    deal_dir = DEALS_DIR / f"{timestamp}_{slug}"
    for sub in ("inputs", "inputs/photos", "outputs", "logs"):
        (deal_dir / sub).mkdir(parents=True, exist_ok=True)

    meta = {
        "address": address,
        "listing_url": listing_url,
        "notes": notes,
        "created_at": datetime.now().isoformat(),
        "status": "created",
    }
    (deal_dir / "deal.json").write_text(json.dumps(meta, indent=2))
    return deal_dir


def load_deal(deal_dir: Path) -> dict[str, Any]:
    """Load deal metadata."""
    return json.loads((deal_dir / "deal.json").read_text())


def save_deal_meta(deal_dir: Path, meta: dict[str, Any]) -> None:
    """Persist updated deal metadata."""
    (deal_dir / "deal.json").write_text(json.dumps(meta, indent=2))


def add_photos(deal_dir: Path, photo_paths: list[str]) -> list[Path]:
    """Copy photos into the deal's inputs/photos folder. Returns new paths."""
    dest_dir = deal_dir / "inputs" / "photos"
    copied: list[Path] = []
    for p in photo_paths:
        src = Path(p)
        if src.exists():
            dst = dest_dir / src.name
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied


def list_photos(deal_dir: Path) -> list[Path]:
    """Return all photo files in the deal's inputs/photos folder."""
    photo_dir = deal_dir / "inputs" / "photos"
    if not photo_dir.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
    return sorted(f for f in photo_dir.iterdir() if f.suffix.lower() in exts)


def save_output(deal_dir: Path, filename: str, data: Any) -> Path:
    """Save an output artifact (JSON or text)."""
    out = deal_dir / "outputs" / filename
    if filename.endswith(".json"):
        out.write_text(json.dumps(data, indent=2, default=str))
    else:
        out.write_text(str(data))
    return out


def save_log(deal_dir: Path, label: str, content: str) -> Path:
    """Append a log entry to the deal's logs folder."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = deal_dir / "logs" / f"{ts}_{label}.txt"
    log_file.write_text(content)
    return log_file


def list_deals() -> list[Path]:
    """Return all deal directories, newest first."""
    if not DEALS_DIR.exists():
        return []
    return sorted(
        [d for d in DEALS_DIR.iterdir() if d.is_dir() and (d / "deal.json").exists()],
        reverse=True,
    )
