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


class BM25Corpus:
    """Reusable deterministic BM25 corpus with pre-tokenized documents.

    The expensive document tokenization/term-frequency work is performed once. Each query only
    computes document-frequency values for the query terms across the selected document subset.
    This preserves the same BM25 semantics as constructing a fresh scorer over that subset while
    making repeated queries over a stable corpus substantially cheaper.
    """

    def __init__(self, documents: list[BM25Document], *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self._documents = tuple(documents)
        self._k1 = k1
        self._b = b
        self._tf = {doc.id: Counter(tokenize(doc.text)) for doc in documents}
        self._lengths = {
            doc.id: sum(self._tf[doc.id].values()) for doc in documents
        }

    def score(
        self,
        query: str,
        *,
        document_ids: tuple[str, ...] | list[str] | None = None,
    ) -> list[tuple[str, float]]:
        if document_ids is None:
            documents = self._documents
        else:
            selected = set(document_ids)
            documents = tuple(doc for doc in self._documents if doc.id in selected)
        if not documents:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return [(doc.id, 0.0) for doc in documents]

        n_docs = len(documents)
        total_len = sum(self._lengths[doc.id] for doc in documents)
        avg_len = total_len / n_docs
        query_terms = tuple(dict.fromkeys(query_tokens))
        df = {
            term: sum(1 for doc in documents if self._tf[doc.id].get(term, 0) > 0)
            for term in query_terms
        }

        result: list[tuple[str, float]] = []
        for doc in documents:
            score = 0.0
            doc_len = self._lengths[doc.id]
            tf = self._tf[doc.id]
            for term in query_tokens:
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                term_df = df[term]
                idf = math.log(1.0 + (n_docs - term_df + 0.5) / (term_df + 0.5))
                norm = freq + self._k1 * (
                    1.0 - self._b + self._b * doc_len / (avg_len or 1.0)
                )
                score += idf * (freq * (self._k1 + 1.0) / norm)
            result.append((doc.id, round(score, 8)))
        result.sort(key=lambda item: (-item[1], item[0]))
        return result


class BM25Scorer:
    """Compatibility wrapper for one bounded BM25 corpus."""

    def __init__(self, documents: list[BM25Document], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._corpus = BM25Corpus(documents, k1=k1, b=b)

    def score(self, query: str) -> list[tuple[str, float]]:
        return self._corpus.score(query)
