# =========================

# UI

# =========================

st.title("🛒 Retail Assistant — ERD-aware SQL")
with st.sidebar:
store\_id = st.text\_input("Store ID", value="S001")
user\_id  = st.text\_input("User (for logs)", value="demo\_user")
st.caption("Interpreting vague time ranges as last 7 days • TZ: Australia/Melbourne • Promo week: Wed→Tue")
st.caption("Examples: 'How much did article A1001 sell in last promo?' • 'Top 5 products by revenue last 7 days'")

question = st.text\_input("Ask a question")

if st.button("Ask") and question.strip():
\# Optional: semantic cache lookup (placeholder)
\_cached = cache\_lookup(store\_id, question)
if \_cached:
st.info("Served from cache.")
st.dataframe(pd.read\_json(\_cached\[1]), use\_container\_width=True)

````
with st.spinner("Thinking..."):
    messages = build_messages(store_id, question)
    winner, trials = asyncio.run(try_models(messages))
    sql = extract_sql(winner["text"])

# Soft budget info
total_est_cost = sum(t["cost_usd"] for t in trials)
if total_est_cost > SOFT_COST_BUDGET:
    st.warning(f"Estimated combined model cost ${total_est_cost:.4f} exceeds soft budget ${SOFT_COST_BUDGET:.2f}.")

st.subheader("Chosen model & answer")
st.write(f"**Model:** `{winner['model']}` • **Latency:** {winner['latency_ms']} ms • **Est. cost:** ${winner['cost_usd']:.4f}")

if not sql:
    st.error("No SQL found in the model's answer.")
else:
    # Validate & harden
    err = None
    if not looks_select_only(sql): err = "SQL is not SELECT-only."
    elif contains_bad(sql):        err = "Blocked keyword in SQL."
    elif not mentions_allowed_objects(sql): err = "SQL references objects outside allowed views/tables."

    if err:
        st.error(err)
    else:
        safe_sql = ensure_store_filter(sql, store_id)
        safe_sql = ensure_limit(safe_sql)

        st.markdown("**SQL used:**")
        st.code(safe_sql, language="sql")

        # Execute, with a single self-repair attempt on error
        try:
            cols, rows = run_sql(safe_sql)
        except Exception as e:
            # Repair loop
            repair_messages = messages + [
                {"role":"assistant","content":f"```sql\n{safe_sql}\n```"},
                {"role":"user","content":f"Your SQL failed with error:\n{e}\nFix it and return ONLY corrected SQL in ```sql ...```."}
            ]
            repaired, _ = asyncio.run(try_models(repair_messages))
            repaired_sql = extract_sql(repaired["text"])
            if repaired_sql and looks_select_only(repaired_sql) and not contains_bad(repaired_sql) and mentions_allowed_objects(repaired_sql):
                repaired_sql = ensure_store_filter(repaired_sql, store_id)
                repaired_sql = ensure_limit(repaired_sql)
                st.info("Auto-repaired the query once based on the DB error.")
                st.code(repaired_sql, language="sql")
                cols, rows = run_sql(repaired_sql)
                safe_sql = repaired_sql
            else:
                st.error(f"SQL error: {e}")
                log_run({
                    "user_id": user_id, "store_id": store_id, "question": question,
                    "chosen_model": winner["model"], "latency_ms": winner["latency_ms"],
                    "cost_usd": winner["cost_usd"], "trials": trials
                })
                st.stop()

        # Display results
        if rows:
            df = pd.DataFrame(rows, columns=cols)
            st.dataframe(df, use_container_width=True)
            num_cols = df.select_dtypes(include=["int64","float64"]).columns.tolist()
            if num_cols:
                st.bar_chart(df[num_cols[0]])
            # (Optional) cache_store(store_id, question, safe_sql, df)
        else:
            st.info("Query returned 0 rows.")

st.divider()
st.subheader("Model trials (debug)")
# Include tokens for observability
trials_pretty = []
for t in trials:
    usage = t.get("usage", {}) or {}
    trials_pretty.append({
        "model": t["model"],
        "latency_ms": t["latency_ms"],
        "cost_usd": t["cost_usd"],
        "score": t.get("score"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    })
st.json(trials_pretty)

# Persist run
log_run({
    "user_id": user_id, "store_id": store_id, "question": question,
    "chosen_model": winner["model"], "latency_ms": winner["latency_ms"],
    "cost_usd": winner["cost_usd"], "trials": trials
})
````

````

---

## How to add more models
1) Find the model IDs on OpenRouter (Dashboard → Models), e.g.:
   - `openrouter/openai/gpt-4o-mini`
   - `openrouter/anthropic/claude-3.5-sonnet`
   - `google/gemini-1.5-pro`
   - `qwen/qwen2.5-72b-instruct`  
2) Add entries to the `MODELS` list with their **per-1k token prices** (USD). Example:

```python
MODELS = [
    {"id": "openrouter/openai/gpt-4o-mini",           "in": 0.0006, "out": 0.0024},
    {"id": "openrouter/anthropic/claude-3.5-sonnet",  "in": 0.0030, "out": 0.0150},
    {"id": "google/gemini-1.5-pro",                   "in": 0.0015, "out": 0.0050},
    {"id": "qwen/qwen2.5-72b-instruct",               "in": 0.0001, "out": 0.0002},
]
````

