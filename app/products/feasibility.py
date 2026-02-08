"""Product 3 — Feasibility Engine: purchase viability + reno economics."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from app.config import PROMPTS_DIR, TEMPLATES_DIR
from app.models import claude
from app.utils import deal as deal_mgr
from app.utils.spreadsheet import (
    CURRENCY_FORMAT,
    PERCENT_FORMAT,
    create_workbook,
    save_workbook,
    write_kv_pairs,
    write_section_header,
    write_table,
)

console = Console()


def _load_feasibility_defaults() -> dict[str, Any]:
    """Load default feasibility assumptions from template."""
    template_path = TEMPLATES_DIR / "feasibility_template.json"
    if template_path.exists():
        return json.loads(template_path.read_text())
    return {}


def _collect_deal_assumptions(defaults: dict[str, Any], cma_data: dict[str, Any]) -> dict[str, Any]:
    """Interactively collect deal-specific assumptions."""
    val = cma_data.get("valuation", {})

    console.print("\n[bold]Deal-Specific Inputs[/bold]")
    console.print(f"[dim]CMA value range: ${val.get('value_range_low', 0):,.0f} – ${val.get('value_range_high', 0):,.0f}[/dim]")

    asking_price = Prompt.ask("Asking price / guide ($)", default="0")
    purchase_price = Prompt.ask("Your intended purchase price ($)", default=asking_price)
    reno_budget = Prompt.ask("Renovation budget ($)", default="0")
    post_reno_value = Prompt.ask(
        "Estimated post-reno sale price ($, or 'cma' to use CMA high)",
        default="cma",
    )
    hold_months = Prompt.ask(
        "Expected hold period (months)",
        default=str(defaults.get("deal_parameters", {}).get("default_hold_period_months", 6)),
    )
    state = Prompt.ask("State (for stamp duty)", default="NSW")

    if post_reno_value.lower() == "cma":
        post_reno_value = str(val.get("value_range_high", 0))

    return {
        "asking_price": int(asking_price.replace(",", "").replace("$", "")),
        "purchase_price": int(purchase_price.replace(",", "").replace("$", "")),
        "reno_budget": int(reno_budget.replace(",", "").replace("$", "")),
        "post_reno_sale_price": int(post_reno_value.replace(",", "").replace("$", "")),
        "hold_period_months": int(hold_months),
        "state": state,
    }


def _compute_feasibility(
    deal_inputs: dict[str, Any],
    defaults: dict[str, Any],
    cma_data: dict[str, Any],
) -> dict[str, Any]:
    """Compute the feasibility model locally (before sending to Claude for commentary)."""
    acq = defaults.get("acquisition_costs", {})
    hold = defaults.get("holding_costs_monthly", {})
    sell = defaults.get("selling_costs", {})
    reno_cfg = defaults.get("renovation", {})
    targets = defaults.get("deal_parameters", {})

    purchase = deal_inputs["purchase_price"]
    reno = deal_inputs["reno_budget"]
    sale = deal_inputs["post_reno_sale_price"]
    months = deal_inputs["hold_period_months"]

    # Acquisition costs
    stamp_duty = int(purchase * acq.get("stamp_duty_rate_pct", 4.5) / 100)
    legal_buy = acq.get("legal_conveyancing", 2500)
    bpi = acq.get("building_pest_inspection", 800)
    total_acquisition = purchase + stamp_duty + legal_buy + bpi + acq.get("other_acquisition", 0)

    # Renovation
    contingency_pct = reno_cfg.get("contingency_pct", 15) / 100
    contingency_amt = int(reno * contingency_pct)
    total_reno = reno + contingency_amt

    # Holding costs
    loan_amount = purchase * hold.get("finance_lvr_pct", 80) / 100
    monthly_interest = loan_amount * (hold.get("finance_interest_rate_annual_pct", 6.5) / 100) / 12
    monthly_holding = (
        monthly_interest
        + hold.get("council_rates", 350)
        + hold.get("water_rates", 150)
        + hold.get("insurance", 250)
        + hold.get("land_tax_monthly", 0)
        + hold.get("utilities", 100)
        + hold.get("other_holding", 0)
    )
    total_holding = int(monthly_holding * months)

    # Selling costs
    commission_pct = sell.get("agent_commission_pct", 2.0) / 100
    commission_amt = int(sale * commission_pct)
    marketing = sell.get("marketing", 5000)
    legal_sell = sell.get("legal_selling", 1500)
    styling = sell.get("styling", 3000)
    total_selling = commission_amt + marketing + legal_sell + styling + sell.get("other_selling", 0)

    # Profitability
    total_cost = total_acquisition + total_reno + total_holding + total_selling
    gross_profit = sale - purchase
    net_profit = sale - total_cost
    roi = net_profit / (total_cost - sale + net_profit) if (total_cost - sale + net_profit) != 0 else 0
    # ROI = net profit / total capital invested (everything except sale)
    total_invested = total_acquisition + total_reno + total_holding
    roi = net_profit / total_invested if total_invested else 0
    margin = net_profit / sale if sale else 0
    profit_per_month = net_profit / months if months else 0
    annualised_roi = roi * (12 / months) if months else 0

    # Max purchase price to hit target
    target_profit = targets.get("target_profit_min", 50000)
    # Max purchase = sale - selling_costs - reno - holding - stamp_duty_etc - target_profit
    # Simplified: solve for purchase where net_profit = target_profit
    # total_cost = purchase + stamp%(purchase) + legal + bpi + reno + cont + holding + selling
    # net = sale - total_cost = target → purchase = (sale - selling - reno - cont - holding - legal - bpi - target) / (1 + stamp%)
    stamp_rate = acq.get("stamp_duty_rate_pct", 4.5) / 100
    max_purchase = int(
        (sale - total_selling - total_reno - total_holding - legal_buy - bpi - target_profit)
        / (1 + stamp_rate)
    )

    return {
        "purchase_analysis": {
            "asking_price": deal_inputs["asking_price"],
            "purchase_price": purchase,
            "cma_value_low": cma_data.get("valuation", {}).get("value_range_low"),
            "cma_value_high": cma_data.get("valuation", {}).get("value_range_high"),
            "stamp_duty": stamp_duty,
            "legal_conveyancing": legal_buy,
            "building_pest_inspection": bpi,
            "total_acquisition_cost": total_acquisition,
        },
        "renovation": {
            "reno_budget": reno,
            "contingency_pct": reno_cfg.get("contingency_pct", 15),
            "contingency_amount": contingency_amt,
            "total_reno_cost": total_reno,
        },
        "holding_costs": {
            "hold_period_months": months,
            "loan_amount": int(loan_amount),
            "finance_cost_monthly": int(monthly_interest),
            "council_rates_monthly": hold.get("council_rates", 350),
            "water_rates_monthly": hold.get("water_rates", 150),
            "insurance_monthly": hold.get("insurance", 250),
            "land_tax_monthly": hold.get("land_tax_monthly", 0),
            "utilities_monthly": hold.get("utilities", 100),
            "total_monthly": int(monthly_holding),
            "total_holding_cost": total_holding,
        },
        "selling": {
            "estimated_sale_price": sale,
            "agent_commission_pct": sell.get("agent_commission_pct", 2.0),
            "agent_commission_amount": commission_amt,
            "marketing_cost": marketing,
            "legal_selling": legal_sell,
            "styling": styling,
            "total_selling_cost": total_selling,
        },
        "profitability": {
            "total_cost_in": total_cost,
            "total_invested": total_invested,
            "estimated_sale_price": sale,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "roi_pct": round(roi * 100, 1),
            "margin_pct": round(margin * 100, 1),
            "profit_per_month": int(profit_per_month),
            "annualised_roi_pct": round(annualised_roi * 100, 1),
        },
        "max_purchase_price": {
            "target_profit": target_profit,
            "target_roi_pct": targets.get("target_roi_min_pct", 15),
            "max_purchase_to_hit_target": max_purchase,
        },
    }


def _display_feasibility(feas: dict[str, Any], commentary: dict | str = "") -> None:
    """Pretty-print feasibility results."""
    prof = feas.get("profitability", {})
    color = "green" if prof.get("net_profit", 0) > 0 else "red"

    console.print()
    console.print(Panel(
        f"[bold {color}]Net Profit:[/bold {color}]  ${prof.get('net_profit', 0):,.0f}\n"
        f"[bold]ROI:[/bold]  {prof.get('roi_pct', 0):.1f}%\n"
        f"[bold]Margin:[/bold]  {prof.get('margin_pct', 0):.1f}%\n"
        f"[bold]Annualised ROI:[/bold]  {prof.get('annualised_roi_pct', 0):.1f}%\n"
        f"[bold]Profit/Month:[/bold]  ${prof.get('profit_per_month', 0):,.0f}\n"
        f"\n[bold]Max Purchase (for target profit):[/bold]  "
        f"${feas.get('max_purchase_price', {}).get('max_purchase_to_hit_target', 0):,.0f}",
        title="💰 Feasibility Result",
        border_style=color,
    ))

    # Cost breakdown table
    table = Table(title="Cost Breakdown")
    table.add_column("Category", style="cyan")
    table.add_column("Amount", justify="right")

    table.add_row("Purchase Price", f"${feas['purchase_analysis']['purchase_price']:,.0f}")
    table.add_row("Stamp Duty", f"${feas['purchase_analysis']['stamp_duty']:,.0f}")
    table.add_row("Legal + B&P", f"${feas['purchase_analysis']['legal_conveyancing'] + feas['purchase_analysis']['building_pest_inspection']:,.0f}")
    table.add_row("Reno (incl contingency)", f"${feas['renovation']['total_reno_cost']:,.0f}")
    table.add_row("Holding Costs", f"${feas['holding_costs']['total_holding_cost']:,.0f}")
    table.add_row("Selling Costs", f"${feas['selling']['total_selling_cost']:,.0f}")
    table.add_row("─" * 20, "─" * 12)
    table.add_row("[bold]Total Cost In[/bold]", f"[bold]${feas['profitability']['total_cost_in']:,.0f}[/bold]")
    table.add_row("[bold]Sale Price[/bold]", f"[bold]${feas['selling']['estimated_sale_price']:,.0f}[/bold]")
    table.add_row(f"[bold {color}]Net Profit[/bold {color}]", f"[bold {color}]${prof['net_profit']:,.0f}[/bold {color}]")

    console.print(table)

    if isinstance(commentary, dict):
        go = commentary.get("go_no_go", "")
        if go:
            go_color = {"GO": "green", "MARGINAL": "yellow", "NO-GO": "red"}.get(go, "white")
            console.print(f"\n[bold {go_color}]Verdict: {go}[/bold {go_color}]")
        reasoning = commentary.get("reasoning", "")
        if reasoning:
            console.print(f"\n{reasoning}")


# ── main feasibility workflow ────────────────────────────────────────────


def run_feasibility(deal_dir: Path | None = None) -> dict[str, Any]:
    """Run the full feasibility workflow."""
    console.print(Panel("[bold]Product 3 — Feasibility Engine[/bold]\nPurchase Viability + Reno Economics", border_style="blue"))

    # ── Step 0: Select deal ──────────────────────────────────────────
    if deal_dir is None:
        deals = deal_mgr.list_deals()
        if deals:
            console.print("\n[bold]Existing deals with CMA data:[/bold]")
            cma_deals = []
            for d in deals:
                cma_file = d / "outputs" / "cma_result.json"
                if cma_file.exists():
                    m = deal_mgr.load_deal(d)
                    cma_deals.append(d)
                    console.print(f"  [{len(cma_deals)}] {m.get('address', d.name)}")

            if cma_deals:
                choice = Prompt.ask("Select deal number (or 'new')", default="1")
                if choice.lower() != "new":
                    idx = int(choice) - 1
                    if 0 <= idx < len(cma_deals):
                        deal_dir = cma_deals[idx]

        if deal_dir is None:
            console.print("[yellow]No deal with CMA data found. Run CMA first (Product 1).[/yellow]")
            address = Prompt.ask("Or enter address for standalone feasibility")
            deal_dir = deal_mgr.create_deal(address)

    meta = deal_mgr.load_deal(deal_dir)
    console.print(f"[green]✓ Using deal:[/green] {meta.get('address', deal_dir.name)}")

    # ── Step 1: Load CMA data ────────────────────────────────────────
    cma_file = deal_dir / "outputs" / "cma_result.json"
    cma_data: dict[str, Any] = {}
    if cma_file.exists():
        cma_data = json.loads(cma_file.read_text())
        val = cma_data.get("valuation", {})
        console.print(
            f"[green]✓ CMA loaded:[/green] "
            f"${val.get('value_range_low', 0):,.0f} – ${val.get('value_range_high', 0):,.0f}"
        )
    else:
        console.print("[yellow]No CMA data found. You'll need to enter values manually.[/yellow]")

    # ── Step 2: Collect assumptions ──────────────────────────────────
    console.print("\n[bold]Step 2: Deal Assumptions[/bold]")
    defaults = _load_feasibility_defaults()
    deal_inputs = _collect_deal_assumptions(defaults, cma_data)
    deal_mgr.save_output(deal_dir, "feasibility_inputs.json", deal_inputs)

    # ── Step 3: Compute feasibility ──────────────────────────────────
    console.print("\n[bold]Step 3: Computing Feasibility[/bold]")
    feas = _compute_feasibility(deal_inputs, defaults, cma_data)
    deal_mgr.save_output(deal_dir, "feasibility_calcs.json", feas)

    # ── Step 4: Claude commentary + sensitivity ──────────────────────
    console.print("\n[bold]Step 4: Claude Analysis & Sensitivity[/bold]")
    console.print("[dim]Sending to Claude for commentary...[/dim]")

    system_prompt = (PROMPTS_DIR / "claude_feasibility_reasoning.md").read_text()
    user_msg = json.dumps({
        "feasibility_model": feas,
        "cma_data": cma_data,
        "deal_inputs": deal_inputs,
        "template_defaults": defaults,
    }, indent=2, default=str)

    try:
        commentary = claude.reason(system_prompt, user_msg, expect_json=True)
        deal_mgr.save_output(deal_dir, "feasibility_commentary.json", commentary)
    except Exception as e:
        console.print(f"[yellow]⚠ Claude commentary failed: {e}[/yellow]")
        commentary = {}

    # Merge Claude's sensitivity/deal-breaker analysis if available
    if isinstance(commentary, dict):
        feas["sensitivity"] = commentary.get("sensitivity", [])
        feas["deal_breakers"] = commentary.get("deal_breakers", [])
        feas["go_no_go"] = commentary.get("go_no_go", "")
        feas["reasoning"] = commentary.get("reasoning", "")

    deal_mgr.save_output(deal_dir, "feasibility_result.json", feas)

    # ── Step 5: Display results ──────────────────────────────────────
    console.print("\n[bold]Step 5: Results[/bold]")
    _display_feasibility(feas, commentary)

    # ── Step 6: Spreadsheet ──────────────────────────────────────────
    console.print("\n[bold]Step 6: Generating Spreadsheet[/bold]")
    xlsx_path = _generate_feasibility_spreadsheet(deal_dir, meta, feas)
    console.print(f"[green]✓ Spreadsheet saved:[/green] {xlsx_path}")

    # ── Step 7: Markdown ─────────────────────────────────────────────
    md_path = _generate_feasibility_markdown(deal_dir, meta, feas)
    console.print(f"[green]✓ Markdown saved:[/green] {md_path}")

    # ── Step 8: Human sign-off ───────────────────────────────────────
    console.print()
    signed_off = Confirm.ask(
        "[bold yellow]⚠ HUMAN SIGN-OFF:[/bold yellow] Review the feasibility. Approve?",
        default=False,
    )
    meta["feasibility_status"] = "approved" if signed_off else "draft"
    meta["feasibility_completed_at"] = datetime.now().isoformat()
    deal_mgr.save_deal_meta(deal_dir, meta)

    status = "[green]APPROVED[/green]" if signed_off else "[yellow]DRAFT[/yellow]"
    console.print(f"\nFeasibility Status: {status}")
    console.print(f"Deal folder: [cyan]{deal_dir}[/cyan]")

    return feas


def _generate_feasibility_spreadsheet(
    deal_dir: Path, meta: dict[str, Any], feas: dict[str, Any]
) -> Path:
    wb = create_workbook()
    ws = wb.active
    ws.title = "Feasibility"
    row = 1

    # Purchase Analysis
    row = write_section_header(ws, row, "PURCHASE ANALYSIS", 4)
    pa = feas["purchase_analysis"]
    row = write_kv_pairs(ws, [
        ("Asking Price", pa["asking_price"]),
        ("Purchase Price", pa["purchase_price"]),
        ("CMA Value Low", pa.get("cma_value_low", "")),
        ("CMA Value High", pa.get("cma_value_high", "")),
        ("Stamp Duty", pa["stamp_duty"]),
        ("Legal / Conveyancing", pa["legal_conveyancing"]),
        ("Building & Pest", pa["building_pest_inspection"]),
        ("Total Acquisition Cost", pa["total_acquisition_cost"]),
    ], start_row=row, val_format=CURRENCY_FORMAT)
    row += 1

    # Renovation
    row = write_section_header(ws, row, "RENOVATION", 4)
    rn = feas["renovation"]
    row = write_kv_pairs(ws, [
        ("Reno Budget", rn["reno_budget"]),
        ("Contingency %", rn["contingency_pct"]),
        ("Contingency Amount", rn["contingency_amount"]),
        ("Total Reno Cost", rn["total_reno_cost"]),
    ], start_row=row, val_format=CURRENCY_FORMAT)
    row += 1

    # Holding Costs
    row = write_section_header(ws, row, "HOLDING COSTS", 4)
    hc = feas["holding_costs"]
    row = write_kv_pairs(ws, [
        ("Hold Period (months)", hc["hold_period_months"]),
        ("Loan Amount", hc["loan_amount"]),
        ("Finance Cost / month", hc["finance_cost_monthly"]),
        ("Council Rates / month", hc["council_rates_monthly"]),
        ("Water / month", hc["water_rates_monthly"]),
        ("Insurance / month", hc["insurance_monthly"]),
        ("Total Monthly", hc["total_monthly"]),
        ("Total Holding Cost", hc["total_holding_cost"]),
    ], start_row=row, val_format=CURRENCY_FORMAT)
    row += 1

    # Selling Costs
    row = write_section_header(ws, row, "SELLING COSTS", 4)
    sc = feas["selling"]
    row = write_kv_pairs(ws, [
        ("Sale Price", sc["estimated_sale_price"]),
        ("Commission %", sc["agent_commission_pct"]),
        ("Commission $", sc["agent_commission_amount"]),
        ("Marketing", sc["marketing_cost"]),
        ("Legal (selling)", sc["legal_selling"]),
        ("Styling", sc["styling"]),
        ("Total Selling Cost", sc["total_selling_cost"]),
    ], start_row=row, val_format=CURRENCY_FORMAT)
    row += 1

    # Profitability
    row = write_section_header(ws, row, "PROFITABILITY", 4)
    pr = feas["profitability"]
    row = write_kv_pairs(ws, [
        ("Total Cost In", pr["total_cost_in"]),
        ("Sale Price", pr["estimated_sale_price"]),
        ("Gross Profit", pr["gross_profit"]),
        ("Net Profit", pr["net_profit"]),
        ("ROI %", pr["roi_pct"]),
        ("Margin %", pr["margin_pct"]),
        ("Profit / Month", pr["profit_per_month"]),
        ("Annualised ROI %", pr["annualised_roi_pct"]),
    ], start_row=row, val_format=CURRENCY_FORMAT)
    row += 1

    # Max Purchase
    row = write_section_header(ws, row, "MAX PURCHASE PRICE", 4)
    mp = feas.get("max_purchase_price", {})
    row = write_kv_pairs(ws, [
        ("Target Profit", mp.get("target_profit", "")),
        ("Max Purchase Price", mp.get("max_purchase_to_hit_target", "")),
    ], start_row=row, val_format=CURRENCY_FORMAT)
    row += 1

    # Sensitivity
    sens = feas.get("sensitivity", [])
    if sens:
        row = write_section_header(ws, row, "SENSITIVITY ANALYSIS", 4)
        sens_headers = ["Scenario", "Impact on Profit", "Still Viable?"]
        sens_rows = [
            [s.get("scenario", ""), s.get("impact_on_profit", ""), "Yes" if s.get("still_viable") else "No"]
            for s in sens
        ]
        row = write_table(ws, sens_headers, sens_rows, start_row=row, col_widths=[30, 20, 12])
        row += 1

    # Verdict
    go = feas.get("go_no_go", "")
    if go:
        row = write_section_header(ws, row, f"VERDICT: {go}", 4)
        ws.cell(row=row, column=1, value=feas.get("reasoning", ""))
        row += 1

    xlsx_path = deal_dir / "outputs" / "feasibility_report.xlsx"
    return save_workbook(wb, xlsx_path)


def _generate_feasibility_markdown(
    deal_dir: Path, meta: dict[str, Any], feas: dict[str, Any]
) -> Path:
    pr = feas["profitability"]
    pa = feas["purchase_analysis"]
    mp = feas.get("max_purchase_price", {})

    lines = [
        f"# Feasibility Report — {meta.get('address', 'Unknown')}",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Summary",
        f"- **Purchase Price**: ${pa['purchase_price']:,.0f}",
        f"- **Total Cost In**: ${pr['total_cost_in']:,.0f}",
        f"- **Sale Price**: ${pr['estimated_sale_price']:,.0f}",
        f"- **Net Profit**: ${pr['net_profit']:,.0f}",
        f"- **ROI**: {pr['roi_pct']:.1f}%",
        f"- **Margin**: {pr['margin_pct']:.1f}%",
        f"- **Max Purchase (for target)**: ${mp.get('max_purchase_to_hit_target', 0):,.0f}",
        "",
    ]

    go = feas.get("go_no_go", "")
    if go:
        lines.extend([f"## Verdict: {go}", feas.get("reasoning", ""), ""])

    sens = feas.get("sensitivity", [])
    if sens:
        lines.append("## Sensitivity")
        for s in sens:
            viable = "✓" if s.get("still_viable") else "✗"
            lines.append(f"- {s.get('scenario', '')}: {viable}")
        lines.append("")

    breakers = feas.get("deal_breakers", [])
    if breakers:
        lines.append("## Deal Breakers")
        for b in breakers:
            lines.append(f"- {b}")
        lines.append("")

    lines.extend(["---", f"_Status: {meta.get('feasibility_status', 'draft')}_"])

    md_path = deal_dir / "outputs" / "feasibility_summary.md"
    md_path.write_text("\n".join(lines))
    return md_path
