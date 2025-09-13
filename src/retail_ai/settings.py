import os
import streamlit as st

# Streamlit page config should be set by the app entrypoint, not here.

# Secrets / env
OPENROUTER_API_KEY: str = st.secrets.get("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
PG_CONN: str = st.secrets.get("PG_CONN", os.getenv("PG_CONN", ""))

# Versions (log with each run for reproducibility)
PROMPT_VERSION = "v1.0"
SCHEMA_VERSION = "v1.0"

# Two OpenRouter models (cheap + stronger) with prices per 1k tokens (USD)
MODELS = [
    {"id": "nousresearch/hermes-4-405b", "in": 0.0020, "out": 0.0080},
    {"id": "deepseek/deepseek-chat-v3.1:free", "in": 0.0000, "out": 0.0000},
    {"id": "x-ai/grok-code-fast-1", "in": 0.0020, "out": 0.0150},
    {"id": "deepseek/deepseek-chat-v3.1", "in": 0.0020, "out": 0.0080},
    {"id": "qwen/qwen3-coder", "in": 0.0020, "out": 0.0080},
    {"id": "google/gemini-2.5-flash", "in": 0.0030, "out": 0.0250},
    {"id": "openai/gpt-4.1-mini", "in": 0.0040, "out": 0.0160},
    {"id": "tencent/hunyuan-a13b-instruct:free", "in": 0.0000, "out": 0.000},
]

# Keep an immutable baseline for UI selection even if MODELS is updated at runtime
DEFAULT_MODELS = MODELS.copy()

OR_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:8501",  # change if deployed
    "X-Title": "Retail Assistant MVP",
}

# Budget / safety knobs
STATEMENT_TIMEOUT_MS = 5000   # DB side timeout per query
MAX_FETCH_ROWS       = 10000  # hard row cap from DB
SOFT_COST_BUDGET     = 0.010  # ~$0.01 soft budget per question (informational)
TZ                   = "Australia/Melbourne"

# What the model may touch
BAD_KEYWORDS = (
    "update", "delete", "insert", "alter", "drop",
    "grant", "revoke", "truncate", "create", "copy",
    "call", "execute", "prepare", "deallocate", "explain",
    "vacuum", "analyze", "listen", "notify",
    ";--",  # injection sentinel
)

ALLOW_VIEWS    = ("v_sales_daily","v_promos_active")
ALLOW_TABLES   = ("stores","brands","products","promotions","sales_transactions")

# Known schema columns for basic validation
COLUMNS = {
    "v_sales_daily": {
        "date","promo_week_start_wed","store_id","article_no","product_name",
        "brand","category","sub_category","regular_price","order_multiple","base_demand","is_high_velocity",
        "units_sold","sale_price","is_promo","discount_pct","promo_channel","has_endcap","on_promo_bay","price_ratio"
    },
    "v_promos_active": {
        "promo_id","article_no","store_id","start_date","end_date","active_date",
        "offer_type","discount_pct","promo_channel","has_endcap","on_promo_bay","brand","category","sub_category"
    },
    "sales_transactions": {
        "date","store_id","article_no","units_sold","sale_price","is_promo","promo_id"
    },
    "stores": {"store_id","store_name","region","store_type","opening_date","store_area_sqm"},
    "brands": {"brand","category","sub_category","promo_allowed"},
    "products": {"article_no","product_name","brand","category","sub_category","regular_price","order_multiple","base_demand","is_high_velocity"},
    "promotions": {"promo_id","article_no","store_id","start_date","end_date","offer_type","discount_pct","promo_channel","has_endcap","on_promo_bay","brand","category","sub_category"},
}
