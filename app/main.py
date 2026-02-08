"""AU Property Ops Copilot — CLI Wizard Entry Point."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from app.utils import deal as deal_mgr

console = Console()

BANNER = """
[bold blue]╔══════════════════════════════════════════════╗
║   AU Property Ops Copilot                    ║
║   Local-Only • Multi-Model • Human Sign-Off  ║
╚══════════════════════════════════════════════╝[/bold blue]
"""


def show_menu() -> str:
    console.print(BANNER)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", width=4)
    table.add_column()
    table.add_column(style="dim")

    table.add_row("1", "CMA Engine", "Comparative Market Analysis (~5 min)")
    table.add_row("2", "Due Diligence Copilot", "Manus-led DD checklist")
    table.add_row("3", "Feasibility Engine", "Purchase viability + reno economics")
    table.add_row("4", "Reno Planner", "Room interview → products → tradies → timeline")
    table.add_row("", "", "")
    table.add_row("D", "Deal Manager", "List / select / view deals")
    table.add_row("Q", "Quit", "")

    console.print(table)
    return Prompt.ask("\nSelect", choices=["1", "2", "3", "4", "d", "D", "q", "Q"], default="1")


def deal_manager_menu() -> Path | None:
    """Browse and select existing deals."""
    deals = deal_mgr.list_deals()
    if not deals:
        console.print("[yellow]No deals found. Create one by running a product workflow.[/yellow]")
        return None

    console.print("\n[bold]Existing Deals[/bold]")
    table = Table()
    table.add_column("#", justify="right", width=4)
    table.add_column("Address", style="cyan")
    table.add_column("Created")
    table.add_column("CMA", justify="center")
    table.add_column("DD", justify="center")
    table.add_column("Feasibility", justify="center")
    table.add_column("Reno", justify="center")

    for i, d in enumerate(deals, 1):
        meta = deal_mgr.load_deal(d)
        table.add_row(
            str(i),
            meta.get("address", d.name),
            meta.get("created_at", "")[:10],
            _status_icon(meta.get("cma_status")),
            _status_icon(meta.get("dd_status")),
            _status_icon(meta.get("feasibility_status")),
            _status_icon(meta.get("reno_status")),
        )

    console.print(table)
    choice = Prompt.ask("Select deal number (or 'back')", default="back")
    if choice.lower() == "back":
        return None

    idx = int(choice) - 1
    if 0 <= idx < len(deals):
        return deals[idx]
    return None


def _status_icon(status: str | None) -> str:
    if status is None:
        return "—"
    return {"approved": "[green]✓[/green]", "draft": "[yellow]◐[/yellow]"}.get(status, "—")


def main():
    """Main CLI loop."""
    selected_deal: Path | None = None

    while True:
        choice = show_menu()

        if choice.lower() == "q":
            console.print("[dim]Goodbye![/dim]")
            sys.exit(0)

        if choice.lower() == "d":
            selected_deal = deal_manager_menu()
            if selected_deal:
                meta = deal_mgr.load_deal(selected_deal)
                console.print(f"\n[green]Selected:[/green] {meta.get('address', '')}")
                console.print(f"[dim]{selected_deal}[/dim]")

                # Offer to run a product on this deal
                action = Prompt.ask(
                    "Run which product on this deal?",
                    choices=["1", "2", "3", "4", "back"],
                    default="back",
                )
                if action == "back":
                    continue
                choice = action  # Fall through to product dispatch
            else:
                continue

        # Product dispatch
        try:
            if choice == "1":
                from app.products.cma import run_cma
                run_cma(selected_deal)

            elif choice == "2":
                from app.products.due_diligence import run_due_diligence
                run_due_diligence(selected_deal)

            elif choice == "3":
                from app.products.feasibility import run_feasibility
                run_feasibility(selected_deal)

            elif choice == "4":
                from app.products.reno_planner import run_reno_planner
                run_reno_planner(selected_deal)

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
        except SystemExit as e:
            console.print(f"\n[red]{e}[/red]")
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            console.print_exception()

        selected_deal = None  # Reset after running a product
        console.print("\n" + "─" * 50 + "\n")

        if not Confirm.ask("Return to main menu?", default=True):
            console.print("[dim]Goodbye![/dim]")
            break


if __name__ == "__main__":
    main()
