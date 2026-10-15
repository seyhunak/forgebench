"""Text-overlap metrics for generation-style outputs (BLEU, ROUGE-L)."""

from __future__ import annotations

import math
import re
from collections import Counter


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", (text or "").lower())


def bleu(hypothesis: str, reference: str, max_n: int = 4) -> float:
    hyp = _tokens(hypothesis)
    ref = _tokens(reference)
    if not hyp or not ref:
        return 0.0
    if len(hyp) > len(ref):
        bp = 1.0
    else:
        bp = (len(hyp) / len(ref)) ** 0.5 if len(ref) else 0.0
    precisions = []
    for n in range(1, max_n + 1):
        hyp_ngrams = Counter(tuple(hyp[i : i + n]) for i in range(len(hyp) - n + 1))
        ref_ngrams = Counter(tuple(ref[i : i + n]) for i in range(len(ref) - n + 1))
        clipped = sum(min(c, ref_ngrams[g]) for g, c in hyp_ngrams.items())
        total = sum(hyp_ngrams.values())
        precisions.append(clipped / total if total else 0.0)
    if any(p == 0 for p in precisions):
        return 0.0
    geo = math.exp(sum(math.log(p) for p in precisions) / len(precisions))
    return bp * geo


def _lcs(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


def rouge_l(hypothesis: str, reference: str) -> float:
    hyp = _tokens(hypothesis)
    ref = _tokens(reference)
    if not hyp or not ref:
        return 0.0
    lcs = _lcs(hyp, ref)
    precision = lcs / len(hyp)
    recall = lcs / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
