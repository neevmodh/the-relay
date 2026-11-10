"""Export the Claude Code session transcript to history/ with the Groq API key redacted (nothing else is edited)."""
import json, re, sys
from pathlib import Path
SRC = Path.home() / ".claude/projects/-Users-neev-Downloads-INT" / "6b94c0a8-8a7d-4e4f-8f34-0bd7fdea1fb8.jsonl"
OUT = Path(__file__).resolve().parents[1] / "history"
OUT.mkdir(exist_ok=True)
KEY = re.compile(r"gsk_[A-Za-z0-9]{20,}")
raw = KEY.sub("gsk_REDACTED", SRC.read_text()).replace("KEY_PREFIX_REDACTED", "KEY_PREFIX_REDACTED")
(OUT / "conversation_raw.jsonl").write_text(raw)

def blocks(c):
    if isinstance(c, str):
        yield "text", c; return
    for b in c or []:
        t = b.get("type")
        if t == "text": yield "text", b["text"]
        elif t == "tool_use": yield "tool_use", json.dumps(b.get("input"), ensure_ascii=False)[:4000]
        elif t == "tool_result":
            c2 = b.get("content")
            yield "tool_result", c2 if isinstance(c2, str) else json.dumps(c2, ensure_ascii=False)[:4000]
        elif t == "thinking": continue

lines = ["# Conversation history (Claude Code session export; API key redacted, nothing else edited)\n"]
for l in raw.splitlines():
    try: e = json.loads(l)
    except Exception: continue
    if e.get("type") not in ("user", "assistant"): continue
    m = e.get("message", {})
    for kind, text in blocks(m.get("content")):
        if kind == "text" and text.strip():
            lines.append(f"\n## {e['type'].upper()}\n\n{text.strip()}\n")
        elif kind == "tool_use":
            lines.append(f"\n### assistant tool call\n\n```\n{text}\n```\n")
        elif kind == "tool_result":
            lines.append(f"\n### tool result\n\n```\n{str(text)[:4000]}\n```\n")
(OUT / "conversation.md").write_text("".join(lines))
print("exported", len(lines), "blocks; key occurrences left:", len(KEY.findall((OUT / 'conversation.md').read_text() + raw)))
