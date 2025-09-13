from __future__ import annotations
import json
from functools import lru_cache

import psycopg
from psycopg.rows import dict_row

from retail_ai import settings


def run_sql(sql: str):
    with psycopg.connect(settings.PG_CONN) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION READ ONLY;")
        cur.execute("SET LOCAL search_path TO public;")
        cur.execute(f"SET LOCAL timezone TO '{settings.TZ}';")
        cur.execute(f"SET LOCAL statement_timeout = {settings.STATEMENT_TIMEOUT_MS};")
        cur.execute("SET LOCAL work_mem = '32MB';")
        cur.execute(sql)
        rows = cur.fetchmany(settings.MAX_FETCH_ROWS)
        cols = [d.name for d in cur.description]
        return cols, rows


@lru_cache(maxsize=64)
def get_data_end_date(store_id: str) -> str | None:
    try:
        with psycopg.connect(settings.PG_CONN) as conn, conn.cursor() as cur:
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
        return None


def log_run(payload):
    with psycopg.connect(settings.PG_CONN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs(
                user_id, store_id, question, chosen_model,
                winner_latency_ms, winner_cost_usd, trials,
                prompt_version, schema_version
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                payload["user_id"], payload["store_id"], payload["question"],
                payload["chosen_model"], payload["latency_ms"], payload["cost_usd"],
                json.dumps(payload["trials"]), settings.PROMPT_VERSION, settings.SCHEMA_VERSION,
            ),
        )
        conn.commit()

