# 🛒 Retail Insights Assistant

**Natural language to safe, SELECT-only SQL for retail analytics — with guardrails, multi-model LLM routing, and instant insights.**


<img width="1086" height="704" alt="Screenshot 2025-09-22 at 11 41 49 PM" src="https://github.com/user-attachments/assets/dae09712-cea6-4b6d-b331-5d58bc7168e1" />



---

## Overview

Retail Insights Assistant is a Streamlit app that lets users ask plain-English questions about retail sales, promotions, products, brands, and stores. The app translates these questions into safe, read-only SQL queries, runs them on a Postgres database, and returns results with charts and KPIs — all with strong guardrails and transparent model routing.

- **Database:** Postgres with tables for stores, products, brands, promotions, and daily sales transactions.
- **LLM Routing:** Multiple OpenRouter models run in parallel; the best answer is chosen by grounding score, cost, and latency.
- **Guardrails:** Only SELECT/WITH queries, allow-listed views/tables, store/date scoping, and automatic error repair.
- **UI:** Modern Streamlit interface with charts, data export, and full SQL transparency.

---

## Features

- **Ask in plain English:** e.g., “Top 5 products by revenue in the last 7 days”
- **Automatic SQL generation:** ERD-aware prompting, few-shot examples, and business rules
- **Safe execution:** Only SELECT/WITH queries, read-only DB session, allow-listed objects
- **Multi-model LLM routing:** Parallel calls to multiple models, with cost/latency tracking
- **Store and date scoping:** All queries are filtered by store and anchored to the latest available data date
- **Transparent results:** See the exact SQL, download results, and review per-model answers
- **Portfolio-ready logs:** All runs are logged with metadata for reproducibility

---

## Data Model

**Tables:**
- `stores`: Store metadata (region, type, area, etc.)
- `brands`: Brand/category hierarchy and promo eligibility
- `products`: SKU-level product info, pricing, demand
- `promotions`: Promo events, mechanics, and scope
- `sales_transactions`: Daily sales, price, promo flags

**Views (preferred for analytics):**
- `v_sales_daily`: Enriched daily sales, discounts, promo context
- `v_promos_active`: Promo calendar (one row per active day per promo)

See [`schema.txt`](schema.txt) or the in-app "About" page for full details.

---

## Example Questions

- “Top 5 products by revenue in the last 7 days”
- “How much did article 200000 sell in its last promo?”
- “Daily sales and discount for brand ‘CHIBrand01C’ last 14 days”
- “Which categories grew week over week in S001?”

---

## How It Works

1. **User asks a question** in plain English.
2. **App builds a prompt** with ERD, views, few-shots, and business rules.
3. **Multiple LLMs** (via OpenRouter) generate candidate SQL queries in parallel.
4. **Best SQL is selected** by grounding score, cost, and latency.
5. **Guardrails applied:** SELECT/WITH-only, store/date filters, allow-list, and error repair.
6. **SQL runs on Postgres** (read-only, safe search_path).
7. **Results displayed:** KPIs, table, chart, SQL, and per-model comparisons.
8. **All runs logged** for reproducibility and analysis.

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-org/retail-assistant-mvp.git
cd retail-assistant-mvp
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure secrets

Create a `.streamlit/secrets.toml` file with your credentials:

```toml
OPENROUTER_API_KEY = "sk-..."
PG_CONN = "postgresql://user:password@host:port/dbname"
```

### 4. (Optional) Configure Streamlit theme

Create `.streamlit/config.toml` for a light theme:

```toml
[theme]
base="light"
```

### 5. Run the app

```bash
streamlit run app.py
```

The app will be available at [http://localhost:8501](http://localhost:8501).

---

## Project Structure

```
retail-assistant-mvp/
├── app.py                        # Streamlit app entrypoint (UI, layout, interactions)
├── load_csvs.py                  # Helper to load CSVs into Postgres
├── schema.txt                    # Textual ERD/schema summary
├── readme.txt                    # Project overview (replace with README.md)
├── requirements.txt              # Python dependencies
├── runtime.txt                   # Python runtime pin (for Streamlit Cloud)
├── .gitignore                    # Standard ignores (.venv/, .DS_Store, etc.)
├── data/                         # Sample CSV datasets
│   ├── stores.csv
│   ├── brands.csv
│   ├── products.csv
│   ├── promotions.csv
│   └── sales_transactions.csv
├── pages/                        # Streamlit multipage docs
│   └── 01_About_the_Project.py   # About & documentation page
├── src/
│   └── retail_ai/                # Core app logic
│       ├── __init__.py
│       ├── settings.py           # Config, model list, constants, allow-lists
│       ├── ui/
│       │   └── styles.css        # Additional UI styling
│       ├── adapters/             # External adapters (DB, LLM)
│       │   ├── __init__.py
│       │   ├── db.py             # Postgres access (read-only, limits, logging)
│       │   └── llm_openrouter.py # OpenRouter client + model routing
│       ├── domain/               # Domain rules & guardrails
│       │   ├── __init__.py
│       │   ├── guardrails.py     # SQL extraction, validation, safe rewrites
│       │   └── prompts.py        # ERD, few-shots, message builder
│       └── services/
│           └── query_service.py  # Orchestrates LLM → SQL → DB → DataFrame
└── .streamlit/                   # Streamlit config & secrets
    ├── secrets.toml              # OPENROUTER_API_KEY, PG_CONN (not committed)
    └── config.toml               # Streamlit UI/config options

```

---

## Safety & Guardrails

- **Read-only DB session** with safe `search_path`
- **Single-statement SELECT/WITH** queries only (no DDL/DML)
- **Allow-list:** Only views/tables defined in schema
- **Auto-inject store/date filters** if missing
- **Timeouts and row caps** on all queries
- **Automatic SQL repair** for common errors
- **No PII in prompts or logs**

---

## Extending & Customizing

- **Add new models:** Edit `settings.py` to add or remove OpenRouter models.
- **Change schema:** Update `schema.txt` and the ERD prompt in `app.py`.
- **Add business rules:** Modify the prompt construction logic for new constraints.
- **UI customization:** Edit CSS in `src/retail_ai/ui/styles.css`.

---

## Roadmap

- Preflight SQL compilation before model selection
- Richer visualizations (Altair/Plotly)
- Semantic cache for repeated questions
- Inline “why this SQL?” explanations
- Admin dashboard for model performance/costs

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Author

Built by Chitransh Patel 
For questions or collaboration, open an issue or reach out via patel.chitransh2000@gmail.com
