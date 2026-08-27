# AGL Data Validation Tool

A lightweight local tool that validates retail crawl data for CPG clients and generates AI-narrated quality reports.

Built for: **Nestlé India** (first client), extendable to other clients via config.

---

## Quick Start

### 1. Install dependencies
```powershell
py -3 -m pip install -r requirements.txt
```

### 2. Set your Gemini API key
Edit the `.env` file and replace the placeholder:
```
GEMINI_API_KEY=your_actual_key_here
```
Get a free key (no card needed) at → https://aistudio.google.com/apikey

### 3. Run the app
```powershell
py -3 -m streamlit run app.py
```
The app opens in your browser at `http://localhost:8501`.

---

## How It Works

1. **Select** a client + platform + data stage in the sidebar
2. **Click Run Validation** — all checks run as real DuckDB SQL queries
3. **Review results** — metric cards, per-rule breakdown, sample failure rows
4. **Read the AI report** — Gemini narrates the findings in plain English
5. **Audit logs** are saved automatically to the `logs/` folder

---

## Validation Rules (Nestlé)

| # | Rule | What it checks |
|---|---|---|
| 1 | Data Hygiene | Strips `region='All'` rollup rows before all other checks |
| 2 | Price Rule | `MRP >= SP` must always hold |
| 3 | OSA OOS | `osa_remark=0` must have `osa=0` |
| 4 | OSA Not Listed | `osa_remark=2` must have `osa=0` |
| 5 | In-Stock Integrity | `osa=1` rows must have valid prices, non-blank title, `price_rp >= price_sp` |
| 6 | Completeness | Row count = expected SKUs × locations (requires config) |
| 7 | Platform ID | Sub-platforms (Amazon Now, Fresh) must have correct product_id prefix |

---

## Using Real Data

By default the tool generates synthetic data. To switch to real data:

1. Export `ebux_pdp` from Databricks as a Parquet or CSV file
2. Place it at `data/ebux_pdp.parquet` (or `data/ebux_pdp.csv`)
3. Restart the app — it auto-detects the file

If column names differ from the defaults, update the `column_map` section in `config/nestle.yaml`.

---

## Adding a New Client

1. Copy `config/nestle.yaml` → `config/yourclient.yaml`
2. Update `client_id`, `client_display_name`, `active_platforms`
3. Set the correct `column_map` if the table schema differs
4. The new client appears in the sidebar dropdown automatically

---

## Run Tests

```powershell
py -3 -m pytest tests/ -v
```

---

## Project Structure

```
├── app.py                    # Streamlit UI
├── requirements.txt
├── .env                      # Put your GEMINI_API_KEY here
├── config/
│   └── nestle.yaml           # Nestlé client config
├── src/
│   ├── config_loader.py      # YAML → validated Pydantic models
│   ├── data_loader.py        # DuckDB builder (synthetic + real files)
│   ├── validators.py         # 7 rule functions (pure SQL)
│   ├── validation_runner.py  # Orchestrator + audit logger
│   └── ai_narrator.py        # Gemini API call + fallback
├── logs/                     # Auto-created, one JSON per run
├── tests/
│   └── test_validators.py    # Unit tests for all rules
└── data/                     # Drop real exports here (git-ignored)
```
