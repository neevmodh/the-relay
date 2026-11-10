"""Re-apply the grader to stored answers (raw/details.jsonl) and rewrite answer_grade in raw/results.csv.
Used after fixing the grader; deterministic, so anyone can reproduce it."""
import json
import pandas as pd
from pathlib import Path
from relay.eval.grade import grade

RAW = Path(__file__).resolve().parents[2] / "raw"
df = pd.read_csv(RAW / "results.csv", keep_default_na=False)
det = {d["request_id"]: d for d in map(json.loads, (RAW / "details.jsonl").open())}
before = df.answer_grade.value_counts().to_dict()
df["answer_grade"] = [grade(det[r]["qid"], det[r]["answer"], det[r]["kind"]) for r in df.request_id]
df.to_csv(RAW / "results.csv", index=False)
print("before", before, "\nafter ", df.answer_grade.value_counts().to_dict())
