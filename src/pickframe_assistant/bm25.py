"""Okapi BM25 over pre-tokenised documents. No dependencies, deterministic, easy to explain."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    index: int
    score: float


class BM25Index:
    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._counts = [Counter(doc) for doc in docs]
        self._lengths = [len(doc) for doc in docs]
        self._avg_length = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        frequency: Counter[str] = Counter()
        for counts in self._counts:
            frequency.update(counts.keys())
        self._doc_frequency = frequency

    def __len__(self) -> int:
        return len(self._counts)

    @property
    def vocabulary(self) -> frozenset[str]:
        return frozenset(self._doc_frequency)

    def terms(self, index: int) -> frozenset[str]:
        return frozenset(self._counts[index])

    def idf(self, term: str) -> float:
        """Inverse document frequency. A term the corpus has never seen gets the highest weight."""
        n = len(self._counts)
        df = self._doc_frequency.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: Sequence[str], k: int) -> list[Hit]:
        """The top `k` documents with a positive score. Ties break on document order."""
        terms = set(query)
        hits: list[Hit] = []
        for index, counts in enumerate(self._counts):
            length_norm = 1 - self._b + self._b * self._lengths[index] / (self._avg_length or 1.0)
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if tf:
                    score += self.idf(term) * tf * (self._k1 + 1) / (tf + self._k1 * length_norm)
            if score > 0:
                hits.append(Hit(index, score))
        hits.sort(key=lambda hit: (-hit.score, hit.index))
        return hits[:k]
