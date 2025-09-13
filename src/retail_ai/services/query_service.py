from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from retail_ai import settings
from retail_ai.domain.prompts import build_messages
from retail_ai.domain import guardrails as gr
from retail_ai.adapters import db as dbx
from retail_ai.adapters import llm_openrouter as llm


@dataclass
class QueryResult:
    sql: str
    df: Optional[pd.DataFrame]
    trials: list[dict]
    winner: dict
    data_end_date: Optional[str]


def run_query(store_id: str, user_id: str, question: str, winner_pref: str = "cheapest") -> QueryResult:
    cached_df = None  # hook up your own cache layer if desired

    messages = build_messages(store_id, question)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        winner, trials = loop.run_until_complete(llm.try_models(messages, winner_pref))
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    sql = gr.extract_sql(winner["text"]) or ""

    # Guardrails
    if not sql:
        raise ValueError("No SQL found in the model's answer.")
    if not gr.looks_select_only(sql):
        raise ValueError("SQL is not SELECT/WITH-only.")
    if gr.contains_bad(sql):
        raise ValueError("Blocked keyword in SQL.")
    if not gr.mentions_allowed_objects(sql):
        raise ValueError("SQL references objects outside allowed views/tables.")
    ok_cols, col_msg = gr.columns_exist(sql)
    if not ok_cols:
        raise ValueError(f"Invalid column reference(s): {col_msg}")

    data_end_date = dbx.get_data_end_date(store_id)
    safe_sql = gr.ensure_store_filter(sql, store_id)
    safe_sql = gr.ensure_limit(safe_sql)
    replaced = gr.replace_current_date(safe_sql, data_end_date)
    if replaced:
        safe_sql = replaced

    try:
        cols, rows = dbx.run_sql(safe_sql)
    except Exception as e:
        # Try known repairs first
        fixed_once = gr.repair_known_errors(safe_sql, str(e))
        if fixed_once and gr.looks_select_only(fixed_once) and not gr.contains_bad(fixed_once) and gr.mentions_allowed_objects(fixed_once):
            fixed_once = gr.ensure_store_filter(fixed_once, store_id)
            fixed_once = gr.ensure_limit(fixed_once)
            replaced = gr.replace_current_date(fixed_once, data_end_date)
            if replaced:
                fixed_once = replaced
            cols, rows = dbx.run_sql(fixed_once)
            safe_sql = fixed_once
        else:
            # One-shot LLM repair with error context
            repair_messages = messages + [
                {"role": "assistant", "content": f"```sql\n{safe_sql}\n```"},
                {"role": "user", "content": f"Your SQL failed with error:\n{e}\nFix it and return ONLY corrected SQL in ```sql ...```."},
            ]
            # Use a fresh loop for the repair call
            repair_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(repair_loop)
                repaired, _ = repair_loop.run_until_complete(llm.try_models(repair_messages, winner_pref))
            finally:
                asyncio.set_event_loop(None)
                repair_loop.close()
            repaired_sql = gr.extract_sql(repaired["text"]) or ""
            if repaired_sql and gr.looks_select_only(repaired_sql) and not gr.contains_bad(repaired_sql) and gr.mentions_allowed_objects(repaired_sql):
                repaired_sql = gr.ensure_store_filter(repaired_sql, store_id)
                repaired_sql = gr.ensure_limit(repaired_sql)
                replaced = gr.replace_current_date(repaired_sql, data_end_date)
                if replaced:
                    repaired_sql = replaced
                cols, rows = dbx.run_sql(repaired_sql)
                safe_sql = repaired_sql
            else:
                raise

    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

    # Persist run metadata
    try:
        dbx.log_run({
            "user_id": user_id,
            "store_id": store_id,
            "question": question,
            "chosen_model": winner["model"],
            "latency_ms": winner["latency_ms"],
            "cost_usd": winner["cost_usd"],
            "trials": trials,
        })
    except Exception:
        # Logging failure shouldn't block the app
        pass

    return QueryResult(sql=safe_sql, df=df, trials=trials, winner=winner, data_end_date=data_end_date)
