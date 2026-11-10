## Table 2a

| Scenario | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |
|---|---|---|---|---|---|---|
| steady (= sweep_A) | real | 23 | 264.5 | 5.2 | 790 / 1185 / 2753 | 817 / 1273 / 2797 |
| burst_naive_real | real | 10 | 1.0 | 623.9 | 742 / 829 / 839 | 510 / 900 / 918 |
| burst | real | 12 | 2.4 | 303.4 | 1201 / 2011 / 2041 | 1186 / 2046 / 2107 |
| overload_q20 | stand-in | 180 | 192.0 | 60.3 | 16897 / 19546 / 19741 | 8 / 19124 / 20013 |
| overload_naive | stand-in | 180 | 179.0 | 60.3 | 864 / 3410 / 4837 | 13 / 1020 / 3085 |
| burst_standin | stand-in | 40 | 3.4 | 711.6 | 1588 / 2983 / 3144 | 1278 / 2663 / 3032 |
| overload | stand-in | 180 | 185.6 | 60.3 | 6730 / 8188 / 9402 | 8 / 7820 / 8670 |
| limit_halved | stand-in | 24 | 172.6 | 8.3 | 689 / 7992 / 8184 | 617 / 15773 / 18733 |
| daily_exhausted | stand-in | 30 | 174.0 | 10.3 | 947 / 1541 / 1743 | 828 / 1544 / 1734 |

## Table 2b

| Scenario | Succeeded % | Rate-limited % | Timed out or given up % | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers (USD, notional) |
|---|---|---|---|---|---|---|---|
| steady (= sweep_A) | 100.0 | 0.0 | 0.0 | 0.00 | 1 | 773 | 0.072 |
| burst_naive_real | 50.0 | 50.0 | 0.0 | 1.50 | 0 | 1441 | 0.126 |
| burst | 83.3 | 0.0 | 16.7 | 0.00 | 8 | 684 | 0.065 |
| overload_q20 | 22.2 | 0.6 | 77.2 | 0.01 | 20 | 607 | 0.057 |
| overload_naive | 15.6 | 84.4 | 0.0 | 2.58 | 0 | 791 | 0.073 |
| burst_standin | 22.5 | 0.0 | 77.5 | 0.00 | 35 | 706 | 0.067 |
| overload | 21.7 | 0.0 | 78.3 | 0.01 | 9 | 603 | 0.057 |
| limit_halved | 66.7 | 4.2 | 29.2 | 0.12 | 2 | 613 | 0.056 |
| daily_exhausted | 66.7 | 33.3 | 0.0 | 0.00 | 1 | 630 | 0.058 |

## Table 3

| Setting (piece size, pieces fetched, re-rank) | Questions asked | Correct and cited % | Wrong % | Correctly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| size120_k3_rr0 | 23 | 60.9 | 4.3 | 21.7 | 773 | 790 / 1185 | 817 / 1273 |
| size200_k4_rr0 | 21 | 57.1 | 4.8 | 23.8 | 1309 | 916 / 1112 | 919 / 1115 |
| size200_k5_rr1_stem | 23 | 56.5 | 8.7 | 21.7 | 1263 | 825 / 1354 | 858 / 1356 |
| size200_k6_rr1 | 23 | 60.9 | 4.3 | 21.7 | 1533 | 797 / 1549 | 826 / 1576 |
