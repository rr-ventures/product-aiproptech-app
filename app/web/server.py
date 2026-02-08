"""FastAPI web server — AU Property Ops Copilot UI."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import DEALS_DIR, PROMPTS_DIR, TEMPLATES_DIR, ANTHROPIC_API_KEY, GEMINI_API_KEY, MANUS_API_KEY
from app.utils import deal as deal_mgr
from app.utils.converter import (
    read_spreadsheet,
    detect_template_type,
    convert_dd_checklist,
    convert_stores_list,
    convert_comps,
    convert_feasibility_template,
)

# ── App Setup ────────────────────────────────────────────────────────────
app = FastAPI(title="AU Property Ops Copilot")

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ── Helpers ──────────────────────────────────────────────────────────────

def _deal_context(deal_id: str) -> dict[str, Any]:
    """Build template context for a deal."""
    deal_dir = DEALS_DIR / deal_id
    meta = deal_mgr.load_deal(deal_dir)
    meta["id"] = deal_id
    photos = [p.name for p in deal_mgr.list_photos(deal_dir)]

    # Load outputs list
    outputs_dir = deal_dir / "outputs"
    outputs = []
    if outputs_dir.exists():
        outputs = sorted(
            f.name for f in outputs_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        )

    # Load vision data
    vision = {}
    vision_file = deal_dir / "outputs" / "vision_extraction.json"
    if vision_file.exists():
        vision = json.loads(vision_file.read_text())

    # Load comps
    comps = []
    comps_file = deal_dir / "outputs" / "comps_input.json"
    if comps_file.exists():
        comps = json.loads(comps_file.read_text())

    # Load CMA result
    cma_result = None
    cma_file = deal_dir / "outputs" / "cma_result.json"
    if cma_file.exists():
        cma_result = json.loads(cma_file.read_text())

    # Load feasibility
    feas_result = None
    feas_file = deal_dir / "outputs" / "feasibility_result.json"
    if feas_file.exists():
        feas_result = json.loads(feas_file.read_text())

    feas_inputs = {}
    feas_inputs_file = deal_dir / "outputs" / "feasibility_inputs.json"
    if feas_inputs_file.exists():
        feas_inputs = json.loads(feas_inputs_file.read_text())

    # CMA valuation shortcut
    cma_val = {}
    if cma_result and "valuation" in cma_result:
        cma_val = cma_result["valuation"]

    # Feasibility defaults
    defaults = {}
    defaults_file = TEMPLATES_DIR / "feasibility_template.json"
    if defaults_file.exists():
        defaults = json.loads(defaults_file.read_text())

    return {
        "deal": meta,
        "photos": photos,
        "outputs": outputs,
        "vision": vision,
        "comps": comps,
        "cma_result": cma_result,
        "cma_data": cma_result,
        "cma_val": cma_val,
        "feas_result": feas_result,
        "feas_inputs": feas_inputs,
        "defaults": defaults,
    }


# ═══════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════

@app.get("/")
async def dashboard(request: Request):
    deals_list = []
    for d in deal_mgr.list_deals():
        meta = deal_mgr.load_deal(d)
        meta["id"] = d.name
        meta["photo_count"] = len(deal_mgr.list_photos(d))
        deals_list.append(meta)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "deals": deals_list,
        "active_page": "dashboard",
        "deal": None,
    })


@app.get("/deals/{deal_id}")
async def deal_detail(request: Request, deal_id: str):
    ctx = _deal_context(deal_id)
    return templates.TemplateResponse("deal.html", {
        "request": request,
        **ctx,
        "active_page": "deal",
    })


@app.get("/deals/{deal_id}/cma")
async def cma_page(request: Request, deal_id: str):
    ctx = _deal_context(deal_id)
    return templates.TemplateResponse("cma.html", {
        "request": request,
        **ctx,
        "active_page": "cma",
    })


@app.get("/deals/{deal_id}/feasibility")
async def feasibility_page(request: Request, deal_id: str):
    ctx = _deal_context(deal_id)
    return templates.TemplateResponse("feasibility.html", {
        "request": request,
        **ctx,
        "active_page": "feasibility",
    })


@app.get("/deals/{deal_id}/dd")
async def dd_page(request: Request, deal_id: str):
    ctx = _deal_context(deal_id)
    # Load checklist
    checklist = []
    cl_file = TEMPLATES_DIR / "dd_checklist_placeholder.json"
    if cl_file.exists():
        data = json.loads(cl_file.read_text())
        checklist = data.get("checklist", [])

    return templates.TemplateResponse("dd.html", {
        "request": request,
        **ctx,
        "checklist": checklist,
        "active_page": "dd",
    })


@app.get("/deals/{deal_id}/reno")
async def reno_page(request: Request, deal_id: str):
    ctx = _deal_context(deal_id)
    # Check stores
    stores_warning = False
    sf = TEMPLATES_DIR / "stores_list_placeholder.json"
    if sf.exists():
        stores = json.loads(sf.read_text()).get("stores", [])
        stores_warning = any("TBA" in s.get("name", "") for s in stores)

    return templates.TemplateResponse("reno.html", {
        "request": request,
        **ctx,
        "stores_warning": stores_warning,
        "active_page": "reno",
    })


@app.get("/settings")
async def settings_page(request: Request):
    """Settings & template management page."""
    # DD checklist status
    dd_count = 0
    dd_file = TEMPLATES_DIR / "dd_checklist_placeholder.json"
    if dd_file.exists():
        dd_data = json.loads(dd_file.read_text())
        dd_count = len(dd_data.get("checklist", []))

    # Stores status
    stores_count = 0
    stores_placeholder = False
    sf = TEMPLATES_DIR / "stores_list_placeholder.json"
    if sf.exists():
        stores_data = json.loads(sf.read_text())
        stores_list = stores_data.get("stores", [])
        stores_count = len(stores_list)
        stores_placeholder = any("TBA" in s.get("name", "") for s in stores_list)

    # Feasibility defaults
    feas = {
        "acquisition_costs": {"stamp_duty_rate_pct": 4.5, "legal_conveyancing": 2500, "building_pest_inspection": 800},
        "holding_costs_monthly": {"finance_interest_rate_annual_pct": 6.5, "finance_lvr_pct": 80, "council_rates": 350, "water_rates": 150, "insurance": 250, "utilities": 100},
        "renovation": {"contingency_pct": 15},
        "selling_costs": {"agent_commission_pct": 2.0, "marketing": 5000, "styling": 3000},
        "deal_parameters": {"default_hold_period_months": 6, "target_profit_min": 50000, "target_roi_min_pct": 15, "target_margin_min_pct": 10},
    }
    ff = TEMPLATES_DIR / "feasibility_template.json"
    if ff.exists():
        feas = json.loads(ff.read_text())

    # Deals list (for comps upload target)
    deals_list = []
    for d in deal_mgr.list_deals():
        meta = deal_mgr.load_deal(d)
        meta["id"] = d.name
        deals_list.append(meta)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "active_page": "settings",
        "deal": None,
        "dd_count": dd_count,
        "stores_count": stores_count,
        "stores_placeholder": stores_placeholder,
        "feas": feas,
        "deals": deals_list,
        "anthropic_ok": bool(ANTHROPIC_API_KEY and not ANTHROPIC_API_KEY.startswith("sk-ant-...")),
        "gemini_ok": bool(GEMINI_API_KEY and not GEMINI_API_KEY.startswith("AIza...")),
        "manus_ok": bool(MANUS_API_KEY),
    })


# ═══════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/deals")
async def create_deal(
    address: str = Form(...),
    listing_url: str = Form(""),
    notes: str = Form(""),
):
    deal_dir = deal_mgr.create_deal(address, listing_url, notes)
    return JSONResponse({"id": deal_dir.name, "address": address})


@app.post("/api/deals/{deal_id}/photos")
async def upload_photos(deal_id: str, files: list[UploadFile] = File(...)):
    deal_dir = DEALS_DIR / deal_id
    photo_dir = deal_dir / "inputs" / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest = photo_dir / f.filename
        with open(dest, "wb") as out:
            content = await f.read()
            out.write(content)
        saved.append(f.filename)

    return JSONResponse({"uploaded": saved, "count": len(saved)})


@app.get("/api/deals/{deal_id}/photos/{filename}")
async def serve_photo(deal_id: str, filename: str):
    path = DEALS_DIR / deal_id / "inputs" / "photos" / filename
    if path.exists():
        return FileResponse(path)
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/deals/{deal_id}/outputs/{filename}")
async def download_output(deal_id: str, filename: str):
    path = DEALS_DIR / deal_id / "outputs" / filename
    if path.exists():
        return FileResponse(path, filename=filename)
    return JSONResponse({"error": "not found"}, status_code=404)


# ── CMA API ──────────────────────────────────────────────────────────

@app.post("/api/deals/{deal_id}/cma/vision")
async def run_vision(deal_id: str):
    """Run Gemini vision extraction on deal photos."""
    deal_dir = DEALS_DIR / deal_id
    meta = deal_mgr.load_deal(deal_dir)
    photos = deal_mgr.list_photos(deal_dir)

    if not photos:
        return JSONResponse({"error": "No photos found"}, status_code=400)

    try:
        from app.models import gemini
        prompt_text = (PROMPTS_DIR / "gemini_vision_extraction.md").read_text()
        result = gemini.extract_listing_facts(photos, prompt_text, meta.get("address", ""))
        deal_mgr.save_output(deal_dir, "vision_extraction.json", result)
        deal_mgr.save_log(deal_dir, "gemini_vision", json.dumps(result, indent=2, default=str))
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/deals/{deal_id}/cma/comps")
async def save_comps(deal_id: str, request: Request):
    """Save comparable sales data."""
    deal_dir = DEALS_DIR / deal_id
    body = await request.json()
    comps = body.get("comps", [])
    deal_mgr.save_output(deal_dir, "comps_input.json", comps)
    return JSONResponse({"saved": len(comps)})


@app.post("/api/deals/{deal_id}/cma/analyze")
async def run_cma_analysis(deal_id: str):
    """Run Claude CMA analysis."""
    deal_dir = DEALS_DIR / deal_id
    meta = deal_mgr.load_deal(deal_dir)

    # Load vision data
    vision = {}
    vf = deal_dir / "outputs" / "vision_extraction.json"
    if vf.exists():
        vision = json.loads(vf.read_text())

    # Load comps
    cf = deal_dir / "outputs" / "comps_input.json"
    if not cf.exists():
        return JSONResponse({"error": "No comps saved"}, status_code=400)
    comps = json.loads(cf.read_text())

    try:
        from app.models import claude
        system_prompt = (PROMPTS_DIR / "claude_cma_reasoning.md").read_text()
        user_message = json.dumps({
            "subject_property": {
                "address": meta.get("address", ""),
                "listing_url": meta.get("listing_url", ""),
                "notes": meta.get("notes", ""),
                "vision_extraction": vision,
            },
            "comparable_sales": comps,
        }, indent=2)

        cma_result = claude.reason(system_prompt, user_message, expect_json=True)
        deal_mgr.save_output(deal_dir, "cma_result.json", cma_result)
        deal_mgr.save_log(deal_dir, "claude_cma", json.dumps(cma_result, indent=2, default=str))

        # Generate spreadsheet + markdown
        from app.products.cma import _generate_cma_spreadsheet, _generate_cma_markdown
        _generate_cma_spreadsheet(deal_dir, meta, vision, comps, cma_result)
        _generate_cma_markdown(deal_dir, meta, cma_result)

        return JSONResponse(cma_result if isinstance(cma_result, dict) else {"raw": cma_result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/deals/{deal_id}/cma/approve")
async def approve_cma(deal_id: str, request: Request):
    deal_dir = DEALS_DIR / deal_id
    body = await request.json()
    meta = deal_mgr.load_deal(deal_dir)
    meta["cma_status"] = "approved" if body.get("approved") else "draft"
    meta["cma_completed_at"] = datetime.now().isoformat()
    deal_mgr.save_deal_meta(deal_dir, meta)
    return JSONResponse({"status": meta["cma_status"]})


# ── Feasibility API ─────────────────────────────────────────────────

@app.post("/api/deals/{deal_id}/feasibility/run")
async def run_feasibility(deal_id: str, request: Request):
    """Run the feasibility calculation + Claude commentary."""
    deal_dir = DEALS_DIR / deal_id
    meta = deal_mgr.load_deal(deal_dir)
    body = await request.json()

    # Load CMA data
    cma_data = {}
    cf = deal_dir / "outputs" / "cma_result.json"
    if cf.exists():
        cma_data = json.loads(cf.read_text())

    # Load defaults
    defaults = {}
    df = TEMPLATES_DIR / "feasibility_template.json"
    if df.exists():
        defaults = json.loads(df.read_text())

    # Save inputs
    deal_inputs = {
        "asking_price": int(body.get("asking_price", 0)),
        "purchase_price": int(body.get("purchase_price", 0)),
        "reno_budget": int(body.get("reno_budget", 0)),
        "post_reno_sale_price": int(body.get("post_reno_sale_price", 0)),
        "hold_period_months": int(body.get("hold_period_months", 6)),
        "state": body.get("state", "NSW"),
    }
    deal_mgr.save_output(deal_dir, "feasibility_inputs.json", deal_inputs)

    try:
        from app.products.feasibility import (
            _compute_feasibility,
            _generate_feasibility_spreadsheet,
            _generate_feasibility_markdown,
        )

        feas = _compute_feasibility(deal_inputs, defaults, cma_data)

        # Claude commentary
        try:
            from app.models import claude as claude_client
            system_prompt = (PROMPTS_DIR / "claude_feasibility_reasoning.md").read_text()
            user_msg = json.dumps({
                "feasibility_model": feas,
                "cma_data": cma_data,
                "deal_inputs": deal_inputs,
                "template_defaults": defaults,
            }, indent=2, default=str)
            commentary = claude_client.reason(system_prompt, user_msg, expect_json=True)
            if isinstance(commentary, dict):
                feas["sensitivity"] = commentary.get("sensitivity", [])
                feas["deal_breakers"] = commentary.get("deal_breakers", [])
                feas["go_no_go"] = commentary.get("go_no_go", "")
                feas["reasoning"] = commentary.get("reasoning", "")
        except Exception:
            pass  # Continue without Claude commentary

        deal_mgr.save_output(deal_dir, "feasibility_result.json", feas)
        _generate_feasibility_spreadsheet(deal_dir, meta, feas)
        _generate_feasibility_markdown(deal_dir, meta, feas)

        return JSONResponse(feas)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/deals/{deal_id}/feasibility/approve")
async def approve_feasibility(deal_id: str, request: Request):
    deal_dir = DEALS_DIR / deal_id
    body = await request.json()
    meta = deal_mgr.load_deal(deal_dir)
    meta["feasibility_status"] = "approved" if body.get("approved") else "draft"
    meta["feasibility_completed_at"] = datetime.now().isoformat()
    deal_mgr.save_deal_meta(deal_dir, meta)
    return JSONResponse({"status": meta["feasibility_status"]})


# ── DD API ───────────────────────────────────────────────────────────

@app.post("/api/deals/{deal_id}/dd/prompt")
async def generate_dd_prompt(deal_id: str, request: Request):
    """Generate a Manus DD job prompt."""
    deal_dir = DEALS_DIR / deal_id
    meta = deal_mgr.load_deal(deal_dir)
    body = await request.json()

    prompt_template = (PROMPTS_DIR / "manus_dd_job.md").read_text()
    job_prompt = prompt_template.replace("{address}", meta.get("address", ""))
    job_prompt = job_prompt.replace("{listing_url}", meta.get("listing_url", ""))
    job_prompt = job_prompt.replace("{state}", body.get("state", "NSW"))
    job_prompt = job_prompt.replace("{council}", body.get("council", "TBD"))

    # Load checklist
    cl_file = TEMPLATES_DIR / "dd_checklist_placeholder.json"
    checklist = []
    if cl_file.exists():
        checklist = json.loads(cl_file.read_text()).get("checklist", [])

    checklist_text = "\n".join(
        f"{item['item_number']}. [{item.get('category', '')}] {item['name']} "
        f"— Source: {item.get('source', 'TBD')} — Risk: {item.get('risk_if_fail', 'medium')}"
        for item in checklist
    )
    job_prompt = job_prompt.replace("{checklist_items}", checklist_text)

    deal_mgr.save_output(deal_dir, "dd_manus_prompt.md", job_prompt)
    return JSONResponse({"prompt": job_prompt})


@app.post("/api/deals/{deal_id}/dd/results")
async def upload_dd_results(deal_id: str, file: UploadFile = File(...)):
    """Upload DD results JSON."""
    deal_dir = DEALS_DIR / deal_id
    content = await file.read()
    dest = deal_dir / "inputs" / "dd_results.json"
    dest.write_bytes(content)
    return JSONResponse({"uploaded": True})


# ── Reno API ─────────────────────────────────────────────────────────

@app.post("/api/deals/{deal_id}/reno/chat")
async def reno_chat(deal_id: str, request: Request):
    """Send a message in the reno interview chat."""
    deal_dir = DEALS_DIR / deal_id
    body = await request.json()
    messages = body.get("messages", [])

    try:
        from app.models import claude as claude_client
        system_prompt = (PROMPTS_DIR / "claude_reno_interview.md").read_text()

        # Add stores context
        stores = []
        sf = TEMPLATES_DIR / "stores_list_placeholder.json"
        if sf.exists():
            stores = json.loads(sf.read_text()).get("stores", [])

        full_system = system_prompt
        if stores:
            full_system += f"\n\nAcceptable stores: {json.dumps(stores)}"

        response = claude_client.chat(full_system, messages)
        return JSONResponse({"response": response})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/deals/{deal_id}/reno/generate")
async def generate_reno_plan(deal_id: str, request: Request):
    """Generate the final reno plan from interview messages."""
    deal_dir = DEALS_DIR / deal_id
    meta = deal_mgr.load_deal(deal_dir)
    body = await request.json()
    messages = body.get("messages", [])

    # Ask Claude to produce final output
    messages.append({
        "role": "user",
        "content": (
            "That covers all rooms. Please now generate the complete structured "
            "renovation plan as JSON, following the output schema in your instructions."
        ),
    })

    try:
        from app.models import claude as claude_client
        system_prompt = (PROMPTS_DIR / "claude_reno_interview.md").read_text()
        response = claude_client.chat(system_prompt, messages)

        # Try to parse JSON
        cleaned = response
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{"):
                    cleaned = stripped
                    break

        try:
            reno_plan = json.loads(cleaned)
        except json.JSONDecodeError:
            reno_plan = {"raw_plan": response, "parse_error": True}

        deal_mgr.save_output(deal_dir, "reno_plan.json", reno_plan)

        # Generate artifacts if plan parsed OK
        if not reno_plan.get("parse_error"):
            from app.products.reno_planner import (
                _generate_product_spreadsheet,
                _generate_quote_tracker,
                _generate_timeline,
            )
            _generate_product_spreadsheet(deal_dir, reno_plan)
            _generate_quote_tracker(deal_dir, reno_plan)
            _generate_timeline(deal_dir, reno_plan)

        return JSONResponse(reno_plan if isinstance(reno_plan, dict) else {"raw": reno_plan})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ═══════════════════════════════════════════════════════════════════════
# TEMPLATE / CONVERTER API
# ═══════════════════════════════════════════════════════════════════════

_TYPE_LABELS = {
    "dd_checklist": "DD Checklist",
    "feasibility": "Feasibility Template",
    "stores": "Stores List",
    "comps": "Comparable Sales",
    "unknown": "Unknown (please select)",
}


@app.post("/api/templates/detect")
async def detect_template(file: UploadFile = File(...)):
    """Upload a spreadsheet and detect what template type it is."""
    content = await file.read()
    filename = file.filename or "upload.xlsx"

    try:
        rows = read_spreadsheet(file_bytes=content, filename=filename)
        detected = detect_template_type(file_bytes=content, filename=filename)

        # Build preview HTML (first 5 rows)
        preview_rows = rows[:5]
        if preview_rows:
            cols = list(preview_rows[0].keys())
            html = '<table class="preview-table"><thead><tr>'
            for c in cols[:10]:  # max 10 columns
                html += f'<th>{c}</th>'
            html += '</tr></thead><tbody>'
            for row in preview_rows:
                html += '<tr>'
                for c in cols[:10]:
                    html += f'<td>{row.get(c, "")}</td>'
                html += '</tr>'
            html += '</tbody></table>'
            if len(rows) > 5:
                html += f'<div class="text-secondary mt-1">...and {len(rows) - 5} more rows</div>'
        else:
            html = '<div class="text-secondary">No data found in file</div>'

        cols_list = list(rows[0].keys()) if rows else []

        return JSONResponse({
            "type": detected,
            "type_label": _TYPE_LABELS.get(detected, detected),
            "row_count": len(rows),
            "col_count": len(cols_list),
            "columns": cols_list,
            "preview_html": html,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/templates/convert")
async def convert_template(
    file: UploadFile = File(...),
    type: str = Form("auto"),
    deal_id: str = Form(""),
):
    """Convert an uploaded spreadsheet to JSON and save it."""
    content = await file.read()
    filename = file.filename or "upload.xlsx"

    if type == "auto":
        type = detect_template_type(file_bytes=content, filename=filename)

    try:
        if type == "dd_checklist":
            result = convert_dd_checklist(content, filename)
            dest = TEMPLATES_DIR / "dd_checklist_placeholder.json"
            dest.write_text(json.dumps(result, indent=2))
            return JSONResponse({
                "message": f"DD Checklist saved — {len(result['checklist'])} items",
                "count": len(result["checklist"]),
            })

        elif type == "stores":
            result = convert_stores_list(content, filename)
            dest = TEMPLATES_DIR / "stores_list_placeholder.json"
            dest.write_text(json.dumps(result, indent=2))
            return JSONResponse({
                "message": f"Stores list saved — {len(result['stores'])} stores",
                "count": len(result["stores"]),
            })

        elif type == "feasibility":
            result = convert_feasibility_template(content, filename)
            dest = TEMPLATES_DIR / "feasibility_template.json"
            dest.write_text(json.dumps(result, indent=2))
            return JSONResponse({
                "message": "Feasibility template saved",
            })

        elif type == "comps":
            if not deal_id:
                return JSONResponse({"error": "Select a deal for comp uploads"}, status_code=400)
            result = convert_comps(content, filename)
            deal_dir = DEALS_DIR / deal_id
            if not deal_dir.exists():
                return JSONResponse({"error": "Deal not found"}, status_code=404)
            deal_mgr.save_output(deal_dir, "comps_input.json", result)
            return JSONResponse({
                "message": f"Comps saved to deal — {len(result)} comparable sales",
                "count": len(result),
            })

        else:
            return JSONResponse({"error": f"Unknown template type: {type}. Select manually."}, status_code=400)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/templates/{template_name}")
async def download_template(template_name: str):
    """Download a template JSON file."""
    name_map = {
        "dd_checklist": "dd_checklist_placeholder.json",
        "feasibility": "feasibility_template.json",
        "stores": "stores_list_placeholder.json",
    }
    filename = name_map.get(template_name)
    if not filename:
        return JSONResponse({"error": "Unknown template"}, status_code=404)

    path = TEMPLATES_DIR / filename
    if path.exists():
        return FileResponse(path, filename=filename, media_type="application/json")
    return JSONResponse({"error": "Template file not found"}, status_code=404)


@app.put("/api/templates/feasibility")
async def update_feasibility(request: Request):
    """Update feasibility template defaults inline."""
    body = await request.json()

    # Load current template
    ff = TEMPLATES_DIR / "feasibility_template.json"
    current = {}
    if ff.exists():
        current = json.loads(ff.read_text())

    # Merge updates — body has section.field structure
    for section, fields in body.items():
        if section in current and isinstance(current[section], dict) and isinstance(fields, dict):
            current[section].update(fields)

    ff.write_text(json.dumps(current, indent=2))
    return JSONResponse({"saved": True})


@app.post("/api/deals/{deal_id}/cma/comps/upload")
async def upload_comps_spreadsheet(deal_id: str, file: UploadFile = File(...)):
    """Upload a comps spreadsheet directly from the CMA page."""
    deal_dir = DEALS_DIR / deal_id
    if not deal_dir.exists():
        return JSONResponse({"error": "Deal not found"}, status_code=404)

    content = await file.read()
    filename = file.filename or "comps.xlsx"

    try:
        comps = convert_comps(content, filename)
        deal_mgr.save_output(deal_dir, "comps_input.json", comps)
        return JSONResponse({
            "comps": comps,
            "count": len(comps),
            "message": f"Imported {len(comps)} comparable sales from {filename}",
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
