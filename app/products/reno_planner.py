"""Product 4 — Reno Execution Planner: room interview → products → tradies → timeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from app.config import PROMPTS_DIR, TEMPLATES_DIR
from app.models import claude
from app.utils import deal as deal_mgr
from app.utils.spreadsheet import (
    CURRENCY_FORMAT,
    create_workbook,
    save_workbook,
    write_section_header,
    write_table,
)

console = Console()


def _load_stores() -> list[dict[str, Any]]:
    """Load preferred stores list."""
    path = TEMPLATES_DIR / "stores_list_placeholder.json"
    if path.exists():
        data = json.loads(path.read_text())
        return data.get("stores", [])
    return []


def _run_room_interview(deal_dir: Path) -> dict[str, Any]:
    """
    Conduct a Claude-guided room-by-room interview.
    Returns the full reno plan JSON from Claude.
    """
    system_prompt = (PROMPTS_DIR / "claude_reno_interview.md").read_text()
    stores = _load_stores()
    stores_context = f"\nAcceptable stores: {json.dumps(stores, indent=2)}" if stores else ""

    # Load vision data if available
    vision_file = deal_dir / "outputs" / "vision_extraction.json"
    vision_context = ""
    if vision_file.exists():
        vision_data = json.loads(vision_file.read_text())
        vision_context = f"\nProperty photo analysis: {json.dumps(vision_data, indent=2)}"

    messages: list[dict[str, str]] = []

    # Initial message to Claude
    meta = deal_mgr.load_deal(deal_dir)
    init_msg = (
        f"I'm planning a renovation for {meta.get('address', 'a property')}. "
        f"Please guide me through a room-by-room interview to define the scope."
        f"{vision_context}{stores_context}"
    )
    messages.append({"role": "user", "content": init_msg})

    console.print("\n[bold]Room-by-Room Interview[/bold]")
    console.print("[dim]Claude will guide you through each room. Type 'done' when all rooms are covered.[/dim]\n")

    # Interactive conversation loop
    while True:
        try:
            response = claude.chat(system_prompt, messages)
        except Exception as e:
            console.print(f"[red]Claude error: {e}[/red]")
            break

        messages.append({"role": "assistant", "content": response})
        console.print(f"[blue]Claude:[/blue] {response}\n")

        user_input = Prompt.ask("[green]You[/green]")

        if user_input.lower() == "done":
            # Ask Claude to produce the final structured output
            messages.append({
                "role": "user",
                "content": (
                    "That covers all rooms. Please now generate the complete structured "
                    "renovation plan as JSON, following the output schema in your instructions."
                ),
            })
            try:
                final_response = claude.chat(system_prompt, messages)
                messages.append({"role": "assistant", "content": final_response})

                # Try to parse JSON from response
                cleaned = final_response
                if "```" in cleaned:
                    # Extract JSON from code fence
                    parts = cleaned.split("```")
                    for part in parts:
                        stripped = part.strip()
                        if stripped.startswith("json"):
                            stripped = stripped[4:].strip()
                        if stripped.startswith("{"):
                            cleaned = stripped
                            break

                reno_plan = json.loads(cleaned)
                return reno_plan

            except (json.JSONDecodeError, Exception) as e:
                console.print(f"[yellow]⚠ Could not parse plan as JSON: {e}[/yellow]")
                # Save raw response
                deal_mgr.save_output(deal_dir, "reno_interview_raw.md", final_response)
                return {"raw_plan": final_response, "parse_error": True}

        messages.append({"role": "user", "content": user_input})

    return {}


def run_reno_planner(deal_dir: Path | None = None) -> dict[str, Any]:
    """Run the Reno Planner workflow."""
    console.print(Panel(
        "[bold]Product 4 — Reno Execution Planner[/bold]\n"
        "Room Interview → Products → Tradies → Timeline",
        border_style="blue",
    ))

    # ── Step 0: Deal setup ───────────────────────────────────────────
    if deal_dir is None:
        deals = deal_mgr.list_deals()
        if deals:
            console.print("\n[bold]Existing deals:[/bold]")
            for i, d in enumerate(deals, 1):
                m = deal_mgr.load_deal(d)
                console.print(f"  [{i}] {m.get('address', d.name)}")
            choice = Prompt.ask("Select deal number (or 'new')", default="1")
            if choice.lower() != "new":
                idx = int(choice) - 1
                if 0 <= idx < len(deals):
                    deal_dir = deals[idx]

        if deal_dir is None:
            address = Prompt.ask("Property address")
            deal_dir = deal_mgr.create_deal(address)

    meta = deal_mgr.load_deal(deal_dir)
    console.print(f"[green]✓ Deal:[/green] {meta.get('address', '')}")

    # ── Check stores list ────────────────────────────────────────────
    stores = _load_stores()
    if any("TBA" in s.get("name", "") for s in stores):
        console.print(
            "[yellow]⚠ Stores list has placeholders. "
            "Edit templates/stores_list_placeholder.json to add your preferred suppliers.[/yellow]"
        )

    # ── Step 1: Room interview ───────────────────────────────────────
    console.print("\n[bold]Step 1: Room-by-Room Interview[/bold]")
    reno_plan = _run_room_interview(deal_dir)

    if not reno_plan:
        console.print("[red]No reno plan generated.[/red]")
        return {}

    deal_mgr.save_output(deal_dir, "reno_plan.json", reno_plan)
    console.print("[green]✓ Reno plan saved[/green]")

    # ── Step 2: Generate all artifacts ───────────────────────────────
    console.print("\n[bold]Step 2: Generating Artifacts[/bold]")

    # Product list spreadsheet
    product_path = _generate_product_spreadsheet(deal_dir, reno_plan)
    console.print(f"[green]✓ Product list:[/green] {product_path}")

    # Trade scope documents
    trade_docs_dir = deal_dir / "outputs" / "trade_scopes"
    trade_docs_dir.mkdir(exist_ok=True)
    trade_packages = reno_plan.get("trade_packages", [])
    for tp in trade_packages:
        trade_name = tp.get("trade", "unknown").replace(" ", "_").lower()
        scope_doc = tp.get("scope_document", "")
        (trade_docs_dir / f"{trade_name}_scope.md").write_text(scope_doc)

        email_template = tp.get("quote_email_template", "")
        if email_template:
            (trade_docs_dir / f"{trade_name}_quote_email.md").write_text(email_template)

    console.print(f"[green]✓ {len(trade_packages)} trade scope docs generated[/green]")

    # Quote tracker spreadsheet
    quote_path = _generate_quote_tracker(deal_dir, reno_plan)
    console.print(f"[green]✓ Quote tracker:[/green] {quote_path}")

    # Timeline spreadsheet
    timeline_path = _generate_timeline(deal_dir, reno_plan)
    console.print(f"[green]✓ Timeline:[/green] {timeline_path}")

    # ── Step 3: Human sign-off ───────────────────────────────────────
    console.print()
    signed_off = Confirm.ask(
        "[bold yellow]⚠ HUMAN SIGN-OFF:[/bold yellow] Review all reno outputs. Approve?",
        default=False,
    )
    meta["reno_status"] = "approved" if signed_off else "draft"
    meta["reno_completed_at"] = datetime.now().isoformat()
    deal_mgr.save_deal_meta(deal_dir, meta)

    console.print(f"\nReno Plan Status: {'[green]APPROVED[/green]' if signed_off else '[yellow]DRAFT[/yellow]'}")
    console.print(f"Deal folder: [cyan]{deal_dir}[/cyan]")

    return reno_plan


def _generate_product_spreadsheet(deal_dir: Path, plan: dict[str, Any]) -> Path:
    wb = create_workbook()
    ws = wb.active
    ws.title = "Product List"

    row = 1
    row = write_section_header(ws, row, "PRODUCT PROCUREMENT PLAN", 9)

    headers = [
        "Category", "Item", "Room", "Budget Low", "Budget High",
        "Preferred Store", "When to Order", "Alternatives", "Notes",
    ]
    products = plan.get("product_list", [])
    rows = [
        [
            p.get("category", ""),
            p.get("item_description", ""),
            p.get("room", ""),
            p.get("budget_estimate_low", ""),
            p.get("budget_estimate_high", ""),
            ", ".join(p.get("preferred_stores", [])),
            p.get("when_to_order", ""),
            p.get("alternatives", ""),
            p.get("notes", ""),
        ]
        for p in products
    ]

    write_table(
        ws, headers, rows, start_row=row,
        col_widths=[15, 35, 12, 12, 12, 20, 18, 25, 25],
        number_formats={3: CURRENCY_FORMAT, 4: CURRENCY_FORMAT},
    )

    # Budget summary
    budget = plan.get("total_budget_estimate", {})
    if budget:
        row = len(rows) + row + 3
        row = write_section_header(ws, row, "BUDGET SUMMARY", 4)
        from app.utils.spreadsheet import write_kv_pairs
        write_kv_pairs(ws, [
            ("Budget Low", budget.get("low", "")),
            ("Budget High", budget.get("high", "")),
            ("Notes", budget.get("notes", "")),
        ], start_row=row, val_format=CURRENCY_FORMAT)

    path = deal_dir / "outputs" / "product_list.xlsx"
    return save_workbook(wb, path)


def _generate_quote_tracker(deal_dir: Path, plan: dict[str, Any]) -> Path:
    wb = create_workbook()
    ws = wb.active
    ws.title = "Quote Tracker"

    row = 1
    row = write_section_header(ws, row, "TRADIE QUOTE TRACKER", 10)

    headers = [
        "Trade", "Company", "Contact", "Phone", "Email",
        "Quote Amount", "Quote Date", "Available Start", "Status", "Notes",
    ]
    # Pre-populate trades from plan
    trades = plan.get("scope_by_trade", [])
    rows = [
        [t.get("trade", ""), "", "", "", "", "", "", "", "Not quoted", ""]
        for t in trades
    ]

    write_table(
        ws, headers, rows, start_row=row,
        col_widths=[15, 20, 18, 14, 25, 14, 12, 14, 12, 25],
        number_formats={5: CURRENCY_FORMAT},
    )

    path = deal_dir / "outputs" / "quote_tracker.xlsx"
    return save_workbook(wb, path)


def _generate_timeline(deal_dir: Path, plan: dict[str, Any]) -> Path:
    wb = create_workbook()
    ws = wb.active
    ws.title = "Timeline"

    row = 1
    row = write_section_header(ws, row, "RENOVATION TIMELINE", 7)

    headers = ["Phase", "Name", "Trades", "Duration (days)", "Dependencies", "Start Date", "Notes"]
    phases = plan.get("timeline", [])
    rows = [
        [
            p.get("phase", ""),
            p.get("name", ""),
            ", ".join(p.get("trades", [])),
            p.get("duration_days", ""),
            ", ".join(p.get("dependencies", [])),
            "",  # Start date placeholder
            p.get("notes", ""),
        ]
        for p in phases
    ]

    write_table(
        ws, headers, rows, start_row=row,
        col_widths=[8, 25, 20, 14, 20, 14, 30],
    )

    path = deal_dir / "outputs" / "timeline.xlsx"
    return save_workbook(wb, path)
