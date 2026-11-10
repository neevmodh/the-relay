"""The pipeline: retrieve (tool) -> [limiter] -> generate (stream) -> verify.

Branch: weak retrieval        -> refuse without spending a model call.
Branch: daily budget gone     -> no model call; return the retrieved passages with a notice.
Branch: high pressure         -> smaller context, shorter answer, no regeneration.
Loop:   verify fails          -> one regeneration with more passages (normal pressure only).
Retry:  429/timeout/5xx       -> bounded, honors retry-after, never waits past the caller's deadline.
All times are measured from request arrival, so queue waiting counts as the user's waiting.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
import unicodedata
from dataclasses import dataclass, field

import httpx

from .client import CallResult, stream_chat
from .retrieve import Setting, coverage, retrieve
from .sched import Limiter

REFUSAL = "The papers in this library do not say."
MIN_COVERAGE = 0.35   # lowered from 0.5: q05 (answerable, cov 0.43) was being refused. Only blocks clear off-topic.

SYSTEM = (
    "You answer questions using ONLY the numbered passages. Cite every claim as [n] using the passage "
    "numbers. If the passages do not contain the answer, reply exactly: " + REFUSAL +
    " Be concise (at most 4 sentences). Passages come from specific paper versions; do not use outside knowledge."
)


@dataclass
class Policy:
    name: str = "careful"
    use_limiter: bool = True
    max_retries: int = 2
    backoff: bool = True          # False = naive: retry immediately, ignore retry-after
    degrade: bool = True
    patience_s: float = 8.0       # longest a request may wait for a slot before it is turned away


@dataclass
class Outcome:
    answer: str = ""
    status: str = "error"            # ok | rate_limited | timeout | error
    kind: str = ""                   # answered | refused | fallback | shed | failed
    first_token_ms: float | None = None
    total_ms: float = 0.0
    retries: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    setting: str = ""
    degraded: bool = False
    queue_ms: float = 0.0            # waiting for the limiter
    backoff_ms: float = 0.0          # sleeping between retries
    work_ms: float = 0.0             # time inside provider attempts that succeeded
    wasted_ms: float = 0.0           # time inside provider attempts that failed
    citations: list[str] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)


def build_prompt(question: str, hits) -> list[dict]:
    ctx = "\n\n".join(f"[{i}] ({c.cite})\n{c.text}" for i, (c, _) in enumerate(hits, 1))
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {question}"}]


def normalize(text: str) -> str:
    """The model sometimes writes citations as 【1】 and uses non-breaking spaces/hyphens. Make them plain."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[【\[]\s*(\d+)\s*[】\]]", r"[\1]", text)
    return text.replace("\u2011", "-")


def verify(answer: str, n_hits: int) -> bool:
    """Programmatic check: a non-refusal answer must cite, and only existing passage numbers."""
    if answer.strip().startswith(REFUSAL[:30]):
        return True
    nums = [int(x) for x in re.findall(r"\[(\d+)\]", answer)]
    return bool(nums) and all(1 <= n <= n_hits for n in nums)


def est_tokens(messages: list[dict], max_tokens: int) -> int:
    return int(sum(len(m["content"]) for m in messages) / 3.6) + int(max_tokens * 0.6)


def fallback_text(hits) -> str:
    lines = ["Today's model capacity is used up, so here are the most relevant passages instead of a written answer:"]
    for i, (c, _) in enumerate(hits[:3], 1):
        lines.append(f"[{i}] {c.cite}: {c.text[:300]}...")
    return "\n".join(lines)


