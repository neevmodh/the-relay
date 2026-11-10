#!/bin/sh
# Fetch the three papers at the exact versions required, then extract page text.
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/papers
curl -sSL -o data/papers/attention_1706.03762v7.pdf https://arxiv.org/pdf/1706.03762v7
curl -sSL -o data/papers/moshi_2410.00037v1.pdf https://arxiv.org/pdf/2410.00037v1
curl -sSL -o data/papers/dynchunk_2507.07955v2.pdf https://arxiv.org/pdf/2507.07955v2
.venv/bin/python relay/pipeline/ingest.py
