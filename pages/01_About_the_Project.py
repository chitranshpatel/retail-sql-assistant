# pages/01_About_the_Project.py
# Streamlit "About / Docs" page for the Retail Assistant
# Drop this file into a `pages/` folder alongside your main app.py

import streamlit as st
import pandas as pd
from textwrap import dedent

# ---------------------------
# Page config (safe to keep per-page)
# ---------------------------
st.set_page_config(page_title="About — Retail Assistant", layout="wide")

# ---------------------------
# Local constants (keep in sync with app.py)
# ---------------------------
PROMPT_VERSION = "v1.0"   # <- keep in sync with app.py
SCHEMA_VERSION = "v1.0"   # <- keep in sync with app.py

# ---------------------------
# Minimal CSS for polished docs
# ---------------------------
def _inject_docs_css():
    st.markdown("""
    <style>
      .hero {
        padding: 1.2rem 1.2rem .9rem;
        border: 1px solid rgba(0,0,0,0.06);
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
        border-radius: 14px;
        margin: 0 0 1rem 0;
      }
      .hero h1 { font-size: 2.1rem; line-height: 1.15; margin: 0 0 .3rem; letter-spacing: -0.02rem; }
      .hero p.lead { font-size: 1.05rem; color:#334155; margin:.25rem 0 .7rem; }
      .badges { display:flex; gap:.5rem; flex-wrap:wrap; }
      .badge {
        font-size:.78rem; border:1px solid rgba(15,118,110,.25);
        padding:.25rem .6rem; border-radius:999px; background:#ecfeff; color:#0f766e; white-space:nowrap;
      }

      .section {
        border: 1px solid rgba(0,0,0,0.06);
        background: #ffffff;
        border-radius: 14px;
        padding: 1rem;
        margin: 0 0 1rem 0;
      }
      .grid-2 { display:grid; grid-template-columns: 1fr 1fr; gap: .9rem; }
      .grid-3 { display:grid; grid-template-columns: 1fr 1fr 1fr; gap: .9rem; }
      @media (max-width: 1100px) {.grid-3 { grid-template-columns: 1fr 1fr; }}
      @media (max-width: 800px) { .grid-2, .grid-3 { grid-template-columns: 1fr; }}
      .tile {
        border: 1px solid rgba(0,0,0,0.06);
        background: #fff;
        border-radius: 12px;
        padding: .9rem;
        height: 100%;
      }
      .tile h3 { margin: 0 0 .4rem; font-size: 1.05rem; }
      .muted { color:#475569; }
      .steps { counter-reset: step; list-style:none; padding-left:0; margin:.25rem 0 0; }
      .steps li { counter-increment: step; margin:.2rem 0; padding-left:.6rem; position:relative; }
      .steps li::before { content: counter(step) "."; position:absolute; left:-1.2rem; color:#0f766e; font-weight:600; }
      .checklist { list-style:none; padding-left:0; margin:.25rem 0 0; }
      .checklist li { margin:.25rem 0; padding-left:1.3rem; position:relative; }
      .checklist li::before { content:"✓"; position:absolute; left:0; color:#0f766e; font-weight:700; }
      .stack-badges { margin-top:.35rem; display:flex; gap:.4rem; flex-wrap:wrap; }
      .kpis { display:flex; gap:.6rem; flex-wrap:wrap; margin-top:.5rem; }
      .kpi {
        background:#f8fafc; border:1px solid rgba(0,0,0,0.06); border-radius:10px;
        padding:.35rem .55rem; font-size:.85rem; color:#334155;
      }
      .pill {
        border: 1px solid rgba(2,132,199,.25);
        background: #f0f9ff; color:#075985;
        border-radius: 999px; padding: .25rem .55rem;
        font-size: .82rem; white-space: nowrap;
      }
      .code-note { background:#f8fafc; border:1px solid rgba(0,0,0,.06); border-radius:10px; padding:.6rem .7rem; }
      .small { font-size:.9rem; }
    </style>
    """, unsafe_allow_html=True)

_inject_docs_css()

