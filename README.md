# AU Property Ops Copilot

Local-only property investment tool. 4 products, multi-model AI, spreadsheet artifacts, human sign-off at every step.

---

## ⚡ Start Here (3 steps)

### Step 1: Install

```bash
pip install -r requirements.txt
```

### Step 2: Add API Keys

Copy `.env.example` → `.env`. Add these two keys:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
GEMINI_API_KEY=AIza-your-key-here
```

- **Anthropic key** → [console.anthropic.com](https://console.anthropic.com) → API Keys
- **Gemini key** → [aistudio.google.com](https://aistudio.google.com) → Get API Key

### Step 3: Run

```bash
python run.py
```

Open **http://localhost:8000** in your browser. That's it.

> Want the CLI instead? Run `python run.py --cli`

---

## 🧭 What You Need to Give Me (Resources to Upload)

Before the products work well, you need to provide some of your own data. Here's exactly what and where:

| What | File to Replace | Format | Needed For |
|------|----------------|--------|------------|
| **Feasibility template** | `templates/feasibility_template.json` | JSON with your cost assumptions | Product 3 (Feasibility) |
| **DD checklist** | `templates/dd_checklist_placeholder.json` | JSON array of checklist items | Product 2 (Due Diligence) |
| **Stores list** | `templates/stores_list_placeholder.json` | JSON with your preferred suppliers | Product 4 (Reno Planner) |
| **CMA examples** | Not a file — just run your first CMA! | Comp sales data you enter manually | Product 1 (CMA) |

### How to provide your Feasibility Template

Open `templates/feasibility_template.json`. It already has sensible defaults. Change the numbers to match yours:

- Stamp duty rate for your state
- Your finance interest rate + LVR
- Monthly council rates, water, insurance
- Agent commission %, marketing budget
- Target profit and ROI thresholds

### How to provide your DD Checklist

Open `templates/dd_checklist_placeholder.json`. Replace the 10 example items with your full 100-step checklist. Each item needs:

```json
{
  "item_number": 1,
  "category": "Planning & Zoning",
  "name": "Confirm zoning classification",
  "source": "State planning portal",
  "risk_if_fail": "critical"
}
```

### How to provide your Stores List

Open `templates/stores_list_placeholder.json`. Replace the "TBA" entries with your actual suppliers per category (tiles, kitchen, bathroom, flooring, etc.).

---

## 📊 Product 1 — CMA Engine

**Goal**: Reduce CMA from ~45 min → ~5 min.

### How to use it, step by step:

1. **Create a new deal** — Click "New Deal", enter the address and listing URL.
2. **Upload listing photos** — Drag & drop or click to upload. These go to the deal's `inputs/photos/` folder.
3. **Run Gemini Vision** — Click "Run Gemini Vision Extraction". Gemini looks at all photos and extracts: property type, beds/baths/cars, condition, finish level, room-by-room notes, uncertainty flags.
4. **Add comparable sales** — Click "+ Add Comp" and enter each sold comp: address, sold price, date, beds/baths/cars, land area, distance. Or upload a JSON file with comps.
5. **Run CMA Analysis** — Click "Run CMA Analysis with Claude". Claude analyses all comps vs your subject, applies adjustments, weights comps, and produces a value range + confidence score. All math is shown.
6. **Review** — Check the results. Download the spreadsheet, JSON, and markdown.
7. **Approve or Draft** — Sign off if you're happy. Nothing is finalized without your approval.

### Where do I get comps?

You don't have Domain API access yet, so:

- **Manual entry**: Type in comps from your own research.
- **ChatGPT web search**: Ask ChatGPT to find recent sold comps in the area. Copy the data into the comp entry form.
- **Upload JSON**: If you export comps from any source, format as JSON and upload directly.

### Output files

After running CMA, you get these in the deal's `outputs/` folder:

- `cma_report.xlsx` — Full spreadsheet with comps table, adjustments, valuation
- `cma_result.json` — Machine-readable (feeds into Feasibility automatically)
- `cma_summary.md` — Human-readable summary

---

## 💰 Product 3 — Feasibility Engine

**Goal**: Should I buy this property? What's my max purchase price?

### How to use it, step by step:

1. **Run CMA first** — Feasibility needs the CMA data (it auto-loads it).
2. **Go to Feasibility** — Click "Feasibility" in the sidebar or deal page.
3. **Enter deal inputs** — Asking price, your purchase price, reno budget, expected sale price, hold period, state.
4. **Click "Calculate Feasibility"** — The tool computes everything locally, then sends to Claude for commentary + GO/NO-GO verdict.
5. **Review** — Check: net profit, ROI, margin, max purchase price, sensitivity analysis, deal breakers.
6. **Approve or Draft** — Sign off when satisfied.

### Output files

- `feasibility_report.xlsx` — Full cost breakdown spreadsheet
- `feasibility_result.json` — Machine-readable
- `feasibility_summary.md` — Summary with verdict

---

## ✅ Product 2 — Due Diligence Copilot

**Goal**: Checklist-driven DD with AI assistance.

### How to use it, step by step:

1. **Provide your DD checklist** — Replace `templates/dd_checklist_placeholder.json` with your full checklist (see format above).
2. **Open DD for a deal** — Go to the deal page, click "Due Diligence".
3. **Generate Manus prompt** — Enter the state and council, click "Generate Manus Prompt".
4. **Run the DD** — Copy the prompt into Manus (or ChatGPT for web-searchable items). Work through the checklist.
5. **Upload results** — When done, save your results as `dd_results.json` and upload via the UI.
6. **Review the compiled report** — The tool generates a DD spreadsheet and markdown report.

### Output files

- `dd_report.xlsx` — Checklist pass/fail + evidence index
- `dd_report.md` — Formatted report
- `dd_manus_prompt.md` — The prompt you generated

---

## 🔨 Product 4 — Reno Execution Planner

**Goal**: After buying, plan the renovation room-by-room → get trade plans + product lists + timeline.

### How to use it, step by step:

1. **Provide your stores list** — Edit `templates/stores_list_placeholder.json` with your preferred suppliers.
2. **Open Reno Planner** — Go to the deal page, click "Reno Planner".
3. **Start the interview** — Click "Start Interview". Claude asks you about each room: what's there now, what you want, budget level, specific products, must-haves vs nice-to-haves.
4. **Answer room by room** — Type your answers. Claude will confirm scope per room before moving on.
5. **Finish** — When all rooms are covered, click "Finish & Generate Plan".
6. **Download artifacts** — Product list spreadsheet, quote tracker, timeline, trade scope documents.

### Output files

- `product_list.xlsx` — What to buy, where, when, budget range
- `quote_tracker.xlsx` — Track tradie quotes
- `timeline.xlsx` — Phased schedule with dependencies
- `trade_scopes/` — Per-trade scope docs + quote request email templates

---

## 🤖 Which AI Does What?

| AI | Role | How It's Used |
|----|------|--------------|
| **Gemini** | Vision / image analysis | Automated via API — analyses listing photos |
| **Claude** | Reasoning / report generation | Automated via API — CMA analysis, feasibility commentary, reno planning |
| **ChatGPT** | Web searching | Use manually — find comps, lookup market data, DD research |
| **Manus** | Long-running agent tasks | Use manually — paste DD prompts, collect evidence |

### Why ChatGPT for web searching?

ChatGPT has built-in web search that's good for finding comps, checking council info, and market research. Use it as your research assistant, then bring the data back into this tool.

---

## 📁 Where Everything Lives

```
deals/                              ← All your deals (auto-created, gitignored)
  20260208-143022_42-smith-st/
    deal.json                       ← Deal metadata
    inputs/photos/                  ← Listing photos
    outputs/                        ← Spreadsheets, JSON, Markdown
    logs/                           ← Model call summaries

templates/                          ← YOUR data goes here
  feasibility_template.json         ← Your cost assumptions
  dd_checklist_placeholder.json     ← Your DD checklist
  stores_list_placeholder.json      ← Your preferred stores

prompts/                            ← AI prompts (editable)
  gemini_vision_extraction.md
  claude_cma_reasoning.md
  claude_feasibility_reasoning.md
  claude_reno_interview.md
  manus_dd_job.md
```

---

## 🔑 Human Sign-Off

Every product ends with an approval step. Nothing is "final" without you clicking Approve. Outputs are marked **draft** until then.

---

## 🛠 Troubleshooting

**"ANTHROPIC_API_KEY is not set"** → You didn't create `.env`. Copy `.env.example` → `.env` and add your keys.

**"GEMINI_API_KEY is not set"** → Same thing — add your Gemini key to `.env`.

**Photos not showing** → Make sure they're JPG, PNG, or WebP. HEIC files may not display in the browser.

**CMA analysis seems wrong** → Edit `prompts/claude_cma_reasoning.md` to adjust the methodology. The prompts are just text files — tweak them freely.

**Feasibility numbers off** → Check `templates/feasibility_template.json` — are the default rates (stamp duty, interest, etc.) correct for your state?
