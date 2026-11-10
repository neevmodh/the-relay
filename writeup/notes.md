# Running notes for the write-up (raw observations, keep honest)

## Retriever pitfalls found so far
1. Moshi appendix (pp.63-64) holds sample dialogue transcripts (France, football, etc.). Off-topic questions
   ("capital of France", "who won the 2022 world cup") score 5.6 / 15.2 BM25 there, so a raw BM25 score floor
   does NOT detect "papers don't say". Need coverage-based gate, not score floor.
2. Dynamic Chunking p.3: figure text extracts as garbled glyphs ("D 4NPPUIJOH.PEVMF ...") yet outranks real text
   for "routing module". Garbage chunks consume top-k slots.
3. Moshi is ~191k of ~376k chars: bigger paper dominates generic queries (to be demonstrated with a question).

## Gate change
Replaced BM25 score floor with query-term coverage (best chunk). Off-topic: 0.33; on-topic: 0.50-1.00.
Fragile: "how many codebooks does Mimi use" sits exactly at 0.50. Related-but-unanswerable ("BLEU of GPT-4")
scores 0.75 and passes the gate, so refusal there has to come from the model. Threshold to be tuned on eval set.

## First real probe (openai/gpt-oss-20b, 1 request)
Headers: limit-requests=1000, limit-tokens=8000, remaining 999 / 7862, reset-requests=1m26.4s, reset-tokens=1.035s.
- 1000 is almost certainly the PER-DAY request limit (86.4 s per request = 86400/1000 = reset-requests); confirm via 429 body.
- 8000 is tokens per MINUTE (138 tokens used -> reset 1.035 s = 138/8000*60 s, i.e. continuous refill).
- 8000 TPM is the binding constraint: a pipeline prompt of ~1500 tokens allows only ~5 requests/min.
- No RPM header; RPM, in-flight limit and TPD still to be found from a 429 body.
- Model: llama-3.1-8b-instant is NOT available on this account; account lists gpt-oss-20b/120b, qwen3.8-27b.
- SECURITY: API key was pasted into the chat -> it is in the conversation history that must be submitted. Redact + rotate.

## Eval-set offline check (free, no API)
Coverage gate cannot separate answerable (0.43-0.89) from unanswerable (0.29-0.67). q05 answerable at 0.43 would be
refused at 0.5 -> lowered gate to 0.35; it is only a cheap filter for blatant off-topic. Model must do real refusals.
Gold NOT in top-4 (size200,k4, BM25) for: q03 (base-model BLEU 27.3 is in a table on p.8; abstract says 28.4 = big model,
so a naive retriever returns the wrong number), q14 (Helium 7B/2.1T split across passages), q15 (WavLM).
Smoke test (real, 4 req): q03 -> refused_wrongly, i.e. retrieval miss turned into a wrong refusal.
Pitfall candidates: (1) numeric table rows lose their headers/captions in extraction; (2) abstract headline number
(28.4) outranks the table row for the base model (27.3) -> wrong-but-confident; (3) Moshi appendix dialogues match
everyday words; (4) garbled figure text; (5) Moshi size dominance; (6) BERT/GPT-3 appear only in Moshi, so
'Transformer paper vs BERT' pulls Moshi passages.

## Steady v0 (real, 23 req @5/min, size200 k4) -> kept as scenario steady_v0
Two requests marked timeout though they had a valid first answer: model wrote citations as 【1】 (full-width), my
verify() wanted [1], so it regenerated; the regeneration needed ~2k tokens, the 7.2k-token window had no room before
the 20 s deadline -> limiter shed it and I discarded the good first answer. Fixes: normalize 【n】, keep first answer
if regeneration can't run. Grader also missed non-breaking spaces ("3.5 days") -> 3 correct answers graded wrong;
regraded from stored answers (raw/details.jsonl) with relay/eval/regrade.py.
After regrade: correct 12, refused_correctly 5, refused_wrongly 3 (q03,q11,q14: retrieval misses), wrong 1 (q15: no model name), 2 ungraded.
TTFT ~ total (median ~0.9 s): gpt-oss hides reasoning, the visible answer arrives almost at once -> no useful streaming.