# ---------------------------
# Data model — dictionary you can maintain here
# ---------------------------
TABLES = {
    "stores": [
        ("store_id", "text (PK)", "S001", "Unique store code"),
        ("store_name", "text", "Abbotsford Metro", "Human-friendly store name"),
        ("region", "text", "VIC", "Geographic region / state"),
        ("store_type", "text", "Metro", "Format, e.g., Metro / Supermarket"),
        ("opening_date", "date", "2021-03-17", "Date the store opened"),
        ("store_area_sqm", "numeric", "850", "Approx. sales floor area in m²"),
    ],
    "brands": [
        ("brand", "text (PK)", "CHIBrand01C", "Brand / label name"),
        ("category", "text", "Snacks", "Top-level category for reporting"),
        ("sub_category", "text", "Chips", "Sub-category/granularity"),
        ("promo_allowed", "boolean", "true", "If brand participates in promos"),
    ],
    "products": [
        ("article_no", "text (PK)", "200000", "SKU / article number"),
        ("product_name", "text", "Contoso Salted Chips 150g", "Product display name"),
        ("brand", "text (FK→brands.brand)", "CHIBrand01C", "Brand code"),
        ("category", "text", "Snacks", "Top-level category"),
        ("sub_category", "text", "Chips", "Granular category"),
        ("regular_price", "numeric", "3.50", "Everyday shelf price"),
        ("order_multiple", "int", "6", "Carton/xpack order multiple"),
        ("base_demand", "int", "12", "Nominal base daily units (modeling)"),
        ("is_high_velocity", "boolean", "false", "High-throughput SKU flag"),
    ],
    "promotions": [
        ("promo_id", "text (PK)", "P_2024_0001", "Promotion identifier"),
        ("article_no", "text (FK→products.article_no)", "200000", "Promoted article"),
        ("store_id", "text (FK→stores.store_id)", "S001", "Store in scope"),
        ("start_date", "date", "2024-11-20", "Promo start date"),
        ("end_date", "date", "2024-12-01", "Promo end date"),
        ("offer_type", "text", "Discount", "Mechanic, e.g., Discount/Multi-buy"),
        ("discount_pct", "numeric", "0.30", "30% off the regular price"),
        ("promo_channel", "text", "In-Store", "Channel: Catalog, Digital, In-Store"),
        ("has_endcap", "boolean", "true", "Endcap allocated?"),
        ("on_promo_bay", "boolean", "true", "Promo bay allocation?"),
        ("brand", "text", "CHIBrand01C", "Brand copy column for convenience"),
        ("category", "text", "Snacks", "Category copy column for convenience"),
        ("sub_category", "text", "Chips", "Sub-category copy column"),
    ],
    "sales_transactions": [
        ("date", "date", "2024-12-01", "Transaction date (daily grain)"),
        ("store_id", "text (FK→stores.store_id)", "S001", "Store code"),
        ("article_no", "text (FK→products.article_no)", "200000", "SKU / article"),
        ("units_sold", "numeric", "18", "Quantity sold (units)"),
        ("sale_price", "numeric", "2.45", "Actual unit price paid that day"),
        ("is_promo", "int (0/1)", "1", "Whether promo applied that day"),
        ("promo_id", "text", "P_2024_0001", "Promo id if applicable"),
    ],
}

