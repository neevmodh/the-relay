# The Relay: plan

Deadline: Sat 14 Nov 2026, 8:43 AM IST. Today: 10 Nov. Python + asyncio + httpx.

## Layout
```
relay/pipeline/   router, retrieve, generate, verify, limiter, run
relay/standin/    fake Groq-compatible SSE server + calib.json
relay/probe/      real-service limit/latency probing
relay/loadgen/    load shapes -> raw/results.csv
relay/eval/       questions.jsonl (>=15) + grading
relay/analysis/   tables recomputed from results.csv only
data/papers/      the 3 arXiv PDFs (pinned versions)
raw/              results.csv, probe headers, logs (submitted)
writeup/          2-page write-up, tables.md
history/          exported assistant conversation (real, uncleaned)
```

## Pipeline design (draft)
1. **Route** (cheap call or rules): classify as answerable-from-library / off-topic / needs-multi-paper; rewrite query.
2. **Retrieve** (tool call, no LLM): BM25 over chunks, optional rerank. Returns chunks with paper, version, section, page.
3. **Generate** (streaming call): answer using only chunks, with citations [paper, section].
4. **Verify** (cheap call or rule check): every claim cited? citations exist in retrieved chunks?
   - Branch: weak retrieval score -> refuse with "papers don't say".
   - Loop: verify fails -> one regenerate with more chunks, max 1 extra.
Shared **limiter**: token bucket for RPM/TPM, daily budget counter, priority queue, bounded queue.

## The one shaping decision (to confirm with measurements)
How the limiter spends scarce tokens under pressure: shed the expensive steps (verify, rerank, big context) before shedding requests. Degrade quality before refusing people. Cost: weaker answers during overload.

## Phases
| Phase | Work | Output |
|---|---|---|
| 0 | Fetch 3 papers at exact versions, chunk | data/papers |
| 1 | Pipeline v0 against real Groq, tiny runs | working end-to-end |
| 2 | Probe real limits; log every header; hit a 429 on purpose | Table 1, raw/probe_* |
| 3 | Write 15-20 questions + grading | eval set |
| 4 | Retrieval sweep, 3+ settings, real calls | Table 3 |
| 5 | Calibrate and build stand-in | calib.json |
| 6 | Load shapes (real when safe, stand-in for overload) | Tables 2a/2b, results.csv |
| 7 | Trace one slow request: wait / work / retry | section 4 |
| 8 | Write-up, vaani.dev feedback, history export | 2 pages |
| 9 | Rehearse live defense; upload to Drive | submit |

## Day plan
- Day 1 (10 Nov): phases 0-2.
- Day 2 (11 Nov): phases 3-5.
- Day 3 (12 Nov): phases 6-7.
- Day 4 (13 Nov): phases 8-9. Buffer until 14 Nov morning.

## Real daily budget discipline
The Groq daily quota is shared by everything. Keep a ledger (raw/budget_ledger.csv). Do probing and retrieval-sweep calls first and sparingly; use the stand-in for everything heavy. Never use extra accounts.

## Open items / to verify, not assume
- Actual Groq limits for the chosen model (read x-ratelimit-* headers and 429 bodies).
- Time to first token is measured from the client at the stream's first content chunk.
- results.csv must let every table number be recomputed.
- Save the conversation history as we go (do not clean it up).
