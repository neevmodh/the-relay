# The Relay: submission folder

- `The_Relay_writeup.pdf`: the write-up (pages 1-2 prose, page 3 the required tables). Source: `writeup/writeup.md`.
- `results.csv`: one row per request (748 rows; `source` is `real` or `stand-in`). Same file as `raw/results.csv`.
- `raw/`: `results.csv`, `details.jsonl` (per-request attempts, queue/backoff/work split, answers), `scenarios.jsonl`
  (duration, offered rate, peak queue per scenario), `probe_calls.jsonl` (all limit probing, headers kept),
  `budget_ledger.csv`, run logs.
- `history/`: the real conversation with the assistant (`conversation.md`, `conversation_raw.jsonl`). API key and organization id redacted.
- `relay/`: code. `pipeline/` (retrieve, client, sched = limiter, run), `standin/` (server, calibrate, calib.json),
  `probe/`, `loadgen/`, `eval/` (questions.jsonl, grader), `analysis/tables.py` (recomputes Tables 2a/2b/3 from results.csv).
- `scripts/`: fetch papers, stand-in scenarios, history export.

Reproduce: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`, put `GROQ_API_KEY` in `.env`,
`scripts/fetch_papers.sh`, start `python -m relay.standin.server --port 8001`, run `scripts/run_standin_scenarios.sh`,
real runs via `python -m relay.loadgen.run_load ...` (see `raw/scenarios.jsonl` for the settings used), then
`python -m relay.analysis.tables`.

Real vs stand-in: rows with `source=real` are Groq `openai/gpt-oss-20b`; `stand-in` rows come from `relay/standin/server.py`.
Answer grades on stand-in rows are blank (its answers are canned text), except the passages-only fallback replies.
Scenario names: `steady_v0` is the first real run, kept because it exposed a bug (see write-up section 8 / notes); `sweep_A` is the steady scenario
with the final code; `overload_q20` = queue-to-deadline version kept for comparison with `overload` (8 s patience).
