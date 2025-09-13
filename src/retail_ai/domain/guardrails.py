from __future__ import annotations
import re
from functools import lru_cache

from retail_ai import settings


def extract_sql(text: str):
    m = re.search(r"```sql(.*?)```", text, flags=re.S | re.I)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"\bselect\b.*", text, flags=re.S | re.I)
    return m2.group(0).strip() if m2 else None


def looks_select_only(sql: str) -> bool:
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        return False
    if ";" in s:
        return False
    return True


def contains_bad(sql: str) -> bool:
    s = sql.lower()
    if ";--" in s:
        return True
    word_keywords = [kw for kw in settings.BAD_KEYWORDS if kw.isalpha()]
    pattern = r"\b(" + "|".join(map(re.escape, word_keywords)) + r")\b"
    if re.search(pattern, s):
        return True
    if re.search(r"\bcopy\b", s):
        return True
    return False


def mentions_allowed_objects(sql: str) -> bool:
    s = sql.lower()
    patterns = [r"\b" + re.escape(name.lower()) + r"\b" for name in (*settings.ALLOW_VIEWS, *settings.ALLOW_TABLES)]
    return any(re.search(p, s) for p in patterns)


def columns_exist(sql: str) -> tuple[bool, str | None]:
    low = sql.lower()
    alias_of: dict[str, str] = {}
    for obj in (*settings.ALLOW_VIEWS, *settings.ALLOW_TABLES):
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
        if col not in {c.lower() for c in settings.COLUMNS.get(obj, set())}:
            bad_refs.append(f"{alias}.{col} not in {obj}")
    if bad_refs:
        return False, "; ".join(sorted(set(bad_refs)))
    return True, None


def ensure_store_filter(sql: str, store_id: str) -> str:
    original = sql
    s_low = sql.lower()
    if re.search(r"\bstore_id\s*=\s*'[^']*'", s_low):
        return original
    alias = None
    m = re.search(r"\bfrom\s+v_sales_daily\s+(?:as\s+)?([a-zA-Z][a-zA-Z0-9_]*)", s_low)
    if not m:
        m = re.search(r"\bfrom\s+sales_transactions\s+(?:as\s+)?([a-zA-Z][a-zA-Z0-9_]*)", s_low)
    if m:
        alias = m.group(1)
    pred = f"{alias}.store_id = '{store_id}'" if alias else f"store_id = '{store_id}'"
    where_match = re.search(r"\bwhere\b", s_low)
    if where_match:
        insert_pos = where_match.end()
        tail = original[insert_pos:]
        prefix = original[:insert_pos]
        sep = "" if tail.startswith((" ", "\n", "\t")) else " "
        return prefix + f"{sep}{pred} AND (" + tail.lstrip() + ")"
    tail_kw = re.search(r"\b(group\s+by|having|order\s+by|limit)\b", s_low)
    if tail_kw:
        i = tail_kw.start()
        spacer = "" if original[:i].endswith((" ", "\n", "\t")) else " "
        return original[:i] + f"{spacer}WHERE {pred} " + original[i:]
    sep = "" if original.endswith((" ", "\n", "\t")) else " "
    return original + f"{sep}WHERE {pred}"


def ensure_limit(sql: str, default_limit: int = 200) -> str:
    """
    Ensure a LIMIT clause exists on the top-level query.
    - Detect any occurrence of LIMIT (robust, not relying on spaces/newlines/semicolons)
    - Avoid adding for obvious aggregates (heuristic)
    - Strip a trailing semicolon before appending to avoid "; LIMIT ..."
    """
    s = sql.rstrip()
    # If any LIMIT exists, do not add another
    if re.search(r"\blimit\b", s, flags=re.I):
        return s
    # Heuristic: skip LIMIT for aggregate-style queries
    if re.search(r"\bgroup\s+by\b|\bsum\s*\(|\bavg\s*\(|\bcount\s*\(|\bmax\s*\(|\bmin\s*\(", s, flags=re.I):
        return s
    # Remove trailing semicolon if present
    if s.endswith(";"):
        s = s[:-1].rstrip()
    return s + f" LIMIT {default_limit}"


def replace_current_date(sql: str, base_date: str | None) -> str:
    if not base_date:
        return sql
    s = sql
    s = re.sub(r"\bcurrent_date\b", f"'{base_date}'::date", s, flags=re.I)
    s = re.sub(r"\bnow\(\)", f"'{base_date}'::timestamp", s, flags=re.I)
    s = re.sub(r"\bcurrent_timestamp\b", f"'{base_date}'::timestamp", s, flags=re.I)
    s = re.sub(r"\bcurrent_timestamp\s*::\s*date\b", f"'{base_date}'::date", s, flags=re.I)
    s = re.sub(r"date_trunc\(\s*'day'\s*,\s*now\(\)\s*\)", f"'{base_date}'::timestamp", s, flags=re.I)
    return s if s != sql else None


def grounding_score(answer: str) -> int:
    sql = extract_sql(answer) or ""
    has_sql = bool(sql)
    ok_shape = looks_select_only(sql) if sql else False
    mentions = mentions_allowed_objects(sql) if sql else False
    return int(has_sql) + int(ok_shape) + int(mentions)


def repair_known_errors(sql: str, db_error_text: str) -> str | None:
    """
    Precision fixes for common alias/column mistakes without round-tripping to the LLM.
    Returns a new SQL string if a fix was applied, else None.
    """
    s = sql
    err = (db_error_text or "").lower()
    if "column s.promo_id does not exist" in err and re.search(r"\bv_promos_active\b.*\bpa\b", s, re.I | re.S):
        s2 = re.sub(r"\bcount\s*\(\s*distinct\s*s\.promo_id\s*\)", "COUNT(DISTINCT pa.promo_id)", s, flags=re.I)
        if s2 != s:
            s = s2
    if re.search(r"\bp\.brand\b", s, re.I) and re.search(r"\bv_sales_daily\b.*\bs\b", s, re.I | re.S):
        s2 = re.sub(r"\bp\.brand\b", "s.brand", s, flags=re.I)
        if s2 != s:
            s = s2
    return s if s != sql else None