async def answer_question(client: httpx.AsyncClient, question: str, setting: Setting = Setting(),
                          *, limiter: Limiter | None = None, policy: Policy = Policy(),
                          deadline_s: float = 20.0) -> Outcome:
    t0 = time.perf_counter()
    deadline = time.monotonic() + deadline_s
    out = Outcome(setting=setting.name)
    lim = limiter if (limiter is not None and policy.use_limiter) else None

    def done(status: str, kind: str) -> Outcome:
        out.status, out.kind = status, kind
        out.total_ms = (time.perf_counter() - t0) * 1000
        return out

    hits = retrieve(question, setting)                                       # tool step
    if not hits or max(coverage(question, c, setting.v2) for c, _ in hits) < MIN_COVERAGE:
        out.answer = REFUSAL
        return done("ok", "refused")

    if lim is not None and lim.daily_exhausted():
        out.answer = fallback_text(hits)
        out.citations = [c.cite for c, _ in hits[:3]]
        return done("rate_limited", "fallback")

    max_tokens = 400
    for round_ in range(2):
        msgs = build_prompt(question, hits)
        if lim is not None and policy.degrade and round_ == 0:
            if lim.pressure(est_tokens(msgs, max_tokens), deadline - time.monotonic()) == "high":
                small = Setting(setting.size, setting.overlap, max(2, setting.k - 2), setting.rerank, setting.v2)
                hits, max_tokens, out.degraded = retrieve(question, small), 250, True
                msgs = build_prompt(question, hits)

        res: CallResult | None = None
        ta = time.perf_counter()
        for attempt in range(policy.max_retries + 1):
            reserved = None
            if lim is not None:
                tq = time.monotonic()
                reserved = await lim.acquire(est_tokens(msgs, max_tokens), deadline, policy.patience_s)
                out.queue_ms += (time.monotonic() - tq) * 1000
                if reserved is None:                                         # cannot start in time: fail fast
                    if out.answer:                                           # regeneration only: keep first answer
                        break
                    return done("timeout", "shed")
            ta = time.perf_counter()
            res = await stream_chat(client, msgs, max_tokens=max_tokens,
                                    timeout_s=max(1.0, deadline - time.monotonic()))
            if lim is not None:
                lim.release(reserved, (res.tokens_in + res.tokens_out) if res.status == "ok" else 0)
                if res.status == "rate_limited":
                    if "requests per day" in res.error or res.headers.get("x-ratelimit-remaining-requests") == "0":
                        lim.day_used = lim.rpd                                # daily budget really is gone: stop calling
                    else:
                        lim.on_429()
            ms = (time.perf_counter() - ta) * 1000
            out.attempts.append({"status": res.status, "http": res.http, "ms": round(ms, 1),
                                 "ttft_ms": res.first_token_ms, "retry_after_s": res.retry_after_s,
                                 "err": res.error[:300], "hdr": res.headers, "t_rel_ms": round((ta - t0) * 1000, 1)})
            if res.status == "ok":
                out.work_ms += ms
                break
            out.wasted_ms += ms
            if attempt == policy.max_retries:
                break
            if policy.backoff:
                base = res.retry_after_s if res.retry_after_s is not None else 0.5 * 2 ** attempt
                wait = base + random.uniform(0, 0.25 * base + 0.1)
            else:
                wait = 0.0
            if time.monotonic() + wait >= deadline:                          # waiting would blow the deadline
                break
            out.retries += 1
            out.backoff_ms += wait * 1000
            await asyncio.sleep(wait)

        if res is None:                                                      # regeneration could not start
            break
        out.tokens_in += res.tokens_in
        out.tokens_out += res.tokens_out
        if res.status == "rate_limited" and lim is not None and lim.daily_exhausted() and not out.answer:
            out.answer = fallback_text(hits)
            out.citations = [c.cite for c, _ in hits[:3]]
            return done("rate_limited", "fallback")
        if res.status != "ok":
            if out.answer:                                                   # regeneration failed: first answer stands
                break
            return done(res.status, "failed")
        if res.first_token_ms is not None:
            out.first_token_ms = (ta - t0) * 1000 + res.first_token_ms       # from arrival, incl. queue + retries
        out.answer = normalize(res.text)
        if verify(out.answer, len(hits)) or out.degraded:
            break
        hits = retrieve(question, Setting(setting.size, setting.overlap, setting.k + 2, setting.rerank, setting.v2))

    out.citations = [c.cite for c, _ in hits]
    return done("ok", "refused" if out.answer.startswith(REFUSAL[:30]) else "answered")
