#!/bin/sh
# Stand-in scenarios (careful policy, patience 8 s). Stand-in server must be running on :8001
# (python -m relay.standin.server --port 8001). Limits in calib.json come from the real probe: tpm 8000, rpm 30, rpd 1000.
# History: overload_q20 (patience = deadline = 20 s) and overload_naive were run earlier with the same stand-in:
#   overload_q20:   ... --scenario overload_q20 --shape overload --rate 60 --duration 180 --patience 20
#   overload_naive: ... --scenario overload_naive --shape overload --rate 60 --duration 180 --policy naive
cd "$(dirname "$0")/.." || exit 1
export LLM_BASE_URL=http://127.0.0.1:8001/v1
PY=.venv/bin/python
cfg() { curl -s -X POST localhost:8001/admin/config -H 'content-type: application/json' -d "$1" >/dev/null; }
RUN="$PY -m relay.loadgen.run_load --source stand-in --size 120 --k 3 --deadline 20 --patience 8"

cfg '{"reset":true,"tpm":8000,"rpm":30,"rpd":1000}'
$RUN --scenario burst_standin --shape burst --n 40
cfg '{"reset":true}'; sleep 65
$RUN --scenario overload --shape overload --rate 60 --duration 180
# per-minute limits halved WITHOUT telling the limiter (it still believes 8000/30)
cfg '{"reset":true,"tpm":4000,"rpm":15}'; sleep 65
$RUN --scenario limit_halved --shape steady --rate 8 --n 24
# daily budget exhausted after 20 requests; limiter still believes 1000/day
cfg '{"reset":true,"tpm":8000,"rpm":30,"rpd":20}'; sleep 65
$RUN --scenario daily_exhausted --shape steady --rate 10 --n 30
cfg '{"reset":true,"rpd":1000}'
