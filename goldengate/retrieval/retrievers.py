"""Offline retrievers over corpus chunks: BM25 (default) and TF-IDF cosine."""

from __future__ import annotations

import math
from collections import Counter
from typing import Protocol, Sequence

from rank_bm25 import BM25Okapi

from goldengate.core.models import Chunk, RetrievedChunk
from goldengate.core.text import content_tokens


class Retriever(Protocol):
    """Anything that ranks chunks for a query."""

    name: str

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        """Return the top ``k`` chunks for ``query``, best first."""
        ...


class BM25Retriever:
    """Okapi BM25 over chunk title + heading + body."""

    name = "bm25"

    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = list(chunks)
        self.k1, self.b = k1, b
        self._bm25 = BM25Okapi([content_tokens(c.search_text) or ["_"] for c in self.chunks], k1=k1, b=b)

    def config(self) -> dict[str, object]:
        return {"retriever": self.name, "k1": self.k1, "b": self.b}

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        tokens = content_tokens(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(self.chunks)), key=lambda i: (-scores[i], self.chunks[i].chunk_id))
        return [
            RetrievedChunk(chunk_id=self.chunks[i].chunk_id, text=self.chunks[i].text,
                           score=round(float(scores[i]), 4), rank=rank + 1)
            for rank, i in enumerate(order[:k])
            if scores[i] > 0
        ]


class TfidfRetriever:
    """Sparse TF-IDF cosine similarity, implemented without external ML libraries."""

    name = "tfidf"

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = list(chunks)
        docs = [Counter(content_tokens(c.search_text)) for c in self.chunks]
        n = len(docs)
        df: Counter[str] = Counter()
        for doc in docs:
            df.update(doc.keys())
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        self.vectors = [self._weigh(doc) for doc in docs]

    def config(self) -> dict[str, object]:
        return {"retriever": self.name}

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self.idf.get(t, 0.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        q = self._weigh(Counter(content_tokens(query)))
        if not q:
            return []
        scores = [sum(w * vec.get(t, 0.0) for t, w in q.items()) for vec in self.vectors]
        order = sorted(range(len(self.chunks)), key=lambda i: (-scores[i], self.chunks[i].chunk_id))
        return [
            RetrievedChunk(chunk_id=self.chunks[i].chunk_id, text=self.chunks[i].text,
                           score=round(scores[i], 4), rank=rank + 1)
            for rank, i in enumerate(order[:k])
            if scores[i] > 0
        ]


def build_retriever(kind: str, chunks: Sequence[Chunk]) -> BM25Retriever | TfidfRetriever:
    """Factory used by systems and settings (``bm25`` or ``tfidf``)."""
    if kind == "tfidf":
        return TfidfRetriever(chunks)
    if kind == "bm25":
        return BM25Retriever(chunks)
    raise ValueError(f"Unknown retriever '{kind}' (expected bm25 or tfidf)")
