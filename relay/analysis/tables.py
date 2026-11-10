"""Recompute Tables 2a, 2b and 3 from raw/results.csv (+ raw/scenarios.jsonl for duration/offered rate/peak queue).

Nothing here is typed in by hand. Percentiles: numpy 'linear' interpolation over requests that have the value
(first-token percentiles use requests that produced a first token; total-time percentiles use all requests,
including those that gave up, because the person waited that long).
Cost: NOTIONAL list price (free tier costs nothing): PRICE_IN / PRICE_OUT per million tokens.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[2] / "raw"
PRICE_IN, PRICE_OUT = 0.075, 0.30      # USD per 1M tokens, gpt-oss-20b list price (assumption, see write-up)


def pct(s: pd.Series, qs=(50, 95, 99)) -> str:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return "not measured"
    return " / ".join(f"{np.percentile(s, q):.0f}" for q in qs)


def load():
    df = pd.read_csv(RAW / "results.csv")
    sc = [json.loads(l) for l in (RAW / "scenarios.jsonl").open()]
    return df, {s["scenario"]: s for s in sc}


def table2(df, sc):
    a, b = [], []
    for name, g in df.groupby("scenario", sort=False):
        if name in ("steady_v0", "sweep_C", "sweep_D") or name not in sc:  # Table 3 rows
            continue
        label = "steady (= sweep_A)" if name == "sweep_A" else name
        s, n = sc[name], len(g)
        a.append(f"| {label} | {g.source.iloc[0]} | {n} | {s['duration_s']:.1f} | {s['offered_per_min']:.1f} | "
                 f"{pct(g.first_token_ms)} | {pct(g.total_ms)} |")
        ok = g[g.status == "ok"]
        model_calls = g[(g.tokens_in > 0)]
        tpa = (model_calls.tokens_in + model_calls.tokens_out).mean() if len(model_calls) else float("nan")
        cost = (model_calls.tokens_in.mean() * PRICE_IN + model_calls.tokens_out.mean() * PRICE_OUT) / 1e6 * 1000 \
            if len(model_calls) else float("nan")
        p = lambda m: f"{100 * m.mean():.1f}"
        b.append(f"| {label} | {p(g.status == 'ok')} | {p(g.status == 'rate_limited')} | "
                 f"{p(g.status.isin(['timeout', 'error']))} | {g.retries.mean():.2f} | {s['peak_queue']} | "
                 f"{tpa:.0f} | {cost:.3f} |")
    h2a = ("| Scenario | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | "
           "First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |\n|---|---|---|---|---|---|---|")
    h2b = ("| Scenario | Succeeded % | Rate-limited % | Timed out or given up % | Retries per request | "
           "Peak queue length | Tokens per answer | Cost per 1,000 answers (USD, notional) |\n|---|---|---|---|---|---|---|---|")
    return h2a + "\n" + "\n".join(a), h2b + "\n" + "\n".join(b)


def table3(df):
    rows = []
    for name, g in df[df.scenario.str.startswith("sweep_") | (df.scenario == "steady_v0")].groupby("retrieval_setting"):
        g = g[g.source == "real"]
        graded = g[g.answer_grade.notna()]
        n = len(graded)
        if n == 0:
            continue
        p = lambda k: f"{100 * (graded.answer_grade == k).mean():.1f}"
        used = g[g.tokens_in > 0]
        rows.append(f"| {name} | {n} | {p('correct')} | {p('wrong')} | {p('refused_correctly')} | "
                    f"{(used.tokens_in + used.tokens_out).mean():.0f} | {pct(g.first_token_ms, (50, 95))} | "
                    f"{pct(g.total_ms, (50, 95))} |")
    h = ("| Setting (piece size, pieces fetched, re-rank) | Questions asked | Correct and cited % | Wrong % | "
         "Correctly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |\n"
         "|---|---|---|---|---|---|---|---|")
    return h + "\n" + "\n".join(rows)


if __name__ == "__main__":
    df, sc = load()
    t2a, t2b = table2(df, sc)
    out = f"## Table 2a\n\n{t2a}\n\n## Table 2b\n\n{t2b}\n\n## Table 3\n\n{table3(df)}\n"
    (Path(__file__).resolve().parents[2] / "writeup" / "tables.md").write_text(out)
    print(out)