VIEWS = {
    "v_sales_daily": [
        ("date", "date", "2024-12-01", "Observation date (daily)"),
        ("promo_week_start_wed", "date", "2024-11-27", "Wed→Tue promo week start"),
        ("store_id", "text", "S001", "Store code"),
        ("article_no", "text", "200000", "SKU / article number"),
        ("product_name", "text", "Contoso Salted Chips 150g", "Display name"),
        ("brand", "text", "CHIBrand01C", "Brand code"),
        ("category", "text", "Snacks", "Top-level category"),
        ("sub_category", "text", "Chips", "Granular category"),
        ("regular_price", "numeric", "3.50", "Everyday shelf price"),
        ("order_multiple", "int", "6", "Order pack multiple"),
        ("base_demand", "int", "12", "Nominal base demand"),
        ("is_high_velocity", "boolean", "false", "High-throughput flag"),
        ("units_sold", "numeric", "18", "Units sold on date"),
        ("sale_price", "numeric", "2.45", "Actual price paid"),
        ("is_promo", "int (0/1)", "1", "Promo indicator"),
        ("discount_pct", "numeric", "0.30", "Discount % if promo"),
        ("promo_channel", "text", "In-Store", "Channel of promo"),
        ("has_endcap", "boolean", "true", "Endcap allocation"),
        ("on_promo_bay", "boolean", "true", "Promo bay allocation"),
        ("price_ratio", "numeric", "0.70", "sale_price / regular_price"),
    ],
    "v_promos_active": [
        ("promo_id", "text", "P_2024_0001", "Promotion id"),
        ("article_no", "text", "200000", "SKU on promo"),
        ("store_id", "text", "S001", "Store in scope"),
        ("start_date", "date", "2024-11-20", "Promo start"),
        ("end_date", "date", "2024-12-01", "Promo end"),
        ("active_date", "date", "2024-11-27", "Each day promo is active"),
        ("offer_type", "text", "Discount", "Mechanic type"),
        ("discount_pct", "numeric", "0.30", "Discount %"),
        ("promo_channel", "text", "In-Store", "Channel"),
        ("has_endcap", "boolean", "true", "Endcap"),
        ("on_promo_bay", "boolean", "true", "Promo bay"),
        ("brand", "text", "CHIBrand01C", "Brand"),
        ("category", "text", "Snacks", "Category"),
        ("sub_category", "text", "Chips", "Sub-category"),
    ]
}

ALLOWED_VIEWS = ("v_sales_daily", "v_promos_active")
ALLOWED_TABLES = ("stores", "brands", "products", "promotions", "sales_transactions")

# ---------------------------
# Helper renderers
# ---------------------------
def render_dict_table(name: str, rows: list[tuple]):
    df = pd.DataFrame(rows, columns=["Column", "Type", "Example", "Description"])
    st.markdown(f"**`{name}`**")
    st.dataframe(df, use_container_width=True, hide_index=True)

def render_markdown_data_dictionary() -> str:
    def md_table(title, rows):
        md = [f"### `{title}`", "", "| Column | Type | Example | Description |", "|---|---|---|---|"]
        for col, typ, ex, desc in rows:
            ex_esc = str(ex).replace("|", "\\|")
            desc_esc = str(desc).replace("|", "\\|")
            md.append(f"| `{col}` | {typ} | {ex_esc} | {desc_esc} |")
        md.append("")
        return "\n".join(md)

    parts = [f"# Retail Assistant — Data Dictionary (Schema v{SCHEMA_VERSION})", ""]
    parts.append("## Views (preferred)")
    for vname, rows in VIEWS.items():
        parts.append(md_table(vname, rows))
    parts.append("## Base tables")
    for tname, rows in TABLES.items():
        parts.append(md_table(tname, rows))
    parts.append(f"_Generated from the About page • Prompt v{PROMPT_VERSION} • Schema v{SCHEMA_VERSION}_")
    return "\n".join(parts)

