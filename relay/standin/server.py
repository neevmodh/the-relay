"""Stand-in for the model provider. OpenAI-compatible streaming /v1/chat/completions.

What it imitates (parameters in calib.json, fitted from raw/ measurements of the real service):
  - latency: time to first token = lognormal base + per-prompt-token cost, then a streamed reply
  - slowdown under load: latency multiplier grows with requests in flight
  - slow tail: a small share of requests are several times slower for no visible reason
  - failures: a small share of 5xx errors, and hangs (accepted, then silent past typical client timeouts)
  - limits: sliding-window tokens/min and requests/min, requests/day, max in flight; 429 with retry-after
    and the same x-ratelimit-* headers the real service sends
  - refusal: some answers are the refusal text, like a model that finds nothing in the passages
Admin: POST /admin/config {"tpm": 4000, "rpd": 20, "reset": true} changes limits without restart
(this is how "per-minute limit halved" and "daily budget exhausted" are run).
Least like the real thing: see writeup (output content is templated, no real reasoning delay structure,
a single process, no provider-side queueing).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import time
from collections import deque
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

CALIB = Path(__file__).with_name("calib.json")
DEFAULT = {
    "ttft_ms_median": 800, "ttft_sigma": 0.35, "ms_per_prompt_token": 0.12,
    "decode_tokens_per_s": 400, "stream_chunk_tokens": 4,
    "out_tokens_mean": 90, "out_tokens_sd": 40, "hidden_reasoning_tokens": 40,
    "chars_per_token": 3.6,
    "tail_prob": 0.04, "tail_mult": 4.0, "error_prob": 0.01, "hang_prob": 0.005, "hang_s": 60,
    "load_alpha": 0.15, "load_free_inflight": 2,
    "refusal_prob": 0.2, "tpm": 8000, "rpm": 30, "rpd": 1000, "max_inflight": 8,
}
cfg = {**DEFAULT, **(json.loads(CALIB.read_text()) if CALIB.exists() else {})}
app = FastAPI()
tok_win: deque = deque()   # (t, tokens)
req_win: deque = deque()   # t
state = {"day": 0, "inflight": 0}
rng = random.Random(7)


def trim(now: float) -> None:
    while tok_win and now - tok_win[0][0] >= 60:
        tok_win.popleft()
    while req_win and now - req_win[0] >= 60:
        req_win.popleft()


def headers(now: float) -> dict:
    trim(now)
    used_t = sum(t for _, t in tok_win)
    return {"x-ratelimit-limit-requests": str(cfg["rpd"]), "x-ratelimit-limit-tokens": str(cfg["tpm"]),
            "x-ratelimit-remaining-requests": str(max(0, cfg["rpd"] - state["day"])),
            "x-ratelimit-remaining-tokens": str(max(0, cfg["tpm"] - used_t))}


def limit_response(kind: str, retry_after: float, now: float):
    h = headers(now)
    h["retry-after"] = str(max(1, math.ceil(retry_after)))
    return JSONResponse({"error": {"message": f"Rate limit reached ({kind}). Please try again in {retry_after:.1f}s.",
                                   "type": "rate_limit_exceeded", "code": "rate_limit_exceeded"}},
                        status_code=429, headers=h)


@app.post("/admin/config")
async def admin(req: Request):
    body = await req.json()
    if body.pop("reset", False):
        tok_win.clear(); req_win.clear(); state["day"] = 0
    cfg.update(body)
    return cfg


@app.get("/admin/stats")
async def stats():
    return {"day": state["day"], "inflight": state["inflight"], "cfg": cfg}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    now = time.monotonic()
    body = await req.json()
    prompt_chars = sum(len(m.get("content", "")) for m in body["messages"])
    tin = int(prompt_chars / cfg["chars_per_token"])
    max_out = int(body.get("max_tokens", 400))
    refuse = rng.random() < cfg["refusal_prob"]
    tout = 12 if refuse else max(5, min(max_out, int(rng.gauss(cfg["out_tokens_mean"], cfg["out_tokens_sd"]))))
    charged = tin + tout + int(cfg["hidden_reasoning_tokens"])

    trim(now)
    if state["day"] >= cfg["rpd"]:
        return limit_response("requests per day (RPD)", 3600, now)
    if len(req_win) >= cfg["rpm"]:
        return limit_response("requests per minute (RPM)", req_win[0] + 60 - now, now)
    used = sum(t for _, t in tok_win)
    if used + charged > cfg["tpm"]:
        need, ra = used + charged - cfg["tpm"], 0.0
        for t0, tk in tok_win:
            need -= tk
            ra = t0 + 60 - now
            if need <= 0:
                break
        return limit_response("tokens per minute (TPM)", max(ra, 0.5), now)
    if state["inflight"] >= cfg["max_inflight"]:
        return limit_response("concurrent requests", 1.0, now)

    tok_win.append((now, charged)); req_win.append(now); state["day"] += 1
    state["inflight"] += 1
    h = headers(now)

    async def gen():
        try:
            load = 1 + cfg["load_alpha"] * max(0, state["inflight"] - cfg["load_free_inflight"])
            ttft = cfg["ttft_ms_median"] * math.exp(rng.gauss(0, cfg["ttft_sigma"])) + cfg["ms_per_prompt_token"] * tin
            if rng.random() < cfg["tail_prob"]:
                ttft *= cfg["tail_mult"]
            ttft *= load
            if rng.random() < cfg["hang_prob"]:
                await asyncio.sleep(cfg["hang_s"])
            await asyncio.sleep(ttft / 1000)
            text = "The papers in this library do not say." if refuse else \
                "According to the passages, the answer is stated in the cited text [1][2]. " * 3
            words = text.split(" ")[:max(1, int(tout * 0.75))]
            step = max(1, int(cfg["stream_chunk_tokens"] * 0.75))
            for i in range(0, len(words), step):
                piece = " ".join(words[i:i + step]) + " "
                yield "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n"
                await asyncio.sleep(cfg["stream_chunk_tokens"] / cfg["decode_tokens_per_s"] * load)
            yield "data: " + json.dumps({"choices": [], "x_groq": {"usage": {"prompt_tokens": tin, "completion_tokens": tout}}}) + "\n\n"
            yield "data: [DONE]\n\n"
        finally:
            state["inflight"] -= 1

    if rng.random() < cfg["error_prob"]:
        state["inflight"] -= 1
        return JSONResponse({"error": {"message": "internal error"}}, status_code=503, headers=h)
    return StreamingResponse(gen(), media_type="text/event-stream", headers=h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    uvicorn.run(app, host="127.0.0.1", port=ap.parse_args().port, log_level="warning")
