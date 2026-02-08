"""Product 2 — Due Diligence Copilot (Manus-led): runnable stub."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from app.config import PROMPTS_DIR, TEMPLATES_DIR
from app.models import manus
from app.utils import deal as deal_mgr
from app.utils.spreadsheet import (
    create_workbook,
    save_workbook,
    write_section_header,
    write_table,
)

console = Console()


def _load_checklist() -> list[dict[str, Any]]:
    """Load the DD checklist from the template file."""
    path = TEMPLATES_DIR / "dd_checklist_placeholder.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("checklist", [])


def run_due_diligence(deal_dir: Path | None = None) -> dict[str, Any]:
    """Run the Due Diligence workflow (stub — produces artifact formats)."""
    console.print(Panel(
        "[bold]Product 2 — Due Diligence Copilot[/bold]\n"
        "Manus-led DD with human sign-off",
        border_style="blue",
    ))

    # ── Step 0: Deal setup ───────────────────────────────────────────
    if deal_dir is None:
        address = Prompt.ask("Property address")
        listing_url = Prompt.ask("Listing URL", default="")
        deal_dir = deal_mgr.create_deal(address, listing_url)
    meta = deal_mgr.load_deal(deal_dir)
    console.print(f"[green]✓ Deal:[/green] {meta.get('address', '')}")

    # ── Step 1: Load checklist ───────────────────────────────────────
    checklist = _load_checklist()
    if not checklist or checklist[0].get("name", "").startswith("Confirm zoning"):
        console.print(
            "[yellow]⚠ Using PLACEHOLDER checklist (10 items). "
            "Replace templates/dd_checklist_placeholder.json with your full 100-step checklist.[/yellow]"
        )
    console.print(f"[green]✓ {len(checklist)} checklist items loaded[/green]")

    # ── Step 2: Generate Manus job prompt ────────────────────────────
    console.print("\n[bold]Step 2: Generating Manus Job Prompt[/bold]")
    prompt_template = (PROMPTS_DIR / "manus_dd_job.md").read_text()

    # Fill template placeholders
    job_prompt = prompt_template.replace("{address}", meta.get("address", ""))
    job_prompt = job_prompt.replace("{listing_url}", meta.get("listing_url", ""))
    job_prompt = job_prompt.replace("{state}", Prompt.ask("State", default="NSW"))
    job_prompt = job_prompt.replace("{council}", Prompt.ask("Council/LGA", default="TBD"))

    checklist_text = "\n".join(
        f"{item['item_number']}. [{item.get('category', '')}] {item['name']} "
        f"— Source: {item.get('source', 'TBD')} — Risk: {item.get('risk_if_fail', 'medium')}"
        for item in checklist
    )
    job_prompt = job_prompt.replace("{checklist_items}", checklist_text)

    # Save the prompt
    prompt_path = deal_mgr.save_output(deal_dir, "dd_manus_prompt.md", job_prompt)
    console.print(f"[green]✓ Manus prompt saved:[/green] {prompt_path}")

    # ── Step 3: Dispatch or manual ───────────────────────────────────
    if manus.is_configured():
        console.print("[dim]Manus API detected. Dispatching job...[/dim]")
        # Note: actual async dispatch would need event loop
        console.print("[yellow]⚠ Manus API dispatch is a future feature. Use the prompt manually for now.[/yellow]")
    else:
        console.print(
            "\n[yellow]Manus API not configured.[/yellow]\n"
            "To run DD:\n"
            "  1. Open the generated prompt file\n"
            "  2. Paste it into the Manus web UI\n"
            "  3. Download the results\n"
            "  4. Place results in the deal's inputs/ folder\n"
            "  5. Re-run this workflow to compile the report\n"
        )

    # ── Step 4: Check for existing results to compile ────────────────
    results_file = deal_dir / "inputs" / "dd_results.json"
    dd_results: list[dict[str, Any]] = []

    if results_file.exists():
        dd_results = json.loads(results_file.read_text())
        console.print(f"[green]✓ Found DD results: {len(dd_results)} items[/green]")
    else:
        console.print("[dim]No DD results file found yet. Generating placeholder outputs...[/dim]")
        # Generate placeholder results for artifact format demonstration
        dd_results = [
            {
                "item_number": item["item_number"],
                "item_name": item["name"],
                "category": item.get("category", ""),
                "status": "PENDING",
                "finding_summary": "Awaiting Manus results or manual entry",
                "source_url": "",
                "screenshot_filename": "",
                "risk_level": item.get("risk_if_fail", "medium"),
                "notes": "",
            }
            for item in checklist
        ]

    deal_mgr.save_output(deal_dir, "dd_results.json", dd_results)

    # ── Step 5: Generate spreadsheet ─────────────────────────────────
    console.print("\n[bold]Step 5: Generating DD Spreadsheet[/bold]")
    xlsx_path = _generate_dd_spreadsheet(deal_dir, meta, dd_results)
    console.print(f"[green]✓ DD spreadsheet saved:[/green] {xlsx_path}")

    # ── Step 6: Generate markdown report ─────────────────────────────
    md_path = _generate_dd_markdown(deal_dir, meta, dd_results)
    console.print(f"[green]✓ DD markdown saved:[/green] {md_path}")

    # ── Step 7: Human sign-off ───────────────────────────────────────
    console.print()
    signed_off = Confirm.ask(
        "[bold yellow]⚠ HUMAN SIGN-OFF:[/bold yellow] Review the DD report. Approve?",
        default=False,
    )
    meta["dd_status"] = "approved" if signed_off else "draft"
    meta["dd_completed_at"] = datetime.now().isoformat()
    deal_mgr.save_deal_meta(deal_dir, meta)

    console.print(f"\nDD Status: {'[green]APPROVED[/green]' if signed_off else '[yellow]DRAFT[/yellow]'}")
    console.print(f"Deal folder: [cyan]{deal_dir}[/cyan]")

    return {"results": dd_results}


def _generate_dd_spreadsheet(
    deal_dir: Path, meta: dict[str, Any], results: list[dict[str, Any]]
) -> Path:
    wb = create_workbook()

    # Sheet 1: Checklist Results
    ws1 = wb.active
    ws1.title = "DD Checklist"
    row = 1
    row = write_section_header(ws1, row, f"DD Report — {meta.get('address', '')}", 8)

    headers = ["#", "Category", "Item", "Status", "Finding", "Risk", "Source URL", "Notes"]
    rows = [
        [
            r.get("item_number", ""),
            r.get("category", ""),
            r.get("item_name", ""),
            r.get("status", "PENDING"),
            r.get("finding_summary", ""),
            r.get("risk_level", ""),
            r.get("source_url", ""),
            r.get("notes", ""),
        ]
        for r in results
    ]
    write_table(ws1, headers, rows, start_row=row, col_widths=[5, 18, 30, 12, 40, 10, 30, 30])

    # Sheet 2: Evidence Index
    ws2 = wb.create_sheet("Evidence Index")
    row = 1
    row = write_section_header(ws2, row, "Evidence Index", 5)
    ev_headers = ["Item #", "Item", "Screenshot", "Source URL", "Summary"]
    ev_rows = [
        [
            r.get("item_number", ""),
            r.get("item_name", ""),
            r.get("screenshot_filename", ""),
            r.get("source_url", ""),
            r.get("finding_summary", ""),
        ]
        for r in results
    ]
    write_table(ws2, ev_headers, ev_rows, start_row=row, col_widths=[8, 30, 25, 35, 40])

    xlsx_path = deal_dir / "outputs" / "dd_report.xlsx"
    return save_workbook(wb, xlsx_path)


def _generate_dd_markdown(
    deal_dir: Path, meta: dict[str, Any], results: list[dict[str, Any]]
) -> Path:
    lines = [
        f"# Due Diligence Report — {meta.get('address', '')}",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]

    # Group by category
    categories: dict[str, list] = {}
    for r in results:
        cat = r.get("category", "Other")
        categories.setdefault(cat, []).append(r)

    for cat, items in categories.items():
        lines.append(f"## {cat}")
        lines.append("")
        for item in items:
            status = item.get("status", "PENDING")
            icon = {"PASS": "✅", "FAIL": "❌", "UNKNOWN": "❓", "PENDING": "⏳"}.get(status, "⚠️")
            lines.append(f"### {icon} {item.get('item_name', '')}")
            lines.append(f"- **Status**: {status}")
            lines.append(f"- **Risk**: {item.get('risk_level', '')}")
            if item.get("finding_summary"):
                lines.append(f"- **Finding**: {item['finding_summary']}")
            if item.get("source_url"):
                lines.append(f"- **Source**: {item['source_url']}")
            lines.append("")

    lines.extend(["---", f"_Status: {meta.get('dd_status', 'draft')}_"])

    md_path = deal_dir / "outputs" / "dd_report.md"
    md_path.write_text("\n".join(lines))
    return md_path
