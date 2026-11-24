"""BM25 检索：纯 Python，用于在客服知识库里找最相关的答案段落。

取舍：
1. 中文按「单字 + 二元组」切词，问"能不能退款"时"退款/能不"都能命中；
2. 单字权重压到二元组的 0.3，否则"的/是/我"会把分数抬起来；
3. 查询里的二元组一个都没命中的段落直接扔掉。
"""

from __future__ import annotations

import math
from collections import Counter

from .text import tokenize

K1 = 1.5
B = 0.75
UNIGRAM_WEIGHT = 0.3


def _weighted_counts(s: str) -> Counter:
    counts: Counter = Counter()
    for tok in tokenize(s):
        counts[tok] += UNIGRAM_WEIGHT if len(tok) == 1 else 1.0
    return counts


class BM25Index:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.tfs: list[Counter] = []
        self.lens: list[float] = []
        self.df: Counter = Counter()

        for d in docs:
            counts = _weighted_counts(d.get("text", ""))
            self.tfs.append(counts)
            self.lens.append(sum(counts.values()) or 1.0)
            for term in counts:
                self.df[term] += 1

        self.n = len(docs)
        self.avgdl = (sum(self.lens) / self.n) if self.n else 0.0

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, idx: int, q_terms: set[str]) -> float:
        tf, dl = self.tfs[idx], self.lens[idx]
        s = 0.0
        for term in q_terms:
            f = tf.get(term, 0.0)
            if not f:
                continue
            s += self.idf(term) * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / self.avgdl))
        return s

    def search(self, query: str, top_k: int = 4, min_score: float = 0.0) -> list[dict]:
        q_terms = set(tokenize(query))
        if not q_terms or not self.n:
            return []

        bigrams = [t for t in q_terms if len(t) > 1]
        hits = []
        for i, doc in enumerate(self.docs):
            s = self.score(i, q_terms)
            if s <= 0:
                continue
            covered = sum(1 for t in bigrams if self.tfs[i].get(t))
            if bigrams and covered == 0:
                continue
            cover = covered / len(bigrams) if bigrams else 0.0
            hits.append((s * (0.6 + 0.4 * cover), doc))

        hits.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, doc in hits[:top_k]:
            if s < min_score:
                continue
            out.append({**doc, "score": round(s, 4)})
        return out
