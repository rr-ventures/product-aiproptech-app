#!/usr/bin/env python3
"""Entry point — AU Property Ops Copilot.

Usage:
  python run.py          → Start the web UI (default, opens on http://localhost:8000)
  python run.py --cli    → Start the CLI wizard instead
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    if "--cli" in sys.argv:
        from app.main import main as cli_main
        cli_main()
    else:
        import uvicorn
        print()
        print("  ┌─────────────────────────────────────────┐")
        print("  │  AU Property Ops Copilot                │")
        print("  │  Open → http://localhost:8000            │")
        print("  │  Press Ctrl+C to stop                   │")
        print("  └─────────────────────────────────────────┘")
        print()
        uvicorn.run("app.web.server:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
