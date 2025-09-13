from __future__ import annotations
import asyncio
import time
import httpx
import certifi

from retail_ai import settings
from retail_ai.domain.guardrails import grounding_score


def call_openrouter_sync(model_id: str, messages: list[dict], max_tokens: int = 500, temperature: float = 0.2):
    payload = {"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    backoffs = [0.4, 0.8, 1.6]
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
                    headers=settings.OR_HEADERS,
                    json=payload,
                )
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, httpx.ReadTimeout, httpx.ConnectError) as e:
                last_err = e
                if i < len(backoffs):
                    time.sleep(backoffs[i])
                else:
                    raise


async def _call_model(model, messages):
    t0 = time.perf_counter()
    data = await asyncio.to_thread(call_openrouter_sync, model["id"], messages, 500, 0.2)
    dt_ms = int((time.perf_counter() - t0) * 1000)

    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    pin = (usage.get("prompt_tokens") or 0) / 1000 * model["in"]
    pout = (usage.get("completion_tokens") or 0) / 1000 * model["out"]
    cost = round(pin + pout, 6)

    return {
        "model": model["id"],
        "text": text,
        "latency_ms": dt_ms,
        "usage": usage,
        "cost_usd": cost,
    }


async def try_models(messages, pref: str = "cheapest"):
    tasks = [_call_model(m, messages) for m in settings.MODELS]
    results = await asyncio.gather(*tasks)
    for r in results:
        r["score"] = grounding_score(r["text"])
    if pref == "fastest":
        sort_key = lambda x: (-x["score"], x["latency_ms"], x["cost_usd"])
    else:
        sort_key = lambda x: (-x["score"], x["cost_usd"], x["latency_ms"])
    winner = sorted(results, key=sort_key)[0]
    return winner, results