# ---------------------------
# Hero
# ---------------------------
st.markdown(f"""
<div class="hero">
  <h1>🛒 Retail Assistant — About & Documentation</h1>
  <p class="lead">
    Natural-language to <strong>safe, SELECT/WITH-only SQL</strong> for retail analytics — with guardrails, multi-model routing,
    and store-scoped, date-anchored answers.
  </p>
  <div class="badges">
    <span class="badge">ERD-aware prompting</span>
    <span class="badge">Read-only DB session</span>
    <span class="badge">Allow-listed objects</span>
    <span class="badge">Multi-model (score → cost/latency)</span>
    <span class="badge">Prompt v{PROMPT_VERSION}</span>
    <span class="badge">Schema v{SCHEMA_VERSION}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------
# Who it's for / Why I built it / Problems it solves
# ---------------------------
st.markdown('<div class="section">', unsafe_allow_html=True)
st.markdown('<div class="grid-3">', unsafe_allow_html=True)

st.markdown("""
<div class="tile">
  <h3>Who it’s for</h3>
  <ul class="checklist">
    <li>Store & department managers</li>
    <li>Category & commercial teams</li>
    <li>Analysts & BI teams</li>
    <li>Portfolio reviewers / hiring managers</li>
  </ul>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="tile">
  <h3>Why I built it</h3>
  <p class="muted small">
    I work in the retail sector and recently completed my Master of Data Science.
    I wanted to apply LLMs to practical retail questions — promo uplift, category trends, and stock decisions —
    in a way that’s <strong>safe</strong>, <strong>fast</strong>, and <strong>cost-aware</strong>.
    This project shows production-style guardrails, multi-model routing, and transparent SQL.
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="tile">
  <h3>Problems it solves</h3>
  <ul class="checklist">
    <li>“Top movers by revenue last week — in seconds.”</li>
    <li>“Uplift for SKU <code>200000</code> in its last promo.”</li>
    <li>“Which categories are growing WoW?”</li>
    <li>Self-serve insights for non-SQL users</li>
  </ul>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# What it does / Features / Flow & Guardrails / Stack
# ---------------------------
st.markdown('<div class="section">', unsafe_allow_html=True)
st.markdown('<div class="grid-2">', unsafe_allow_html=True)

st.markdown("""
<div class="tile">
  <h3>What the app does (in 60s)</h3>
  <ol class="steps">
    <li>Ask a question in plain English</li>
    <li>App drafts SQL with ERD-aware rules & few-shots</li>
    <li>Multiple models run in parallel (OpenRouter)</li>
    <li>Winner picked by accuracy score → your tie-breaker (Cheapest or Fastest)</li>
    <li>Guardrails enforce: SELECT/WITH-only, store filter, date anchoring, allow-list, limit</li>
    <li>SQL runs on Postgres (read-only) → table + quick chart + exact SQL</li>
  </ol>
  <div class="kpis">
    <div class="kpi">Grounding score = SQL present + shape OK + allowed objects</div>
    <div class="kpi">Tie-breaker: Cheapest ↔ Fastest (user selectable)</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="tile">
  <h3>Key features</h3>
  <ul class="checklist">
    <li>ERD-aware prompting & few-shots</li>
    <li><strong>Latest date used</strong> anchoring (no wall-clock drift)</li>
    <li>Read-only session; locked <code>search_path</code></li>
    <li>Allow-list: views & core tables only</li>
    <li>SELECT/WITH-only single statement; DDL/DML blocked</li>
    <li>Statement timeout & row cap</li>
    <li>Auto-repair on SQL error (one pass)</li>
    <li>Cost/latency visible per model</li>
  </ul>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

st.markdown("""
<div class="tile" style="margin-top:.9rem;">
  <h3>Tech stack</h3>
  <div class="stack-badges">
    <span class="badge">Streamlit</span>
    <span class="badge">Postgres</span>
    <span class="badge">OpenRouter</span>
    <span class="badge">Python</span>
    <span class="badge">httpx</span>
    <span class="badge">psycopg</span>
  </div>
  <p class="muted" style="margin-top:.4rem;">
    Multi-model routing with cost/latency tracking • Transparent SQL • Portfolio-ready logs
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Prompting rules & Safety
# ---------------------------
with st.expander("Prompting rules & safety guardrails", expanded=True):
    st.markdown("""
- Return **ONE** query (SELECT or WITH). No multi-statements.
- Always filter by `store_id` when relevant; app injects it if missing.
- Vague time ranges (e.g., “last 7 days”) anchor to the dataset’s **Latest date used** (max date), not wall-clock.
- Case-insensitive text filters: `ILIKE` or `LOWER(col)=LOWER('value')`.
- Prefer views (`v_sales_daily`, `v_promos_active`); fall back to base tables only when needed.

**Safety at runtime**
- Read-only transaction, `search_path` pinned.
- Allow-listed objects only.
- Blocklist: UPDATE, DELETE, INSERT, ALTER, DROP, CREATE, COPY, EXECUTE, … (and multi-statement attempts).
- Enforce `LIMIT` for non-aggregates; global row cap; statement timeout.
- Auto-repair once if SQL fails; show repaired SQL in the UI.
    """)

# ---------------------------
# Model routing & scoring
# ---------------------------
with st.expander("Model routing & scoring", expanded=False):
    st.markdown("""
- Run all configured models in parallel.
- Compute **Grounding score**:
  1) Parsable fenced SQL present  
  2) Passes single-statement shape (SELECT/WITH)  
  3) Mentions allowed views/tables
- Your selected tie-breaker resolves ties: **Cheapest → Fastest** or **Fastest → Cheapest**.
- If winner fails: one-pass auto-repair; otherwise error surfaced with details.
    """)

# ---------------------------
# Data model — Views first (preferred), then Base tables
# ---------------------------
st.subheader("Data model & dictionary")

st.caption("**Views (preferred for analytics)**")
for vname, rows in VIEWS.items():
    render_dict_table(vname, rows)

st.caption("**Base tables**")
for tname, rows in TABLES.items():
    render_dict_table(tname, rows)

st.download_button(
    "Download Data Dictionary (Markdown)",
    data=render_markdown_data_dictionary().encode("utf-8"),
    file_name="retail_assistant_data_dictionary.md",
    mime="text/markdown",
    use_container_width=True
)

# ---------------------------
# How to use & Examples
# ---------------------------
with st.expander("How to use (step-by-step) & example questions", expanded=False):
    st.markdown("""
**Workflow**
1. Click a popular question chip or type your own.
2. See the chosen model, latency, and cost.
3. Review the exact SQL, the results table, and a quick chart.
4. Download CSV or copy SQL and iterate.

**Examples**
- “Top 5 products by revenue in the last 7 days.”
- “How much did article **200000** sell in its last promo?”
- “Daily sales and discount for brand **‘CHIBrand01C’** last 14 days.”
- “Which categories grew week over week in **S001**?”
    """)

# ---------------------------
# Limitations, Roadmap, Deployment, Privacy, Testing
# ---------------------------
with st.expander("Limitations & edge cases", expanded=False):
    st.markdown("""
- Schema-specific: prompts assume your ERD and views exist.
- Extremely fuzzy questions may under-specify columns.
- Free models can be slower; paid models may cost more.
- Zero-row results usually indicate overly tight filters (brand casing, dates, or store scope).
    """)

with st.expander("Roadmap", expanded=False):
    st.markdown("""
- Preflight compilation before model selection (lower error rate).
- Richer visuals (Altair/Plotly for time-series).
- Semantic cache (Redis) for repeated questions.
- Inline “why this SQL?” annotations for transparency.
- Admin page for per-model performance & costs over time.
    """)

with st.expander("Deployment & configuration", expanded=False):
    st.markdown("""
- **Secrets**: `OPENROUTER_API_KEY`, `PG_CONN` in `.streamlit/secrets.toml`.
- **Theme**: light theme via `.streamlit/config.toml`.
- DB role: read-only access to views/tables; statement timeout configured.
- Optional environment split: dev/prod with separate keys and DBs.
    """)

with st.expander("Privacy & security posture", expanded=False):
    st.markdown("""
- Read-only DB access; app avoids mutating data.
- App shares prompt text with the selected LLM provider via OpenRouter.
- Do not include PII fields in prompts unless explicitly intended & approved.
- Logs can be minimized or disabled depending on environment.
    """)

with st.expander("Testing & quality", expanded=False):
    st.markdown("""
- Guardrail unit tests: `ensure_store_filter`, `looks_select_only`, `ensure_limit`, `contains_bad`.
- Golden-set prompts → expected SQL snapshot tests.
- Manual QA checklist for top business questions & zero-row handling.
    """)

# ---------------------------
# About the author
# ---------------------------
st.markdown("""
<div class="section">
  <div class="tile">
    <h3>About the author</h3>
    <p class="muted small">
      I work in retail and completed a Master of Data Science. I enjoy building practical AI tools that
      combine <strong>LLM safety</strong>, <strong>cost-aware routing</strong>, and <strong>clear analytics</strong>.
      This app applies those principles to retail decisions like promos, category trends, and stock planning.
    </p>
  </div>
</div>
""", unsafe_allow_html=True)
