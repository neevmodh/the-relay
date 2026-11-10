| Limit | Value you found | How you found it | Confidence |
|---|---|---|---|
| Requests per minute | 30 | Burst of 40 tiny concurrent requests: exactly 30 ok, 10 rejected; body says `requests per minute (RPM): Limit 30, Used 30` | high |
| Tokens per minute | 8,000 | `x-ratelimit-limit-tokens: 8000`; naive burst of 10 real requests: 5 rejected with `TPM: Limit 8000, Used 7433, Requested 1477`; remaining-tokens refills continuously | high |
| Requests per day | 1,000 | `x-ratelimit-limit-requests: 1000`, falls by 1 per successful call; `reset-requests` = used × 86.4 s (rolling refill). Never reached | medium |
| Tokens per day | not measured | In no header and never reached; I did not spend the quota to find it (about 130k tokens used in all) | low |
| Requests in flight at once | no separate limit found (40 concurrent accepted until RPM bit) | Burst of 40 and burst of 8 produced no concurrency error | low |
| What it returns when a limit is hit | HTTP 429, JSON message naming the limit, integer `retry-after` header (2 to 8 s seen) | Seen in the probe burst and the naive real burst | high |
| Time until it recovers | RPM about 4 s (2 s stated); TPM 6.8 to 8 s stated, depends on request size | RPM: polled once per 3 s after the burst. TPM: from `retry-after`, not independently timed | medium |