## vaani.dev observations (via text fetch, NOT a real browser: verify before submitting)
Voice AI platform for phone agents (sales/admissions/support). Stood out: concrete latency claim (sub-500ms, ~450ms p90),
customer numbers (891 leads, 16,282 calls), Teacher AI (agent from plain-language description), call screening.
Confusing: latency stated as "sub-500ms" and "~450ms p90" with no definition (end of user speech -> first audio? which
percentile/network?); stat counters read 0M+/0.0%/<0ms in the fetched text (probably animation, check in browser);
three domains (vaani.dev, vaanivoice.ai, platform.vaani.dev) behind different buttons; "world's speech modelling &
infrastructure layer" is vague. Change: define the latency number on the page (what is measured, p50/p90/p99, under what load)
-- ties to this assignment, where time-to-first-token and the slow tail are the whole story.

## Retrieval sweep so far (real, 23 questions each)
steady_v0 (200/k4): correct 12; sweep_A (120/k3): correct 14 (v0 had 2 ungraded due to the shed bug; so A~B);
sweep_C (200/k6/rerank): correct 14, tokens ~2x A. Identical failures at ALL settings: q03,q11 (refused_wrongly), q14 (refused_wrongly), q15 (wrong).
Tokens per call (input sum / 23): v0 27.4k, A 16.4k, C 33.8k. => more pieces/rerank bought 0 questions at 2x cost.
Diagnosis offline: gold chunk BM25 rank q03 5-7, q11 6-9, q14 22, q15 9-26 (not in top 6). Causes: tokenizer ("Mimi's"!="mimi",
"7B-parameter"!="parameters", "quantizers"!="quantizer"), generic query words (many/get/use), numeric table rows.
Stemming tokenizer (v2): q14 22->5, q15 9->3, q03 5->6, q11 6->8 (size200); at size120 q11 6->35 (worse). Tested as sweep_D.

## TABLE 1 evidence (real, openai/gpt-oss-20b, free/on_demand tier)
- RPM = 30: probe burst of 40 tiny concurrent requests -> exactly 30 ok, 10 rate_limited; body "requests per minute (RPM): Limit 30, Used 30, Requested 1. Please try again in 2s"; recovered ~4 s. HIGH.
- TPM = 8000: naive burst of 10 x ~1.4k-token requests -> 5 ok, 5 429 "tokens per minute (TPM): Limit 8000, Used 7433, Requested 1477. Please try again in 6.825s"; header x-ratelimit-limit-tokens=8000; remaining-tokens falls by tokens used and refills continuously (138 tokens -> reset 1.035 s). HIGH.
- RPD = 1000: header x-ratelimit-limit-requests=1000, remaining decremented per ok request; reset-requests = used*86.4 s (e.g. 117 used -> 2h48m28.8s) => rolling refill, not midnight reset. Never hit it. MEDIUM (header only).
  429s appear NOT to count toward RPD (883 -> 854 after 30 ok + 10 rejected).
- TPD: not hit, not in any header. NOT MEASURED (low).
- In flight: 40 concurrent accepted without a concurrency error (the RPM limit bit first). Not separately limited up to 40. LOW.
- 429 response: HTTP 429, JSON error.message names the limit (TPM/RPM), retry-after header (seconds, integer), x-ratelimit-* headers.
- Recovery: TPM retry-after 7-8 s (depends on size of request vs freed tokens); RPM 2 s stated, ~4 s observed.
Cost: $0.075/M in, $0.30/M out (Groq docs, notional; free tier costs 0).
Careful burst (real, n=12): ok 10, shed 2, 0 provider 429, peak queue 8. Naive burst (real, n=10): ok 5, 5 failed after 4 attempts each in ~0.7 s (20 rejected calls).
