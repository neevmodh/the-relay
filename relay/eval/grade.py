"""Automatic grading against questions.jsonl, spot-checked by hand.

answerable/trap : answered + cites [n] + all gold patterns match -> correct; answered otherwise -> wrong;
                  refused -> refused_wrongly
unanswerable    : refused -> refused_correctly; answered -> wrong (it said something the papers don't support)
Failed requests (timeout/error) get no grade. Fallback replies (passages only) are graded by whether the
passages contain the gold fact, because that is what the person received.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

QS = {q["id"]: q for q in (json.loads(l) for l in (Path(__file__).parent / "questions.jsonl").open())}
REFUSE_RE = re.compile(r"(do(es)? not|don't|doesn't|cannot|can't|no) (say|contain|mention|provide|state|report|specify|address)|"
                       r"not (in|found in|covered by) the (papers|passages)|do not say", re.I)


def is_refusal(text: str) -> bool:
    return bool(REFUSE_RE.search(text[:250]))


def grade(qid: str, answer: str, kind: str) -> str:
    """kind is the pipeline outcome kind: answered | refused | fallback | shed | failed"""
    q = QS[qid]
    answer = re.sub(r"[【\[]\s*(\d+)\s*[】\]]", r"[\1]", unicodedata.normalize("NFKC", answer)).replace("\u2011", "-")
    if kind in ("shed", "failed"):
        return ""
    refused = kind == "refused" or is_refusal(answer)
    if q["kind"] == "unanswerable":
        return "refused_correctly" if refused else "wrong"
    if kind == "fallback":
        return "correct" if re.search(q["gold"], answer, re.I | re.S) else "wrong"
    if refused:
        return "refused_wrongly"
    cited = bool(re.search(r"\[\d+\]", answer))
    return "correct" if cited and re.search(q["gold"], answer, re.I | re.S) else "wrong"
