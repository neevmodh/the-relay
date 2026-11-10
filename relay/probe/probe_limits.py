"""Probe the real Groq service. Cheap, staged, and logged. Fills Table 1.

Every call is appended to raw/probe_calls.jsonl (all rate-limit headers kept) and to
raw/budget_ledger.csv so the shared daily quota is accounted for.

Stages (run one at a time, read output between them):
  headers   1 request: dump every response header, see what the service tells us
  latency   N sequential requests: latency spread, no limits touched
  burst     fire K concurrent requests: finds in-flight/RPM behaviour; stops at first 429,
            then polls with 1 request every few seconds to time recovery
Usage: python -m relay.probe.probe_limits headers|latency N|burst K
Stays inside the provider's terms: one account, one key, no tricks.
"""
from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from pathlib import Path

import httpx

from relay.pipeline.client import MODEL, stream_chat

RAW = Path(__file__).resolve().parents[2] / "raw"
MSGS = [{"role": "user", "content": "Reply with the single word: ok"}]


def log(stage: str, res, extra: dict | None = None) -> None:
    RAW.mkdir(exist_ok=True)
    row = {"t": time.time(), "stage": stage, "model": MODEL, "status": res.status, "http": res.http,
           "first_token_ms": res.first_token_ms, "total_ms": res.total_ms, "tokens_in": res.tokens_in,
           "tokens_out": res.tokens_out, "retry_after_s": res.retry_after_s, "headers": res.headers,
           "error": res.error, **(extra or {})}
    with (RAW / "probe_calls.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    led = RAW / "budget_ledger.csv"
    new = not led.exists()
    with led.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["t", "stage", "status", "tokens_in", "tokens_out"])
        w.writerow([row["t"], stage, res.status, res.tokens_in, res.tokens_out])


async def one(c, stage, **kw):
    r = await stream_chat(c, MSGS, max_tokens=60, timeout_s=30, **kw)
    log(stage, r)
    return r


async def headers():
    async with httpx.AsyncClient() as c:
        r = await one(c, "headers")
    print(r.status, r.http, r.headers, r.error)


async def latency(n: int):
    async with httpx.AsyncClient() as c:
        for i in range(n):
            r = await one(c, "latency")
            print(i, r.status, f"ttft={r.first_token_ms and round(r.first_token_ms)} total={round(r.total_ms)}",
                  r.headers.get("x-ratelimit-remaining-requests"), r.headers.get("x-ratelimit-remaining-tokens"))
            if r.status == "rate_limited":
                print("hit a limit during latency stage; stopping:", r.error, r.headers)
                break


async def burst(k: int):
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=k)) as c:
        t0 = time.time()
        rs = await asyncio.gather(*[one(c, "burst") for _ in range(k)])
        ok = sum(r.status == "ok" for r in rs)
        rl = [r for r in rs if r.status == "rate_limited"]
        print(f"burst {k}: ok={ok} rate_limited={len(rl)} other={k - ok - len(rl)}")
        if not rl:
            return
        print("first 429 body:", rl[0].error, "| headers:", rl[0].headers)
        print("polling for recovery (1 request / 3s, max 90s)...")
        t_hit = time.time()
        while time.time() - t_hit < 90:
            await asyncio.sleep(3)
            r = await one(c, "recovery")
            if r.status == "ok":
                print(f"recovered after ~{time.time() - t_hit:.0f}s")
                return
        print("did not recover within 90s")


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage == "headers":
        asyncio.run(headers())
    elif stage == "latency":
        asyncio.run(latency(int(sys.argv[2])))
    elif stage == "burst":
        asyncio.run(burst(int(sys.argv[2])))
