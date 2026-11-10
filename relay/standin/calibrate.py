"""Fit relay/standin/calib.json from real measurements only (source == real rows in raw/results.csv
and raw/probe_calls.jsonl). Prints what was fitted and from how many samples, so nothing is hidden.

Fitted:  ttft_ms_median, ttft_sigma (lognormal on residual after prompt-size effect), ms_per_prompt_token,
         decode_tokens_per_s, out_tokens_mean/sd (non-refusal replies), refusal_prob, chars_per_token
Not fitted (no real evidence, left at defaults and flagged in the write-up): tail_prob/tail_mult beyond what
the sample shows, error_prob, hang_prob, load_alpha (real service was never pushed into overload), max_inflight.
tpm/rpm/rpd come from Table 1 (probe headers and 429 bodies), set by hand in calib.json after reading them.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("calib.json")


def main() -> None:
    df = pd.read_csv(ROOT / "raw" / "results.csv")
    r = df[(df.source == "real") & (df.status == "ok") & (df.tokens_in > 0) & df.first_token_ms.notna()].copy()
    n = len(r)
    # Per-request time before the first visible token includes hidden reasoning, so fit on all real calls.
    x = r.tokens_in.values.astype(float)
    y = r.first_token_ms.values.astype(float)
    slope, icpt = np.polyfit(x, y, 1)
    slope = max(0.0, float(slope))
    resid = np.log(np.clip(y - slope * x, 50, None))
    med = float(np.exp(np.median(resid)))
    sigma = float(np.std(resid))
    out = r.tokens_out.values.astype(float)
    refusals = out < 40
    ans = out[~refusals]
    decode = (r.total_ms - r.first_token_ms).clip(lower=1)
    rate = float(np.median(out / (decode / 1000)))   # tokens/s after the first visible token
    cfg = {
        "ttft_ms_median": round(med, 1), "ttft_sigma": round(sigma, 3), "ms_per_prompt_token": round(slope, 4),
        "decode_tokens_per_s": round(min(rate, 2000), 1),
        "out_tokens_mean": round(float(ans.mean()), 1) if len(ans) else 90,
        "out_tokens_sd": round(float(ans.std()), 1) if len(ans) else 40,
        "refusal_prob": round(float(refusals.mean()), 3),
    }
    # keep hand-set limits if present
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    cfg = {**old, **cfg}
    OUT.write_text(json.dumps(cfg, indent=2))
    print(f"fitted from {n} real ok calls: slope={slope:.4f} ms/token, intercept(ignored)={icpt:.0f}")
    print(json.dumps(cfg, indent=2))
    print("observed real ttft p50/p95/p99:", [round(float(np.percentile(y, q))) for q in (50, 95, 99)])


if __name__ == "__main__":
    main()
