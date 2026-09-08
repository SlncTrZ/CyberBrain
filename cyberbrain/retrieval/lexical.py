# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN_RE.findall(text))


@dataclass(frozen=True, slots=True)
class BM25Document:
    id: str
    text: str


class BM25Scorer:
    """Small deterministic BM25 scorer for bounded candidate sets."""

    def __init__(self, documents: list[BM25Document], *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self._documents = tuple(documents)
        self._k1 = k1
        self._b = b
        self._tokens = {doc.id: tokenize(doc.text) for doc in documents}
        self._tf = {doc_id: Counter(tokens) for doc_id, tokens in self._tokens.items()}
        self._lengths = {doc_id: len(tokens) for doc_id, tokens in self._tokens.items()}
        self._avg_len = (sum(self._lengths.values()) / len(documents)) if documents else 0.0
        self._df: Counter[str] = Counter()
        for tokens in self._tokens.values():
            self._df.update(set(tokens))

    def score(self, query: str) -> list[tuple[str, float]]:
        if not self._documents:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return [(doc.id, 0.0) for doc in self._documents]
        n_docs = len(self._documents)
        result: list[tuple[str, float]] = []
        for doc in self._documents:
            score = 0.0
            doc_len = self._lengths[doc.id]
            tf = self._tf[doc.id]
            for term in query_tokens:
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                norm = freq + self._k1 * (
                    1.0 - self._b + self._b * doc_len / (self._avg_len or 1.0)
                )
                score += idf * (freq * (self._k1 + 1.0) / norm)
            result.append((doc.id, round(score, 8)))
        result.sort(key=lambda item: (-item[1], item[0]))
        return result
