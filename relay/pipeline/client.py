"""Streaming chat client for an OpenAI-compatible endpoint (Groq or the stand-in).

One call = one attempt. No retries here: retry policy lives in run.py so every
attempt is visible and countable. Records timing and the rate-limit headers.
"""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")


@dataclass
class CallResult:
    status: str                      # ok | rate_limited | timeout | error
    http: int = 0
    text: str = ""
    first_token_ms: float | None = None
    total_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    retry_after_s: float | None = None
    headers: dict = field(default_factory=dict)
    error: str = ""


RL_HEADERS = ("retry-after", "x-ratelimit-limit-requests", "x-ratelimit-limit-tokens",
              "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens",
              "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens", "x-request-id")


async def stream_chat(client: httpx.AsyncClient, messages: list[dict], *, max_tokens: int = 400,
                      timeout_s: float = 30.0, model: str = MODEL, temperature: float = 0.0) -> CallResult:
    key = os.getenv("GROQ_API_KEY", "")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "stream": True}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"   # reasoning tokens count against max_tokens and the TPM limit
    t0 = time.perf_counter()
    r = CallResult(status="error")
    try:
        async with client.stream("POST", f"{BASE_URL}/chat/completions", json=body,
                                 headers={"Authorization": f"Bearer {key}"},
                                 timeout=httpx.Timeout(timeout_s, connect=10.0)) as resp:
            r.http = resp.status_code
            r.headers = {h: resp.headers[h] for h in RL_HEADERS if h in resp.headers}
            if resp.status_code == 429:
                await resp.aread()
                r.status = "rate_limited"
                ra = resp.headers.get("retry-after")
                r.retry_after_s = float(ra) if ra else None
                r.error = resp.text[:300]
            elif resp.status_code != 200:
                await resp.aread()
                r.error = resp.text[:300]
            else:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    ev = json.loads(payload)
                    usage = ev.get("usage") or ev.get("x_groq", {}).get("usage")
                    if usage:
                        r.tokens_in = usage.get("prompt_tokens", 0)
                        r.tokens_out = usage.get("completion_tokens", 0)
                    for ch in ev.get("choices", []):
                        piece = ch.get("delta", {}).get("content")
                        if piece:
                            if r.first_token_ms is None:
                                r.first_token_ms = (time.perf_counter() - t0) * 1000
                            r.text += piece
                r.status = "ok"
    except httpx.TimeoutException:
        r.status = "timeout"
    except httpx.HTTPError as e:
        r.status, r.error = "error", repr(e)[:200]
    r.total_ms = (time.perf_counter() - t0) * 1000
    return r
