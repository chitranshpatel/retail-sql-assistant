from __future__ import annotations

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
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

