# app.py — Retail Assistant (ERD-aware, multi-model, safe SQL)
import os, re, json, time, asyncio, hashlib
from functools import lru_cache
import pandas as pd
import altair as alt
import streamlit as st
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from retail_ai import settings as cfg
from retail_ai.adapters import db as dbx
from retail_ai.services.query_service import run_query

# =========================
# App config / constants
# =========================
st.set_page_config(page_title="🛒 Retail Assistant — ERD SQL", layout="wide")

OPENROUTER_API_KEY = cfg.OPENROUTER_API_KEY
PG_CONN            = cfg.PG_CONN

if not OPENROUTER_API_KEY or not PG_CONN:
    st.error("Missing secrets. Set OPENROUTER_API_KEY and PG_CONN in .streamlit/secrets.toml.")
    st.stop()

# Versions (log with each run for reproducibility)
PROMPT_VERSION = cfg.PROMPT_VERSION
SCHEMA_VERSION = cfg.SCHEMA_VERSION

# CSS loader from package file
def _inject_styles_from_file():
    css_path = os.path.join("src", "retail_ai", "ui", "styles.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except Exception:
        pass

# Two OpenRouter models (cheap + stronger) with prices per 1k tokens (USD)
MODELS = cfg.MODELS
# OR_HEADERS = {
#     "Authorization": f"Bearer {OPENROUTER_API_KEY}",
#     "HTTP-Referer": "https://streamlit.io",
#     "X-Title": "Retail Assistant MVP"
# }
OR_HEADERS = cfg.OR_HEADERS



# Budget / safety knobs
STATEMENT_TIMEOUT_MS = cfg.STATEMENT_TIMEOUT_MS
MAX_FETCH_ROWS       = cfg.MAX_FETCH_ROWS
SOFT_COST_BUDGET     = cfg.SOFT_COST_BUDGET
TZ                   = cfg.TZ

# What the model may touch
BAD_KEYWORDS = cfg.BAD_KEYWORDS
ALLOW_VIEWS    = cfg.ALLOW_VIEWS
ALLOW_TABLES   = cfg.ALLOW_TABLES

# Known schema columns for basic validation
COLUMNS = cfg.COLUMNS

# =========================
# Prompt (ERD + views + few-shots + rules)
# =========================
def _inject_base_css():
    # Subtle, light-theme friendly styles for hero + cards + chips + build section
    st.markdown("""
    <style>
      .hero {
        padding: 1.2rem 1.2rem 0.8rem;
        border: 1px solid rgba(0,0,0,0.06);
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
        border-radius: 14px;
        margin: 0 0 1rem 0;
      }
      .hero h1 {
        font-size: 2.2rem;
        line-height: 1.15;
        margin: 0 0 .25rem 0;
        letter-spacing: -0.02rem;
      }
      .hero p.lead {
        font-size: 1.05rem;
        margin: .3rem 0 .6rem;
        color: #334155;
      }
      .badges { display: flex; gap: .5rem; flex-wrap: wrap; margin-top:.2rem; }
      .badge {
        font-size: .78rem;
        border: 1px solid rgba(15,118,110,0.25);
        padding: .25rem .6rem;
        border-radius: 999px;
        background: #ecfeff;
        color: #0f766e;
        white-space: nowrap;
      }
      .card {
        border: 1px solid rgba(0,0,0,0.06);
        background: #fff;
        border-radius: 12px;
        padding: .9rem;
        height: 100%;
      }
      .card h3 { font-size: 1rem; margin: 0 0 .35rem; }
      .muted { color: #475569; font-size: .92rem; }

      /* Chips */
      .chips {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: .5rem;
        margin: .5rem 0 1rem;
      }
      .chips .stButton > button {
        border-radius: 999px;
        border: 1px solid rgba(2,132,199,.25);
        background: #f0f9ff;
        color: #075985;
        padding: .45rem .8rem;
        font-size: .9rem;
        width: 100%;
      }
      .chips .stButton > button:hover {
        background: #e0f2fe;
        border-color: #0284c7;
      }

      /* Build section */
      .section {
        border: 1px solid rgba(0,0,0,0.06);
        background: #ffffff;
        border-radius: 14px;
        padding: 1rem;
      }
      .grid-2 {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: .9rem;
      }
      @media (max-width: 900px) {
        .grid-2 { grid-template-columns: 1fr; }
      }
      .tile {
        border: 1px solid rgba(0,0,0,0.06);
        background: #fff;
        border-radius: 12px;
        padding: .9rem;
      }
      .tile h3 { margin: 0 0 .4rem; font-size: 1.05rem; }
      .steps {
        counter-reset: step;
        list-style: none;
        padding-left: 0;
        margin: .2rem 0 0;
      }
      .steps li {
        counter-increment: step;
        margin: .2rem 0;
        padding-left: .6rem;
        position: relative;
      }
      .steps li::before {
        content: counter(step) ".";
        position: absolute;
        left: -1.2rem;
        color: #0f766e;
        font-weight: 600;
      }
      .checklist {
        list-style: none;
        padding-left: 0;
        margin: .2rem 0 0;
      }
      .checklist li {
        margin: .25rem 0;
        padding-left: 1.3rem;
        position: relative;
      }
      .checklist li::before {
        content: "✓";
        position: absolute;
        left: 0;
        color: #0f766e;
        font-weight: 700;
      }
      .stack-badges { margin-top: .35rem; display: flex; gap: .4rem; flex-wrap: wrap; }
      .kpis { display: flex; gap: .75rem; flex-wrap: wrap; margin-top: .5rem; }
      .kpi {
        background: #f8fafc;
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 10px;
        padding: .4rem .6rem;
        font-size: .85rem;
        color: #334155;
      }

      .hintline {
        font-size: 1.05rem;
        font-weight: 600;
        color: #075985;   /* blue-ish, matches your chips */
        margin: 0.5rem 0 0.8rem;
      }

      /* tighten spacing so Ask box is visible without scroll */
      .hero {
        margin-bottom: 0.5rem !important;   /* was ~1rem */
        padding-bottom: 0.6rem !important;  /* less vertical space */
      }
      .card {
        padding: 0.6rem !important;
        margin-bottom: 0.5rem !important;
      }
      .chips {
        margin: 0.25rem 0 0.5rem !important; /* less space after chips */
      }
      .askbox {
        margin-top: 0.4rem !important; /* bring askbox closer */
      }

      /* Redesigned hero overrides */
      .hero {
        padding: 1rem 1.2rem 0.8rem;
        border: 1px solid rgba(0,0,0,0.06);
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
        border-radius: 16px;
        margin: 0 0 1rem 0;
      }
      .hero h1 {
        font-size: 2.4rem;
        line-height: 1.15;
        font-weight: 800;
        margin: 0;
        color: #0f172a;
      }
      .hero p.lead.big {
        font-size: 1.15rem;
        line-height: 1.45;
        margin: 0.35rem 0 0.6rem;
        color: #334155;
        font-weight: 600;
      }
      .hero p.lead.big strong { font-weight: 800; }

      /* --- Header polish --- */
      .hero {
        padding: 1.3rem 1.2rem 1rem;
        border: 1px solid rgba(0,0,0,0.06);
        background: linear-gradient(180deg, #ffffff 0%, #f2f8ff 100%);
        border-radius: 16px;
        margin: 0 0 1rem 0;
      }
      .hero h1 {
        font-size: 2.35rem;
        line-height: 1.12;
        margin: 0 0 .35rem 0;
        letter-spacing: -0.02rem;
        font-weight: 800;
      }
      .hero p.lead.big {
        font-size: 1.15rem;
        line-height: 1.45;
        margin: .35rem 0 .65rem;
        color: #0f172a;
        font-weight: 700;
      }
      .hero p.lead.big strong { font-weight: 800; }

      /* --- Sidebar readability + width --- */
      [data-testid="stSidebar"] {
        min-width: 340px;
        max-width: 380px;
        border-right: 1px solid rgba(0,0,0,0.05);
      }
      /* Expander title: larger, bolder */
      [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-size: 1.0rem;
        font-weight: 700;
      }
      /* Sidebar labels, helper text a touch larger */
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] .stMarkdown,
      [data-testid="stSidebar"] .stCaption {
        font-size: 0.98rem;
      }
      /* Multiselect & select inputs: bigger text/chips */
      [data-testid="stSidebar"] div[data-baseweb="select"] * { font-size: 0.95rem; }
      [data-testid="stSidebar"] div[data-baseweb="tag"] {
        padding: 2px 8px;
        border-radius: 999px;
      }
      /* Radio options: bigger tappable targets */
      [data-testid="stSidebar"] .stRadio > label {
        font-size: 0.98rem;
        font-weight: 600;
      }
      [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label { padding: 2px 0; }
      /* Inputs/buttons inside sidebar a bit taller */
      [data-testid="stSidebar"] .stTextInput input,
      [data-testid="stSidebar"] button[kind="secondary"],
      [data-testid="stSidebar"] button[kind="primary"] {
        height: 40px;
        font-size: 0.95rem;
      }

      /* Highlight Ask a Question box */
      .askbox-main {
        border: 2px solid #0284c7;           /* stronger blue border */
        background: #f0f9ff;                 /* subtle light blue background */
        border-radius: 14px;
        padding: 1rem;
        margin: 0.6rem 0 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
      }
      /* Bigger label */
      .askbox-main label {
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
      }
      /* Align input + buttons in one row */
      .ask-form-row {
        display: flex;
        gap: 0.5rem;
        align-items: center;
      }
      .ask-form-row input {
        flex: 1;  /* stretch input full width */
        height: 46px !important;
        font-size: 1rem !important;
      }
      .ask-form-row button {
        height: 46px !important;
        padding: 0 1.2rem;
        font-size: 0.95rem !important;
        font-weight: 600;
      }

      /* Compact, neat ask bar */
      .askbar {
        border: 1px solid rgba(0,0,0,0.07);
        background: #ffffff;
        border-radius: 12px;
        padding: 0.75rem;
        margin: 0.5rem 0 0.8rem;
      }
      .askbar-head {
        font-size: 1rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 0.5rem;
      }
      /* Make the input and buttons same height and aligned */
      .askbar input[type="text"] {
        height: 44px !important;
        font-size: 1rem !important;
      }
      /* Buttons in the askbar */
      .askbar .stButton > button {
        height: 44px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
      }
      /* Primary = the first button in the row (Ask) */
      .askbar [data-testid="column"]:nth-of-type(2) .stButton > button {
        background: #0284c7 !important;
        color: #fff !important;
        border: none !important;
      }
      .askbar [data-testid="column"]:nth-of-type(2) .stButton > button:hover {
        background: #0369a1 !important;
      }
      /* Secondary = second button (Clear) */
      .askbar [data-testid="column"]:nth-of-type(3) .stButton > button {
        background: #f1f5f9 !important;
        color: #334155 !important;
        border: 1px solid #cbd5e1 !important;
      }
      .askbar [data-testid="column"]:nth-of-type(3) .stButton > button:hover {
        background: #e2e8f0 !important;
      }

      /* === Global Theme: Light Green + White === */
      body, .stApp {
        background: #f9fdf9 !important;   /* very light green background */
        color: #0f172a !important;
      }

      /* Hero header */
      .hero {
        background: linear-gradient(180deg, #ffffff 0%, #f0fdf4 100%) !important; /* white to light green */
        border: 1px solid rgba(0,128,0,0.1);
        border-radius: 16px;
      }
      .hero h1 {
        color: #065f46 !important;        /* deep green heading */
      }
      .hero p.lead.big {
        color: #14532d !important;        /* darker muted green text */
      }

      /* Badges (chips under hero) */
      .badge {
        border: 1px solid rgba(5,150,105,0.25) !important;
        background: #ecfdf5 !important;   /* mint green background */
        color: #065f46 !important;        /* dark green text */
      }

      /* Sidebar */
      [data-testid="stSidebar"] {
        background: #f0fdf4 !important;   /* soft light green */
        border-right: 1px solid rgba(0,128,0,0.08);
      }
      [data-testid="stSidebar"] label {
        color: #065f46 !important;
        font-weight: 600;
      }

      /* Ask box */
      .askbar {
        border: 1.5px solid #10b981 !important;   /* emerald border */
        background: #ffffff !important;           /* white inside */
      }
      .askbar-head {
        color: #065f46 !important;
      }

      /* Input field */
      .askbar input[type="text"] {
        border: 1px solid #a7f3d0 !important;     /* pale mint border */
        background: #ffffff !important;
      }

      /* Buttons */
      .askbar [data-testid="column"]:nth-of-type(2) .stButton > button {
        background: #10b981 !important;           /* emerald green */
        color: #fff !important;
      }
      .askbar [data-testid="column"]:nth-of-type(2) .stButton > button:hover {
        background: #059669 !important;           /* darker emerald */
      }
      .askbar [data-testid="column"]:nth-of-type(3) .stButton > button {
        background: #ecfdf5 !important;
        color: #065f46 !important;
        border: 1px solid #6ee7b7 !important;
      }
      .askbar [data-testid="column"]:nth-of-type(3) .stButton > button:hover {
        background: #d1fae5 !important;
      }

      /* Cards (1, 2, 3 steps) */
      .card {
        border: 1px solid rgba(16,185,129,0.25) !important;
        background: #ffffff !important;
      }
      .card h3 {
        color: #065f46 !important;
      }

      /* === Global Theme: Elegant White + Emerald Accents === */
      body, .stApp {
        background: #ffffff !important;
        color: #0f172a !important;
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
      }

      /* Hero header */
      .hero {
        padding: 1.5rem 1.5rem 1.2rem;
        border: 1px solid #e5e7eb;
        background: linear-gradient(180deg, #ffffff 0%, #f9fafb 100%) !important;
        border-radius: 20px;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      }
      .hero h1 {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0f172a !important;
      }
      .hero p.lead.big {
        font-size: 1.1rem;
        font-weight: 500;
        margin-top: 0.4rem;
        color: #475569 !important; /* slate gray */
      }
      .hero p.lead.big strong {
        color: #0f172a;
        font-weight: 700;
      }

      /* Badges (chips) */
      .badge {
        font-size: 0.82rem;
        border: 1px solid #d1fae5;
        background: #ecfdf5;
        color: #065f46;
        padding: 0.25rem 0.7rem;
        border-radius: 999px;
      }

      /* Sidebar */
      [data-testid="stSidebar"] {
        background: #f9fafb !important;
        border-right: 1px solid #e5e7eb;
      }
      [data-testid="stSidebar"] label {
        color: #0f172a !important;
        font-weight: 600;
      }

      /* Ask box */
      .askbar {
        border: 1px solid #e5e7eb !important;
        background: #ffffff !important;
        border-radius: 14px;
        padding: 1rem;
        margin: 0.8rem 0 1rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
      }
      .askbar-head {
        font-size: 1rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.5rem;
      }
      .askbar input[type="text"] {
        border: 1px solid #d1d5db !important;
        background: #ffffff !important;
        font-size: 1rem !important;
        border-radius: 8px !important;
        height: 44px !important;
      }

      /* Primary Ask button */
      .askbar [data-testid="column"]:nth-of-type(2) .stButton > button {
        background: #10b981 !important;   /* emerald */
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        height: 44px !important;
      }
      .askbar [data-testid="column"]:nth-of-type(2) .stButton > button:hover {
        background: #059669 !important;
      }

      /* Secondary Clear button */
      .askbar [data-testid="column"]:nth-of-type(3) .stButton > button {
        background: #f9fafb !important;
        color: #374151 !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 8px !important;
        height: 44px !important;
      }
      .askbar [data-testid="column"]:nth-of-type(3) .stButton > button:hover {
        background: #f3f4f6 !important;
      }

      /* Cards */
      .card {
        border: 1px solid #e5e7eb !important;
        background: #ffffff !important;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }
      .card h3 {
        color: #0f172a !important;
        font-weight: 600;
      }
      .card .muted {
        color: #475569 !important;
      }
    </style>
    """, unsafe_allow_html=True)
ERD_TEXT = """
TABLE stores(
  store_id TEXT PK, store_name TEXT, region TEXT, store_type TEXT,
  opening_date DATE, store_area_sqm NUMERIC
)
TABLE brands(
  brand TEXT PK, category TEXT, sub_category TEXT, promo_allowed BOOLEAN
)
TABLE products(
  article_no TEXT PK, product_name TEXT, brand TEXT FK->brands.brand,
  category TEXT, sub_category TEXT, regular_price NUMERIC,
  order_multiple INT, base_demand INT, is_high_velocity BOOLEAN
)
TABLE promotions(
  promo_id TEXT PK, article_no TEXT FK->products.article_no, store_id TEXT FK->stores.store_id,
  start_date DATE, end_date DATE, offer_type TEXT, discount_pct NUMERIC,
  promo_channel TEXT, has_endcap BOOLEAN, on_promo_bay BOOLEAN,
  brand TEXT, category TEXT, sub_category TEXT
)
TABLE sales_transactions(
  date DATE, store_id TEXT FK->stores.store_id, article_no TEXT FK->products.article_no,
  units_sold NUMERIC, sale_price NUMERIC, is_promo INT, promo_id TEXT
)

VIEWS (prefer these when sufficient):
v_sales_daily(
  date, promo_week_start_wed, store_id, article_no, product_name,
  brand, category, sub_category, regular_price, order_multiple, base_demand, is_high_velocity,
  units_sold, sale_price, is_promo, discount_pct, promo_channel, has_endcap, on_promo_bay, price_ratio
)
v_promos_active(
  promo_id, article_no, store_id, start_date, end_date, active_date,
  offer_type, discount_pct, promo_channel, has_endcap, on_promo_bay, brand, category, sub_category
)

Note:
- v_sales_daily does NOT contain promo_id. If you need promo identifiers/counts, join v_promos_active and use pa.promo_id.

Business rules:
- Promo week is Wed→Tue (helper exists: week_start_wed(date)).
- If time period is vague (e.g., "last week"), interpret as last 7 days:
  CURRENT_DATE - INTERVAL '6 days' to CURRENT_DATE.
- Always filter by store_id when applicable.
- Prefer the views; fall back to base tables if a needed column is not in the views.
"""

FEWSHOTS = """
Example 1:
Q: How much did article A1001 sell in its last promo?
```sql
SELECT s.store_id, s.article_no,
       MIN(s.date) AS promo_start, MAX(s.date) AS promo_end,
       SUM(s.units_sold) AS units_last_promo
FROM v_sales_daily s
JOIN v_promos_active pa
  ON pa.article_no = s.article_no
 AND pa.store_id   = s.store_id
 AND s.date        = pa.active_date
WHERE s.store_id = 'S001' AND s.article_no = 'A1001'
GROUP BY s.store_id, s.article_no
ORDER BY promo_end DESC
LIMIT 1

Example 2:
Q: Top 5 products by revenue in the last 7 days

SELECT article_no, product_name,
       SUM(units_sold * sale_price) AS revenue
FROM v_sales_daily
WHERE store_id = 'S001'
  AND date BETWEEN (CURRENT_DATE - INTERVAL '6 days') AND CURRENT_DATE
GROUP BY article_no, product_name
ORDER BY revenue DESC
LIMIT 5
 
Example 3:
Q: How many promos has brand 'CHIBrand01C' run and what was the last promo's units?
```sql
SELECT
  s.brand,
  COUNT(DISTINCT pa.promo_id) AS promo_count,
  MAX(pa.end_date)           AS last_promo_end,
  SUM(s.units_sold) FILTER (WHERE s.date = pa.active_date) AS units_during_promos
FROM v_sales_daily s
JOIN v_promos_active pa
  ON pa.article_no = s.article_no
 AND pa.store_id   = s.store_id
 AND s.date        = pa.active_date
WHERE s.store_id = 'S001'
  AND LOWER(s.brand) = LOWER('CHIBrand01C')
GROUP BY s.brand
ORDER BY last_promo_end DESC
LIMIT 1
```
"""

def build_messages(store_id: str, question: str):
  rules = f"""
  Return ONE SELECT query in a single fenced block:
  SELECT ...
  Constraints:
  SELECT-only. No DDL/DML.
  Always include a filter: store_id = '{store_id}' when relevant.
  For vague time ranges (e.g., "last 7 days"), compute them relative to the dataset end date,
  not the real current date. If you use CURRENT_DATE/NOW(), the system may replace it with the
  latest available data date.
  Text filters must be case-insensitive to avoid inconsistent results:
    - Use ILIKE for pattern matching.
    - For exact text matches, use LOWER(column) = LOWER('value').
  For listings, apply sensible ORDER BY and LIMIT.

  If the user asks to "predict/forecast" future sales, do NOT invent predictive SQL.
  Instead, return historical aggregates that are useful for planning, such as:
    - performance in the last promo (units, revenue, average discount),
    - average promo-day units vs non-promo-day units (uplift),
    - count and recency of promos (use pa.promo_id from v_promos_active),
  and make the query clearly historical.
  """

  system = "You are a precise retail data analyst. Write only SQL that runs on PostgreSQL."
  user = f"{ERD_TEXT}\n{FEWSHOTS}\n{rules}\nQuestion: {question}"
  return [{"role":"system","content":system}, {"role":"user","content":user}]

# =========================
# Guardrails & helpers
# =========================

def extract_sql(text: str):
    # First try to capture a fenced block ```sql ... ```
    m = re.search(r"```sql(.*?)```", text, flags=re.S | re.I)
    if m:
        return m.group(1).strip()
    # Otherwise fall back to first SELECT statement
    m2 = re.search(r"\bselect\b.*", text, flags=re.S | re.I)
    return m2.group(0).strip() if m2 else None

def looks_select_only(sql: str) -> bool:
    """
    Accept exactly one query:
    - Must start with SELECT or WITH
    - Forbid multiple statements (extra semicolons)
    """
    s = sql.strip()
    # Strip one optional trailing semicolon
    if s.endswith(";"):
        s = s[:-1].rstrip()
    low = s.lower()

    # Must begin with SELECT or WITH
    if not (low.startswith("select") or low.startswith("with")):
        return False

    # After removing one optional trailing semicolon, no other semicolons allowed
    if ";" in s:
        return False

    return True

def contains_bad(sql: str) -> bool:
    s = sql.lower()

    # Catch the explicit comment-injection sentinel
    if ";--" in s:
        return True

    # Build a boundary-aware pattern from BAD_KEYWORDS (skip tokens that aren't plain words)
    word_keywords = [kw for kw in BAD_KEYWORDS if kw.isalpha()]
    pattern = r"\b(" + "|".join(map(re.escape, word_keywords)) + r")\b"

    if re.search(pattern, s):
        return True

    # Also guard against COPY ... TO / FROM even if someone adds spacing or casing
    if re.search(r"\bcopy\b", s):
        return True

    return False


def mentions_allowed_objects(sql: str) -> bool:
    """
    Returns True only if the SQL text references at least one allowed view/table
    using word-boundary aware matches (reduces false positives from strings).
    """
    s = sql.lower()
    patterns = [r"\b" + re.escape(name.lower()) + r"\b" for name in (*ALLOW_VIEWS, *ALLOW_TABLES)]
    return any(re.search(p, s) for p in patterns)

def columns_exist(sql: str) -> tuple[bool, str | None]:
    """
    Naive but useful: for each known alias in FROM/JOIN, map alias->object,
    then scan for alias.column patterns and verify existence.
    """
    low = sql.lower()
    alias_of: dict[str, str] = {}
    for obj in (*ALLOW_VIEWS, *ALLOW_TABLES):
        for m in re.finditer(rf"\b{re.escape(obj.lower())}\b\s+(?:as\s+)?([a-z][a-z0-9_]*)", low):
            alias_of[m.group(1)] = obj

    bad_refs: list[str] = []
    for m in re.finditer(r"\b([a-z][a-z0-9_]*)\.(\*|[a-z][a-z0-9_]*)\b", low):
        alias, col = m.group(1), m.group(2)
        if alias not in alias_of:
            bad_refs.append(f"Undefined alias '{alias}'")
            continue
        if col == "*":
            continue
        obj = alias_of[alias]
        if col not in {c.lower() for c in COLUMNS.get(obj, set())}:
            bad_refs.append(f"{alias}.{col} not in {obj}")
    if bad_refs:
        return False, "; ".join(sorted(set(bad_refs)))
    return True, None

def ensure_store_filter(sql: str, store_id: str) -> str:
    """
    Inject a store filter safely:
    - If a store_id predicate already exists anywhere, return as-is.
    - Prefer qualifying with the detected alias of v_sales_daily / sales_transactions if present.
    - If a WHERE exists, prepend our predicate with AND (respecting whitespace).
    - Else, insert WHERE {pred} before GROUP BY / HAVING / ORDER BY / LIMIT, or at end.
    """
    original = sql
    s_low = sql.lower()

    # If query already filters by store_id, keep as is
    if re.search(r"\bstore_id\s*=\s*'[^']*'", s_low):
        return original

    # Try to detect an alias (FROM ... [AS] alias) for v_sales_daily or sales_transactions
    alias = None
    # FROM v_sales_daily [AS] x
    m = re.search(r"\bfrom\s+v_sales_daily\s+(?:as\s+)?([a-zA-Z][a-zA-Z0-9_]*)", s_low)
    if not m:
        # FROM sales_transactions [AS] x
        m = re.search(r"\bfrom\s+sales_transactions\s+(?:as\s+)?([a-zA-Z][a-zA-Z0-9_]*)", s_low)
    if m:
        alias = m.group(1)

    pred = f"{alias}.store_id = '{store_id}'" if alias else f"store_id = '{store_id}'"

    # If there's a WHERE (but without store_id), add "pred AND ( ...rest-of-where... )" for safety
    where_match = re.search(r"\bwhere\b", s_low)
    if where_match:
        insert_pos = where_match.end()
        tail = original[insert_pos:]              # everything after WHERE
        # Ensure a space before our predicate; keep existing whitespace after WHERE
        prefix = original[:insert_pos]
        sep = "" if tail.startswith((" ", "\n", "\t")) else " "
        # We want "WHERE {pred} AND (" + tail + ")" (tail stripped of leading whitespace)
        return prefix + f"{sep}{pred} AND (" + tail.lstrip() + ")"

    # Otherwise, inject a new WHERE before GROUP BY / HAVING / ORDER BY / LIMIT
    tail_kw = re.search(r"\b(group\s+by|having|order\s+by|limit)\b", s_low)
    if tail_kw:
        i = tail_kw.start()
        spacer = "" if original[:i].endswith((" ", "\n", "\t")) else " "
        return original[:i] + f"{spacer}WHERE {pred} " + original[i:]

    # No tail keywords; append at the end
    sep = "" if original.endswith((" ", "\n", "\t")) else " "
    return original + f"{sep}WHERE {pred}"


def ensure_limit(sql: str, default_limit: int = 200) -> str:
  s = sql.rstrip()
  if re.search(r"\blimit\b", s, flags=re.I):
    return s
  # if aggregating, don't force a limit
  if re.search(r"\bgroup\s+by\b|\bsum\s*\(|\bavg\s*\(|\bcount\s*\(|\bmax\s*\(|\bmin\s*\(", s, flags=re.I):
    return s
  if s.endswith(";"):
    s = s[:-1].rstrip()
  return s + f" LIMIT {default_limit}"

@lru_cache(maxsize=64)
def get_data_end_date(store_id: str) -> str | None:
    """
    Latest data date (YYYY-MM-DD) for a given store.
    Prefers the view; falls back to the base table.
    """
    try:
        with psycopg.connect(PG_CONN) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(
                    (SELECT MAX(date) FROM v_sales_daily WHERE store_id = %s),
                    (SELECT MAX(date) FROM sales_transactions WHERE store_id = %s)
                )::text
                """,
                (store_id, store_id),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        # Uncomment while debugging:
        # st.warning(f"get_data_end_date error: {e}")
        return None

def replace_current_date(sql: str, base_date: str | None) -> str:
    """
    If base_date is provided, replace CURRENT_DATE / NOW() / CURRENT_TIMESTAMP
    (and common ::date casts) with that date. Leaves explicit literals untouched.
    """
    if not base_date:
        return sql
    # Normalize replacements with regex (case-insensitive, word-boundaries)
    s = sql
    s = re.sub(r"\bcurrent_date\b", f"'{base_date}'::date", s, flags=re.I)
    # NOW() and CURRENT_TIMESTAMP used as date (cast if needed)
    s = re.sub(r"\bnow\(\)", f"'{base_date}'::timestamp", s, flags=re.I)
    s = re.sub(r"\bcurrent_timestamp\b", f"'{base_date}'::timestamp", s, flags=re.I)
    # Common cast form: CURRENT_TIMESTAMP::date
    s = re.sub(r"\bcurrent_timestamp\s*::\s*date\b", f"'{base_date}'::date", s, flags=re.I)
    # date_trunc('day', NOW()) patterns
    s = re.sub(r"date_trunc\(\s*'day'\s*,\s*now\(\)\s*\)", f"'{base_date}'::timestamp", s, flags=re.I)
    s = re.sub(r"date_trunc\(\s*'day'\s*,\s*current_timestamp\s*\)", f"'{base_date}'::timestamp", s, flags=re.I)
    return s


def repair_known_errors(sql: str, db_error_text: str) -> str | None:
    """
    Precision fixes for common alias/column mistakes without round-tripping to the LLM.
    Returns a new SQL string if a fix was applied, else None.
    """
    s = sql
    err = (db_error_text or "").lower()
    # Fix s.promo_id -> pa.promo_id when pa join exists
    if "column s.promo_id does not exist" in err and re.search(r"\bv_promos_active\b.*\bpa\b", s, re.I | re.S):
        s2 = re.sub(r"\bcount\s*\(\s*distinct\s*s\.promo_id\s*\)", "COUNT(DISTINCT pa.promo_id)", s, flags=re.I)
        if s2 != s:
            s = s2
    # Fix stray alias p.brand -> s.brand when s alias exists
    if re.search(r"\bp\.brand\b", s, re.I) and re.search(r"\bv_sales_daily\b.*\bs\b", s, re.I | re.S):
        s2 = re.sub(r"\bp\.brand\b", "s.brand", s, flags=re.I)
        if s2 != s:
            s = s2
    return s if s != sql else None



def hash_key(*parts: str) -> str:
  return hashlib.sha256("||".join(parts).encode()).hexdigest()

# =========================
# DB execution (timeout, tz, row-cap)
# =========================

def run_sql(sql: str):
    # Read-only, safe search_path, and resource limits for every query
    with psycopg.connect(PG_CONN) as conn, conn.cursor(row_factory=dict_row) as cur:
        # Start a read-only transaction first
        cur.execute("SET TRANSACTION READ ONLY;")
        # Constrain object resolution to the expected schema (adjust if not 'public')
        cur.execute("SET LOCAL search_path TO public;")
        # Session limits and context
        cur.execute(f"SET LOCAL timezone TO '{TZ}';")
        cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS};")
        cur.execute("SET LOCAL work_mem = '32MB';")

        # Execute and cap rows
        cur.execute(sql)
        rows = cur.fetchmany(MAX_FETCH_ROWS)
        cols = [d.name for d in cur.description]
        return cols, rows
  
# =========================
# LLM calls (parallel) + routing
# =========================
def call_openrouter_sync(model_id: str, messages: list[dict], max_tokens: int = 500, temperature: float = 0.2):
    payload = {"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    backoffs = [0.4, 0.8, 1.6]  # seconds

    with httpx.Client(
        timeout=30.0,
        verify=certifi.where(),
        http2=False,
        trust_env=False,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=0),
    ) as client:
        last_err = None
        for i in range(len(backoffs) + 1):
            try:
                r = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=OR_HEADERS,
                    json=payload
                )
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, httpx.ReadTimeout, httpx.ConnectError) as e:
                last_err = e
                if i < len(backoffs):
                    time.sleep(backoffs[i])
                else:
                    raise


async def call_model(model, messages):
    t0 = time.perf_counter()
    data = await asyncio.to_thread(call_openrouter_sync, model["id"], messages, 500, 0.2)
    dt_ms = int((time.perf_counter() - t0) * 1000)

    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    pin  = (usage.get("prompt_tokens") or 0) / 1000 * model["in"]
    pout = (usage.get("completion_tokens") or 0) / 1000 * model["out"]
    cost = round(pin + pout, 6)

    return {
        "model": model["id"],
        "text": text,
        "latency_ms": dt_ms,
        "usage": usage,
        "cost_usd": cost,   # <- fixed (was 'coste')
    }


def grounding_score(answer: str) -> int:
    """
    Score a model answer by how 'runnable' it looks:
    +1: contains a fenced/parsable SQL block
    +1: the SQL passes looks_select_only (SELECT/WITH, single statement)
    +1: mentions at least one allowed view/table
    Max score = 3
    """
    sql = extract_sql(answer) or ""
    has_sql = bool(sql)
    ok_shape = looks_select_only(sql) if sql else False
    mentions = mentions_allowed_objects(sql) if sql else False
    return int(has_sql) + int(ok_shape) + int(mentions)

async def try_models(messages, pref: str = "cheapest"):
    tasks = [call_model(m, messages) for m in MODELS]
    results = await asyncio.gather(*tasks)
    # score each result
    for r in results:
        r["score"] = grounding_score(r["text"])

    if pref == "fastest":
        sort_key = lambda x: (-x["score"], x["latency_ms"], x["cost_usd"])
    else:  # "cheapest"
        sort_key = lambda x: (-x["score"], x["cost_usd"], x["latency_ms"])

    winner = sorted(results, key=sort_key)[0]
    return winner, results

      
# =========================
# Light semantic cache (placeholder)
# =========================
@lru_cache(maxsize=256)
def cache_lookup(store_id: str, question: str):
  return None # hook up your own cache (e.g., Redis / DB)

def cache_store(store_id: str, question: str, sql: str, df: pd.DataFrame):
  pass

# =========================
# Logging to DB
# =========================
def log_run(payload):
  try:
    with psycopg.connect(PG_CONN) as conn, conn.cursor() as cur:
      cur.execute("""
      INSERT INTO runs(user_id, store_id, question, chosen_model,
      winner_latency_ms, winner_cost_usd, trials,
      prompt_version, schema_version)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
      """, (
      payload["user_id"], payload["store_id"], payload["question"],
      payload["chosen_model"], payload["latency_ms"], payload["cost_usd"],
      json.dumps(payload["trials"]), PROMPT_VERSION, SCHEMA_VERSION
      ))
      conn.commit()
  except Exception as e:
    st.toast(f"Log error: {e}")

# =========================
# Query runner helper
# =========================
def _handle_query(store_id: str, user_id: str, question: str):
    """Legacy path - delegate to the modular handler for consistency."""
    _handle_query_modular(store_id, user_id, question)


def _handle_query_modular(store_id: str, user_id: str, question: str):
    with st.spinner("Thinking..."):
        pref = st.session_state.get("winner_pref", "cheapest")
        try:
            result = run_query(store_id, user_id, question, pref)
        except Exception as e:
            st.error(f"Query failed: {e}")
            return

    st.session_state["last_trials"] = result.trials
    st.session_state["chosen_model"] = result.winner.get("model")
    st.session_state["chosen_latency_ms"] = result.winner.get("latency_ms")
    st.session_state["chosen_cost_usd"] = result.winner.get("cost_usd")

    total_est_cost = sum((t.get("cost_usd") or 0.0) for t in result.trials)
    if total_est_cost > SOFT_COST_BUDGET:
        st.warning(f"Estimated combined model cost ${total_est_cost:.4f} exceeds soft budget ${SOFT_COST_BUDGET:.2f}.")

    st.subheader("Chosen model & answer")
    st.write(f"**Model:** `{result.winner.get('model')}` • **Latency:** {result.winner.get('latency_ms')} ms • **Est. cost:** ${float(result.winner.get('cost_usd', 0.0)):.4f}")

    st.caption(f"Latest date used: {result.data_end_date or 'CURRENT_DATE'}")
    st.markdown("**SQL used:**")
    st.code(result.sql, language="sql")
    st.session_state["last_sql"] = result.sql

    df = result.df
    if df is not None and not df.empty:
        st.session_state["last_df"] = df
        st.dataframe(df, use_container_width=True)
        num_cols = df.select_dtypes(include=["int64","float64","int32","float32"]).columns.tolist()
        if num_cols:
            st.bar_chart(df[num_cols[0]])
    else:
        st.info(f"Query returned 0 rows for store_id='{store_id}'. Tip: widen the date range or check filters.")

    st.divider()
    st.subheader("Model trials (debug)")
    trials_pretty = []
    for t in result.trials:
        usage = t.get("usage", {}) or {}
        trials_pretty.append({
            "model": t.get("model"),
            "latency_ms": t.get("latency_ms"),
            "cost_usd": t.get("cost_usd"),
            "score": t.get("score"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        })
    st.json(trials_pretty)


# =========================
# UI (refined, scalable, portfolio-ready)
# =========================
_inject_styles_from_file()

# Hero header
st.markdown("""
<div class="hero">
  <div style="display:flex; align-items:center; gap:.6rem;">
    <span style="font-size:2.2rem;">📊</span>
    <h1 style="margin:0; font-size:2.4rem; font-weight:800; letter-spacing:-0.02rem;">
      Retail Insights Assistant
    </h1>
  </div>
  <p class="lead big" style="margin-top:.4rem;">
    <strong>Ask questions in plain English.</strong>  
    The app generates <strong>safe, SELECT-only SQL</strong>, runs it on Postgres, and returns insights instantly.
  </p>
  <div class="badges">
    <span class="badge">ERD-aware</span>
    <span class="badge">Multi-model (cost-aware)</span>
    <span class="badge">Guardrails: read-only & allow-list</span>
    <span class="badge">Postgres</span>
  </div>
</div>
""", unsafe_allow_html=True)


# Three-step feature guidance (moved above Ask box)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(
        '<div class="card"><h3>1) Ask</h3><p class="muted">e.g., “Top products last 7 days”.</p></div>',
        unsafe_allow_html=True
    )
with c2:
    st.markdown(
        '<div class="card"><h3>2) We write SQL</h3><p class="muted">Safe queries only.</p></div>',
        unsafe_allow_html=True
    )
with c3:
    st.markdown(
        '<div class="card"><h3>3) See results</h3><p class="muted">Clean table + chart.</p></div>',
        unsafe_allow_html=True
    )



# ── Ask box (main panel) — moved directly under hero ─────────
st.markdown('<div class="askbar">', unsafe_allow_html=True)
with st.form(key="ask_form"):
    st.markdown('<div class="askbar-head">Ask a question</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([8, 1.2, 1.2], vertical_alignment="center")
    with c1:
        question_main = st.text_input(
            "Ask a question",
            value=st.session_state.get("question", ""),
            placeholder="e.g., Top 5 products by revenue in the last 7 days",
            label_visibility="collapsed",
            key="ask_input",
        )
    with c2:
        ask_submit = st.form_submit_button("Ask", use_container_width=True)
    with c3:
        clear_submit = st.form_submit_button("Clear", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# --- Model selector (main panel, not hidden) ---
st.markdown("### ⚡ Model Settings")

st.caption(
    "Free models are enabled by default. "
    "Turn on paid models if you want extra quality or speed."
)

all_models = getattr(cfg, "DEFAULT_MODELS", MODELS)
all_ids = [m["id"] for m in all_models]
free_ids = [m["id"] for m in all_models if (m.get("in",0)==0 and m.get("out",0)==0)]

def model_label(mid: str) -> str:
    m = next(mm for mm in all_models if mm["id"] == mid)
    if m.get("in",0) == 0 and m.get("out",0) == 0:
        return f"{mid} · 🟢 Free"
    else:
        return f"{mid} · 💲 ${m['in']:.4f}/{m['out']:.4f} per 1k"

selected_models = st.multiselect(
    "Enabled models",
    options=all_ids,
    default=free_ids or all_ids,
    format_func=model_label,
    help="Pick which models to actually run."
)

# Persist + update
st.session_state["enabled_model_ids"] = selected_models
if selected_models:
    cfg.MODELS = [m for m in all_models if m["id"] in selected_models]
else:
    cfg.MODELS = [m for m in all_models if m["id"] in free_ids] or all_models

# Tie-breaker stays, but inline here
winner_pref_label = st.radio(
    "Tie-breaker preference (after accuracy)",
    options=["Cheapest then fastest", "Fastest then cheapest"],
    index=0,
    horizontal=True
)
st.session_state["winner_pref"] = "fastest" if "Fastest" in winner_pref_label else "cheapest"

st.divider()

# --- Results anchor: everything renders here, below the Ask box ---
results_container = st.container()

# --- Unified runner: always render results under the Ask box ---
store_id = 'S001'
user_id = 'demo_user'
q_to_run = st.session_state.get("question", "").strip() if st.session_state.get("trigger_run") else ""
if q_to_run:
    with results_container:
        _handle_query_modular(store_id, user_id, q_to_run)
    st.session_state["trigger_run"] = False

if ask_submit:
    if question_main.strip():
        st.session_state["question"] = question_main
        st.session_state["trigger_run"] = True  # unified runner flag
        st.rerun()
    else:
        st.warning("Please enter a question.")

if clear_submit:
    st.session_state["question"] = ""

# Saved questions from this session
hist = st.session_state.get("history", [])
if hist:
    with st.expander("🕘 Recent questions (this session)", expanded=False):
        for j, hq in enumerate(hist):
            h1, h2 = st.columns([8,1])
            h1.write(f"• {hq}")
            if h2.button("Ask", key=f"ask_hist_{j}"):
                st.session_state["question"] = hq
                st.session_state["trigger_run"] = True
                st.rerun()

# ── Sidebar: context & input ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Controls")
    # For demo, store/user are fixed (matches your current behavior)
    store_id = st.text_input("Store ID", value="S001", disabled=True)
    user_id  = st.text_input("User (for logs)", value="demo_user", disabled=True)

    # Data freshness
    try:
        _sidebar_end = dbx.get_data_end_date(store_id)
    except Exception:
        _sidebar_end = None

    st.caption(f"📅 Latest date used: **{_sidebar_end or 'CURRENT_DATE'}**")
    st.caption("Promo week: **Wed→Tue**  •  TZ: **Australia/Melbourne**")

    # Model selection moved to main panel.

    # Question input moved to main panel

# ── Popular questions (chips) ────────────────────────────────
st.subheader("✨ Popular questions")

EXAMPLE_QUERIES = [
    "Top 5 products by revenue in the last 7 days",
    "How much did article 200000 sell in its last promo?",
    "Daily sales and discount for brand 'CHIBrand01C' last 14 days",
    "Which categories grew week over week in S001?",
]

st.markdown('<div class="chips">', unsafe_allow_html=True)
cols = st.columns(len(EXAMPLE_QUERIES))
for i, q in enumerate(EXAMPLE_QUERIES):
    with cols[i]:
        if st.button(q, key=f"chip_{i}", use_container_width=True):
            st.session_state["question"] = q
            st.session_state["trigger_run"] = True
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# Hint line under chips
st.markdown(
    "Try things like **“category revenue last week”**, **“promo uplift for ‘CHIBrand01C’ last 14 days”**, "
    "or **“units & discount trend for article 200000”**. "
    "_Time ranges are anchored to your latest data date; queries are scoped to the store automatically._"
)

st.divider()

# ── Results zone (tabs) — These widgets are filled by your existing _handle_query ─────────
st.subheader("📊 Results")

# Results styles (added once)
st.markdown("""
<style>
  .results-card {
    border: 1px solid #e5e7eb;
    background: linear-gradient(180deg, #ffffff 0%, #f9fafb 100%);
    border-radius: 16px;
    padding: 1rem;
    margin: 0.8rem 0 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }
  .results-head { display:flex; align-items:center; justify-content:space-between; gap:.5rem; margin-bottom:.6rem; }
  .results-title { display:flex; align-items:center; gap:.5rem; font-weight:800; font-size:1.15rem; color:#0f172a; }
  .model-pill {
    font-size:.85rem; font-weight:700;
    border:1px solid #d1fae5; color:#065f46; background:#ecfdf5;
    padding:.35rem .6rem; border-radius:999px; white-space:nowrap;
  }
  .results-sub { color:#475569; font-size:.95rem; margin-top:-.2rem; }
  .kpi-row { display:grid; grid-template-columns: repeat(3, 1fr); gap:.6rem; }
  @media (max-width: 900px) { .kpi-row { grid-template-columns: 1fr; } }
  .kpi-card { border: 1px solid #e5e7eb; background:#fff; border-radius:12px; padding:.75rem .85rem; display:flex; align-items:center; gap:.6rem; }
  .kpi-ico { font-size:1.1rem; border-radius:10px; background:#f1f5f9; padding:.35rem .5rem; }
  .kpi-text { display:flex; flex-direction:column; line-height:1.2; }
  .kpi-label { font-size:.82rem; color:#64748b; }
  .kpi-value { font-size:1.05rem; font-weight:800; color:#0f172a; }
  .anchor-link { text-decoration:none; color:#94a3b8; font-size:1rem; }
  .anchor-link:hover { color:#64748b; }
</style>
""", unsafe_allow_html=True)

# Polished Results header card
chosen_model = st.session_state.get("chosen_model")
chosen_latency = st.session_state.get("chosen_latency_ms")
chosen_cost = st.session_state.get("chosen_cost_usd")
winner_pref_txt = "Cheapest → Fastest" if st.session_state.get("winner_pref") == "cheapest" else "Fastest → Cheapest"

# Friendly defaults
model_disp = chosen_model or "—"
lat_disp = f"{chosen_latency:.0f} ms" if isinstance(chosen_latency, (int, float)) else "—"
cost_disp = f"${float(chosen_cost):.4f}" if isinstance(chosen_cost, (int, float)) else "—"

st.markdown("""
<div class="results-card">
  <div class="results-head">
    <div class="results-title">
      <span>📊 Results</span>
      <a class="anchor-link" href="#results" title="Link to Results">#</a>
    </div>
    <div class="model-pill">🏆 {model}</div>
  </div>
  <div class="results-sub">When you run a question, you’ll see KPIs, data, a chart, the executed SQL, and per-model comparisons.</div>
  <div class="kpi-row" style="margin-top:.7rem;">
    <div class="kpi-card">
      <div class="kpi-ico">🤖</div>
      <div class="kpi-text">
        <div class="kpi-label">Chosen Model</div>
        <div class="kpi-value">{model}</div>
      </div>
    </div>
    <div class="kpi-card">
      <div class="kpi-ico">⚡</div>
      <div class="kpi-text">
        <div class="kpi-label">Latency</div>
        <div class="kpi-value">{latency}</div>
      </div>
    </div>
    <div class="kpi-card">
      <div class="kpi-ico">💲</div>
      <div class="kpi-text">
        <div class="kpi-label">Est. Cost</div>
        <div class="kpi-value">{cost}</div>
      </div>
    </div>
  </div>
  <div style="margin-top:.6rem; color:#475569; font-size:.9rem;">
    Tie-breaker preference: <strong>{pref}</strong>
  </div>
</div>
""".format(model=model_disp, latency=lat_disp, cost=cost_disp, pref=winner_pref_txt), unsafe_allow_html=True)

# The following tabs provide a neat, consistent structure for showing output from _handle_query
tab_summary, tab_table, tab_chart, tab_sql, tab_models, tab_logs = st.tabs(
    ["Summary", "Table", "Chart", "SQL", "Models", "Logs"]
)

with tab_summary:
    st.info(
        "After you ask a question, a short summary and key KPIs will appear here. "
        "Use the other tabs for details."
    )

with tab_table:
    st.caption("Tabular results (exportable).")
    # Add an export zone: you can re-use the df from _handle_query by st.session_state if you store it there.
    if "last_df" in st.session_state and isinstance(st.session_state["last_df"], pd.DataFrame):
        df = st.session_state["last_df"]
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "Download CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="results.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.caption("Run a query to populate the table.")

with tab_chart:
    st.caption("Quick look chart (first numeric column).")
    if "last_df" in st.session_state and isinstance(st.session_state["last_df"], pd.DataFrame):
        df = st.session_state["last_df"]
        num_cols = df.select_dtypes(include=["int64","float64","int32","float32"]).columns.tolist()
        if num_cols:
            st.bar_chart(df[num_cols[0]])
        else:
            st.caption("No numeric columns detected.")
    else:
        st.caption("Run a query to populate the chart.")

with tab_sql:
    st.caption("Exact SQL executed (after safety transforms).")
    if "last_sql" in st.session_state:
        st.code(st.session_state["last_sql"], language="sql")
    else:
        st.caption("Run a query to see the executed SQL.")

with tab_models:
    st.caption("All model trials (cost • latency • grounding score).")

    trials = st.session_state.get("last_trials")
    chosen_model = st.session_state.get("chosen_model")
    selected_models = st.session_state.get("enabled_model_ids", [])
    if not trials:
        st.caption("No trials yet. Ask a question.")
    else:
        # Filter to selected models from sidebar
        filtered = [t for t in trials if t["model"] in selected_models] if selected_models else trials

        # Build a clean dataframe
        rows = []
        for t in filtered:
            usage = t.get("usage", {}) or {}
            rows.append({
                "Model": t["model"],
                "Score": t.get("score", 0),
                "Latency (ms)": t.get("latency_ms", 0),
                "Cost (USD)": float(t.get("cost_usd", 0.0)),
                "Prompt Tokens": usage.get("prompt_tokens"),
                "Completion Tokens": usage.get("completion_tokens"),
                "Answer": t.get("text", ""),
                "Winner": "🏆" if t["model"] == chosen_model else "",
            })

        dfm = pd.DataFrame(rows)

        # Rank according to your preference (after accuracy/score)
        pref = st.session_state.get("winner_pref", "cheapest")  # 'cheapest' or 'fastest'
        if pref == "fastest":
            dfm = dfm.sort_values(by=["Score", "Latency (ms)", "Cost (USD)"], ascending=[False, True, True])
        else:
            dfm = dfm.sort_values(by=["Score", "Cost (USD)", "Latency (ms)"], ascending=[False, True, True])

        dfm.insert(0, "Rank", range(1, len(dfm) + 1))

        # Pretty, interactive table
        st.dataframe(
            dfm.drop(columns=["Answer"]),  # keep Answer out of the table; show below in expanders
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d", help="Ordering after score tie-breaker"),
                "Score": st.column_config.NumberColumn(format="%d", help="Grounding score (0–3)"),
                "Latency (ms)": st.column_config.NumberColumn(format="%.0f"),
                "Cost (USD)": st.column_config.NumberColumn(format="$%.4f"),
                "Prompt Tokens": st.column_config.NumberColumn(format="%d"),
                "Completion Tokens": st.column_config.NumberColumn(format="%d"),
                "Winner": st.column_config.TextColumn(help="Selected by the router", width="small"),
            }
        )

        # Quick charts
        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown("**Latency by model**")
            st.bar_chart(
                dfm.set_index("Model")["Latency (ms)"],
                use_container_width=True
            )
        with cc2:
            st.markdown("**Cost by model**")
            st.bar_chart(
                dfm.set_index("Model")["Cost (USD)"],
                use_container_width=True
            )

        # Cost vs Latency scatter with Score encoding
        st.markdown("**Cost vs Latency (bubble by score)**")
        scatter = alt.Chart(dfm).mark_circle().encode(
            x=alt.X("Latency (ms):Q", title="Latency (ms)"),
            y=alt.Y("Cost (USD):Q", title="Cost (USD)"),
            size=alt.Size("Score:Q", legend=None),
            color=alt.Color("Score:Q", scale=alt.Scale(scheme="blues"), legend=alt.Legend(title="Score")),
            tooltip=["Model","Score","Latency (ms)","Cost (USD)","Prompt Tokens","Completion Tokens"]
        ).properties(height=360, width="container")
        st.altair_chart(scatter, use_container_width=True)

        # Download
        st.download_button(
            "Download trials CSV",
            data=dfm.drop(columns=["Answer"]).to_csv(index=False).encode("utf-8"),
            file_name="model_trials.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Raw answers (collapsible)
        st.markdown("### Per-model answers")
        for _, r in dfm.iterrows():
            with st.expander(f"{r['Model']} {r['Winner']}"):
                st.write(rows[[rr["Model"] for rr in rows].index(r["Model"])] ["Answer"]) 

with tab_logs:
    st.caption("Run metadata and diagnostics.")
    st.caption("Note: You already write trials to the DB in `log_run()`. This tab can be extended to fetch & display them.")

st.divider()

# ── Knowledge center (polished) ───────────────────────────────────────────────
st.subheader("🧩 How it’s built")

st.markdown('<div class="section">', unsafe_allow_html=True)

# Two-column: Flow + Guardrails
st.markdown('<div class="grid-2">', unsafe_allow_html=True)

# Flow
st.markdown(f"""
<div class="tile">
  <h3>Flow</h3>
  <ol class="steps">
    <li>User asks in plain English</li>
    <li>App builds ERD-aware prompt with rules & few-shots</li>
    <li>Parallel OpenRouter calls (multiple models)</li>
    <li>Pick best answer (SQL) by score → cost → latency</li>
    <li>Apply guardrails (SELECT/WITH-only, store filter, date anchoring)</li>
    <li>Run on Postgres (read-only session, safe search_path)</li>
    <li>Render results & log trials</li>
  </ol>
  <div class="kpis">
    <div class="kpi">Prompt v{PROMPT_VERSION}</div>
    <div class="kpi">Schema v{SCHEMA_VERSION}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Guardrails
st.markdown(f"""
<div class="tile">
  <h3>Guardrails</h3>
  <ul class="checklist">
    <li>Read-only SQL session; safe <code>search_path</code></li>
    <li>Single-statement <strong>SELECT</strong> or <strong>WITH</strong> (no multi-queries)</li>
    <li>Allow-list only: <code>v_sales_daily</code>, <code>v_promos_active</code>, and core tables</li>
    <li>Auto-inject <code>store_id</code> predicate if missing</li>
    <li>Anchor “last 7 days” etc. to dataset’s latest date</li>
    <li>Timeout: {STATEMENT_TIMEOUT_MS} ms • Row cap: {MAX_FETCH_ROWS}</li>
  </ul>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # /grid-2

# Full-width: Tech stack
st.markdown("""
<div class="tile" style="margin-top:.9rem;">
  <h3>Tech stack</h3>
  <div class="stack-badges">
    <span class="badge">Streamlit</span>
    <span class="badge">Postgres</span>
    <span class="badge">OpenRouter</span>
    <span class="badge">httpx</span>
    <span class="badge">psycopg</span>
    <span class="badge">Python</span>
  </div>
  <p class="muted" style="margin-top:.4rem;">
    Multi-model routing with cost/latency tracking • Transparent SQL • Portfolio-ready logs
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # /section

# Optional: ERD excerpt
with st.expander("ERD excerpt & allowed objects", expanded=False):
    st.code(ERD_TEXT.strip(), language="markdown")
    st.caption("Allowed views: v_sales_daily, v_promos_active — Tables: stores, brands, products, promotions, sales_transactions")

# ── Auto-run example if flagged (kept from your original flow) ─────────────────
if st.session_state.get("auto_ask") and (st.session_state.get("question") or "").strip():
    st.session_state["trigger_run"] = True
    st.session_state["auto_ask"] = False
    st.rerun()



# =========================
# Pricing explainer (reference)
# =========================
# "in" = input price per 1K tokens; "out" = output price per 1K tokens.
# cost = (prompt_tokens/1000)*in + (completion_tokens/1000)*out.
