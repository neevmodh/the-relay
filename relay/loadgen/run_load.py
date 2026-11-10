"""Run one load scenario and append rows to raw/results.csv.

  python -m relay.loadgen.run_load --scenario steady_real --source real --shape steady --rate 5 --n 23
Shapes: steady (rate/min, n requests) | burst (n at once) | overload (rate/min for --duration s)
The same code path serves real and stand-in; only LLM_BASE_URL differs.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import time
from pathlib import Path

import httpx

from relay.eval.grade import QS, grade
from relay.pipeline.retrieve import Setting
from relay.pipeline.run import Policy, answer_question
from relay.pipeline.sched import Limiter

import os
RAW = Path(os.getenv("RELAY_RAW") or Path(__file__).resolve().parents[2] / "raw")
COLS = ["request_id", "scenario", "source", "start_time", "first_token_ms", "total_ms", "status", "retries",
        "tokens_in", "tokens_out", "retrieval_setting", "answer_grade"]


def arrivals(shape: str, rate: float, n: int, duration: float) -> list[float]:
    if shape == "burst":
        return [i * 0.02 for i in range(n)]
    if shape == "steady":
        return [i * 60.0 / rate for i in range(n)]
    if shape == "overload":
        n = int(rate * duration / 60)
        return [i * 60.0 / rate for i in range(n)]
    raise SystemExit(f"unknown shape {shape}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--source", choices=["real", "stand-in"], required=True)
    ap.add_argument("--shape", choices=["steady", "burst", "overload"], required=True)
    ap.add_argument("--rate", type=float, default=5.0, help="requests/min offered")
    ap.add_argument("--n", type=int, default=23)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--size", type=int, default=200)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--rerank", type=int, default=0)
    ap.add_argument("--stem", type=int, default=0)
    ap.add_argument("--deadline", type=float, default=20.0)
    ap.add_argument("--policy", choices=["careful", "naive"], default="careful")
    ap.add_argument("--tpm", type=int, default=8000)
    ap.add_argument("--rpm", type=int, default=30)
    ap.add_argument("--rpd", type=int, default=1000)
    ap.add_argument("--patience", type=float, default=8.0)
    ap.add_argument("--max-inflight", type=int, default=4)
    ap.add_argument("--qids", default="", help="comma list; default = all, cycled")
    ap.add_argument("--max-real", type=int, default=60, help="safety cap on real requests in this run")
    a = ap.parse_args()

    qids = a.qids.split(",") if a.qids else list(QS)
    offs = arrivals(a.shape, a.rate, a.n, a.duration)
    if a.source == "real" and len(offs) > a.max_real:
        raise SystemExit(f"{len(offs)} requests exceeds --max-real {a.max_real}; refusing to spend the real quota")
    setting = Setting(a.size, 40, a.k, bool(a.rerank), bool(a.stem))
    pol = Policy(a.policy, use_limiter=a.policy == "careful", max_retries=2 if a.policy == "careful" else 3,
                 backoff=a.policy == "careful", degrade=a.policy == "careful", patience_s=a.patience)
    lim = Limiter(a.tpm, a.rpm, a.rpd, a.max_inflight)
    RAW.mkdir(exist_ok=True)
    rows, details = [], []

    async def one(i: int, off: float, client) -> None:
        await asyncio.sleep(off)
        qid = qids[i % len(qids)]
        start = time.time()
        o = await answer_question(client, QS[qid]["question"], setting, limiter=lim, policy=pol,
                                  deadline_s=a.deadline)
        rows.append({"request_id": f"{a.scenario}-{i:04d}", "scenario": a.scenario, "source": a.source,
                     "start_time": dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat(timespec="milliseconds"),
                     "first_token_ms": "" if o.first_token_ms is None else round(o.first_token_ms, 1),
                     "total_ms": round(o.total_ms, 1), "status": o.status, "retries": o.retries,
                     "tokens_in": o.tokens_in, "tokens_out": o.tokens_out, "retrieval_setting": o.setting,
                     "answer_grade": grade(qid, o.answer, o.kind)})
        details.append({"request_id": rows[-1]["request_id"], "qid": qid, "kind": o.kind, "degraded": o.degraded,
                        "queue_ms": round(o.queue_ms, 1), "backoff_ms": round(o.backoff_ms, 1),
                        "work_ms": round(o.work_ms, 1), "wasted_ms": round(o.wasted_ms, 1),
                        "attempts": o.attempts, "answer": o.answer[:600], "citations": o.citations})

    t0 = time.time()
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=200)) as client:
        await asyncio.gather(*[one(i, off, client) for i, off in enumerate(offs)])
    dur = time.time() - t0

    path = RAW / "results.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, COLS)
        if new:
            w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["request_id"]))
    with (RAW / "details.jsonl").open("a") as f:
        for d in sorted(details, key=lambda d: d["request_id"]):
            f.write(json.dumps(d) + "\n")
    with (RAW / "scenarios.jsonl").open("a") as f:
        f.write(json.dumps({"scenario": a.scenario, "source": a.source, "shape": a.shape, "requests": len(rows),
                            "duration_s": round(dur, 1), "offered_per_min": round(len(offs) / max(offs[-1], 1e-9) * 60, 1) if a.shape != "burst" else round(len(offs) / (dur / 60), 1),
                            "peak_queue": lim.peak_waiting, "policy": a.policy, "patience_s": a.patience, "tpm": a.tpm, "rpm": a.rpm,
                            "rpd": a.rpd, "deadline_s": a.deadline, "setting": setting.name}) + "\n")
    ok = sum(r["status"] == "ok" for r in rows)
    print(f"{a.scenario}: {len(rows)} requests in {dur:.0f}s, ok={ok}, peak_queue={lim.peak_waiting}")
    from collections import Counter
    print("status", dict(Counter(r["status"] for r in rows)), "grade", dict(Counter(r["answer_grade"] for r in rows)))


if __name__ == "__main__":
    asyncio.run(main())
