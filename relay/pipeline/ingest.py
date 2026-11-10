"""Extract per-page text from the 3 pinned papers and write data/pages.jsonl.

Chunking happens at retrieval time (retrieve.py) so piece size can be swept.
Each page record keeps paper, version and page number so citations can point
to where an answer came from.
"""
import json
import re
import sys
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parents[2]
PAPERS = {
    "attention_1706.03762v7.pdf": ("Attention Is All You Need", "1706.03762", "v7"),
    "moshi_2410.00037v1.pdf": ("Moshi", "2410.00037", "v1"),
    "dynchunk_2507.07955v2.pdf": ("Dynamic Chunking", "2507.07955", "v2"),
}
HEAD = re.compile(r"^(\d+(\.\d+)*)\s+[A-Z][^\n]{2,80}$", re.M)


def clean(t: str) -> str:
    t = t.replace("\x00", "")
    t = re.sub(r"-\n(?=[a-z])", "", t)  # undo hyphenation across lines
    return re.sub(r"[ \t]+", " ", t).strip()


def main() -> None:
    out = ROOT / "data" / "pages.jsonl"
    n = 0
    with out.open("w") as f:
        for fn, (title, aid, ver) in PAPERS.items():
            r = pypdf.PdfReader(ROOT / "data" / "papers" / fn)
            for i, p in enumerate(r.pages, 1):
                text = clean(p.extract_text() or "")
                heads = [m.group(0) for m in HEAD.finditer(text)]
                f.write(json.dumps({"paper": title, "arxiv": aid, "version": ver,
                                    "page": i, "headings": heads, "text": text}) + "\n")
                n += 1
    print(f"wrote {n} pages -> {out}")


if __name__ == "__main__":
    sys.exit(main())
