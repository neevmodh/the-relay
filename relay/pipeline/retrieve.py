"""Chunking + BM25 retrieval. This is the 'tool' step: no LLM call, no tokens.

Settings are swept for Table 3: piece size (words), overlap, top-k, rerank.
Rerank here is a cheap lexical one (query-term coverage + phrase bonus),
so it costs no model tokens.
"""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[2]
TOK = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
STOP = set("the a an of to in and or is are was were be for on with as by that this it its from at we our can how what which does do".split())


STOP2 = STOP | set("many much get got use used have has had does did give gives".split())


def stem(w: str) -> str:
    for suf in ("ization", "ations", "ation", "ers", "ing", "ies", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokenize(s: str, v2: bool = False) -> list[str]:
    """v1: whole tokens. v2: drop possessives, split hyphens, light stemming, extra stop words."""
    s = s.lower()
    if not v2:
        return [w for w in TOK.findall(s) if w not in STOP]
    s = re.sub(r"['\u2019]s\b", "", s)
    return [stem(w) for w in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", s) if w not in STOP2]


@dataclass
class Chunk:
    cid: str
    paper: str
    arxiv: str
    version: str
    page: int
    text: str

    @property
    def cite(self) -> str:
        return f"{self.paper} (arXiv {self.arxiv}{self.version}), p.{self.page}"


@dataclass(frozen=True)
class Setting:
    size: int = 200      # words per piece
    overlap: int = 40
    k: int = 4           # pieces fetched
    rerank: bool = False
    v2: bool = False     # stemming tokenizer

    @property
    def name(self) -> str:
        return f"size{self.size}_k{self.k}_rr{int(self.rerank)}" + ("_stem" if self.v2 else "")


@lru_cache(maxsize=8)
def _index(size: int, overlap: int, v2: bool = False):
    chunks: list[Chunk] = []
    for line in (ROOT / "data" / "pages.jsonl").open():
        pg = json.loads(line)
        words = pg["text"].split()
        step = max(1, size - overlap)
        for i in range(0, max(1, len(words)), step):
            piece = " ".join(words[i:i + size])
            if len(piece.split()) < 20:
                continue
            chunks.append(Chunk(f"{pg['arxiv']}:{pg['page']}:{i}", pg["paper"], pg["arxiv"],
                                pg["version"], pg["page"], piece))
    return chunks, BM25Okapi([tokenize(c.text, v2) for c in chunks])


def coverage(query: str, c: "Chunk", v2: bool = False) -> float:
    """Fraction of distinct query terms present in the chunk. Gate for 'the papers do not say'."""
    qs = set(tokenize(query))
    return len(qs & set(tokenize(c.text, v2))) / max(1, len(qs))


def retrieve(query: str, s: Setting = Setting()) -> list[tuple[Chunk, float]]:
    chunks, bm25 = _index(s.size, s.overlap, s.v2)
    q = tokenize(query, s.v2)
    scores = bm25.get_scores(q)
    pool = 3 * s.k if s.rerank else s.k
    top = sorted(range(len(chunks)), key=lambda i: -scores[i])[:pool]
    out = [(chunks[i], float(scores[i])) for i in top]
    if s.rerank:
        qs = set(q)
        def cov(c: Chunk) -> float:
            return len(qs & set(tokenize(c.text, s.v2))) / max(1, len(qs))
        out = sorted(out, key=lambda t: -(cov(t[0]) + 0.02 * t[1]))[:s.k]
    return out


if __name__ == "__main__":
    import sys
    for c, sc in retrieve(" ".join(sys.argv[1:]) or "scaled dot-product attention scaling factor"):
        print(f"{sc:6.2f}  {c.cite}\n        {c.text[:110]}...")
