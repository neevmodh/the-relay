"""Build writeup/The_Relay_writeup.pdf: pages 1-2 prose (writeup.md), then the required tables (table1.md + tables.md)."""
import subprocess, sys
from pathlib import Path
import markdown
W = Path(__file__).resolve().parent
tables = (W / "tables.md").read_text().replace("## Table 2a", "### Table 2a: latency, one row per load scenario") \
    .replace("## Table 2b", "### Table 2b: outcomes, same rows").replace("## Table 3", "### Table 3: retrieval settings")
css = """@page{size:A4;margin:10mm 11mm}body{font:9.7pt/1.34 Helvetica,Arial,sans-serif;color:#111}
h1{font-size:13pt;margin:0 0 3px}p{margin:0 0 5.5px;text-align:justify}code{font-size:8.6pt;background:#f1f1f1;padding:0 1px}
.tables{page-break-before:always}.tables h3{font-size:9.5pt;margin:8px 0 3px}
table{border-collapse:collapse;width:100%;font-size:7.4pt;margin-bottom:3px}th,td{border:1px solid #bbb;padding:1.5px 3px;text-align:left;vertical-align:top}th{background:#eef1f4}
.note{font-size:7.3pt;color:#333}"""
prose = markdown.markdown((W / "writeup.md").read_text(), extensions=["tables"])
t1 = markdown.markdown((W / "table1.md").read_text(), extensions=["tables"])
tb = markdown.markdown(tables, extensions=["tables"])
note = ("<p class='note'>Notes. Real = Groq <code>openai/gpt-oss-20b</code>; stand-in = my server calibrated from real measurements. "
        "Percentiles: linear interpolation over the requests that have the value (p95/p99 of 23 requests are near the maximum). Total time includes requests that were turned away (a turned-away request takes ms, so total p50 can be tiny in overload). "
        "Rate-limited % counts requests that got no model answer because of a limit (provider 429 or the passages-only reply after the daily budget). 'Timed out or given up' includes requests my limiter refused after 8 s patience. "
        "Table 3 percentages do not sum to 100: the rest are answers refused wrongly (3 of 23 at every setting), and size200_k4 has 21 graded rows (2 requests lost to a bug fixed afterwards; run kept as <code>steady_v0</code>). "
        "Cost is notional list price ($0.075 / $0.30 per M tokens), the free tier costs nothing. Tokens per answer count API-reported tokens only. Scenarios <code>overload_q20</code> (queue to 20 s) and <code>overload_naive</code> are in results.csv for comparison with <code>overload</code>.</p>")
html = f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{prose}<div class='tables'><h1>Required results tables</h1><h3>Table 1: limits found in the real service</h3>{t1}{tb}{note}</div></body></html>"
(W / "writeup.html").write_text(html)
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
out = W / "The_Relay_writeup.pdf"
subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", f"file://{W/'writeup.html'}"],
               check=True, capture_output=True)
import pypdf
print("pages:", len(pypdf.PdfReader(str(out)).pages))
