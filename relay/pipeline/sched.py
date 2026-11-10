"""Admission control for the shared provider limits.

One Limiter per process. It keeps sliding 60 s windows of tokens and requests, a cap on requests
in flight, and a daily request counter. Requests are served FIFO. A request that cannot start
before its deadline gives up at once (fail fast) instead of waiting to time out.

Policy under pressure (decided here, executed in run.py):
  - normal: full context, one regeneration allowed if verification fails.
  - high pressure (queue building or projected wait is a big share of the deadline): smaller context,
    shorter answer, no regeneration. Quality drops before anybody is turned away.
  - daily budget gone: no model call; reply with the retrieved passages and a clear notice.
The limiter learns downward: a 429 shrinks its belief about the per-minute limit, which then
recovers slowly. This matters because the real limits can change without notice.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque


class Limiter:
    def __init__(self, tpm: int = 8000, rpm: int = 30, rpd: int = 1000, max_inflight: int = 4,
                 headroom: float = 0.9):
        self.tpm, self.rpm, self.rpd = tpm, rpm, rpd
        self.headroom = headroom
        self.scale = 1.0                       # learned shrink factor after 429s
        self.day_used = 0
        self.tok: deque = deque()              # (t, tokens)
        self.req: deque = deque()              # t
        self.inflight = 0
        self.max_inflight = max_inflight
        self.waiting = 0
        self.pending = 0                       # estimated tokens of requests waiting for a slot
        self.peak_waiting = 0
        self._lock = asyncio.Lock()            # FIFO ticket
        self._last_shrink = 0.0

    # ---- state ----
    def _trim(self, now: float) -> None:
        while self.tok and now - self.tok[0][0] >= 60:
            self.tok.popleft()
        while self.req and now - self.req[0] >= 60:
            self.req.popleft()

    def daily_exhausted(self) -> bool:
        return self.day_used >= self.rpd

    def _wait_needed(self, est: int, now: float) -> float:
        self._trim(now)
        cap_t = self.tpm * self.scale * self.headroom
        cap_r = max(1, int(self.rpm * self.scale * self.headroom))
        wait = 0.0
        used = sum(t for _, t in self.tok)
        for t0, tk in self.tok:                 # oldest first
            if used + est <= cap_t:
                break
            used -= tk
            wait = max(wait, t0 + 60 - now)
        if len(self.req) >= cap_r:
            wait = max(wait, self.req[len(self.req) - cap_r] + 60 - now)
        return max(0.0, wait)

    def pressure(self, est: int, deadline_left: float) -> str:
        now = time.monotonic()
        w = self._wait_needed(est, now)
        committed = sum(t for _, t in self.tok) + self.pending + est
        if (self.waiting >= 3 or w > 0.3 * deadline_left or self.scale < 0.8
                or committed > 0.7 * self.tpm * self.scale * self.headroom):
            return "high"
        return "normal"

    # ---- acquire / release ----
    async def acquire(self, est: int, deadline: float, patience: float = 1e9):
        """Return a reservation (est tokens) or None if the request cannot start before its deadline."""
        deadline = min(deadline, time.monotonic() + patience)   # patience: how long we let anyone queue
        self.waiting += 1
        self.pending += est
        self.peak_waiting = max(self.peak_waiting, self.waiting)
        try:
            try:
                await asyncio.wait_for(self._lock.acquire(), timeout=max(0.0, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                return None
            try:
                while True:
                    now = time.monotonic()
                    w = self._wait_needed(est, now)
                    if self.inflight < self.max_inflight and w == 0:
                        self.tok.append((now, est))
                        self.req.append(now)
                        self.inflight += 1
                        self.day_used += 1
                        return est
                    if now + max(w, 0.05) > deadline:
                        return None
                    await asyncio.sleep(min(max(w, 0.05), 0.25))
            finally:
                self._lock.release()
        finally:
            self.waiting -= 1
            self.pending -= est

    def release(self, reserved: int | None, actual_tokens: int = 0) -> None:
        """actual_tokens > 0: replace the estimate with real usage. 0: the attempt failed, refund the reservation."""
        if reserved is None:
            return
        self.inflight -= 1
        for i in range(len(self.tok) - 1, -1, -1):
            if self.tok[i][1] == reserved:
                if actual_tokens:
                    self.tok[i] = (self.tok[i][0], actual_tokens)
                else:
                    del self.tok[i]
                    if self.req:
                        self.req.pop()
                    self.day_used = max(0, self.day_used - 1)
                break
        self.scale = min(1.0, self.scale + 0.02)

    def on_429(self) -> None:
        now = time.monotonic()
        if now - self._last_shrink > 2.0:       # shrink at most once per 2 s so a burst of 429s doesn't zero us
            self.scale = max(0.3, self.scale * 0.7)
            self._last_shrink = now
