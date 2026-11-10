# Live-conversation prep (NOT part of the submission)

They will ask you to explain results and change the system live. You must be able to say each of these in your own words.

## The 6 decisions, and what each cost
1. **Token limiter first** (8,000 TPM binds before 30 RPM or 1,000 RPD; ~10 answers/min). Cost: capped throughput, shed under overload.
2. **8 s patience, fail fast** instead of queueing to a 20 s deadline. Gain: served wait 16.0 s -> 6.0 s, same throughput (40 vs 39). Cost: 78% instant "no" at 5x overload. The 8 s is an assumption, not measured. *Try changing it live (sched.py `patience`) and rerun a stand-in scenario.*
3. **Degrade before refusing** (3->2 passages, 250 max tokens, no regeneration) once committed tokens >70% of cap. Cost: weaker answers (33 of 39 served at overload were degraded).
4. **Setting 120 / 3 / no re-rank.** Same quality as 200/6/re-rank (60.9%) at half the tokens (773 vs 1,533). No setting fixed q03, q11, q14.
5. **Daily budget gone -> passages only, no model call** (4 ms; 5 of 10 contained the answer). Gap: flag never clears, but the allowance refills ~1 request / 86.4 s.
6. **Retries**: max 2, only 429/timeout/5xx, `retry-after` + jitter, never past deadline; daily 429 not retried.

## Numbers to know cold
RPM 30 | TPM 8,000 | RPD 1,000 | TPD not measured | 429 body names the limit; `retry-after` integer seconds.
Real steady (23 req @5/min): TTFT 790/1185/2753 ms, 100% ok. Decode after first token: median 21 ms (reasoning model hides thinking).
Naive real burst: 50% ok, 15 immediate retries all failed. Careful real burst: 10/12 served, 0 provider 429s.
Quality (23 q): 60.9% correct, 4.3% wrong, 21.7% correctly refused, 13.0% wrongly refused.

## Things you must be able to explain
- Why `steady_v0` exists (a bug: model cited as `【1】`, verify failed, regeneration was shed, good answer discarded) and what changed.
- Why stand-in rows have blank grades, and why stand-in p99 (1.7 s) is thinner than real (2.75 s).
- Why the coverage gate is only 0.35 (q05 at 0.43 was refused at 0.5; coverage cannot separate answerable from unanswerable).
- Why total p50 is 8 ms in overload (most requests were turned away instantly).
- Weakest points: hidden-reasoning ~40 tokens is one data point; patience 8 s unmeasured; real service never overloaded beyond two bursts; peak queue comes from scenarios.jsonl not results.csv.

## Do before you submit (I cannot do these for you)
1. **Rotate your Groq key** (it appeared in the chat and so in the history; redacted in the export, but rotate anyway).
2. **Visit vaani.dev yourself** and rewrite the "Your feedback on Vaani" paragraph in your own honest words (my draft came from a text fetch).
3. **Rewrite "How I worked with the assistant" truthfully.** The draft says you overruled nothing. If you want that to change, review a decision, change it, and record it.
4. Rewrite the "new to me" sentence in section 8 in your own words (it must be something *you* learned).
5. Re-export history last (`python scripts/export_history.py`), rebuild PDF (`python writeup/build.py`), re-copy into `submission/`.
6. Upload `submission/` to Google Drive, set "Anyone with the link can view", paste the link into the form with the same email you applied with. Deadline: Sat 14 Nov 2026, 8:43 AM IST.
