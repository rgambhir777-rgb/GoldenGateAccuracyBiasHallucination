"""Retrieval quality against gold chunk IDs (separates retrieval from generation failures)."""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(retrieved: Sequence[str], gold: Sequence[str], k: int) -> float | None:
    """|gold ∩ top-k retrieved| / |gold|; ``None`` when there is no gold."""
    if not gold:
        return None
    top = set(retrieved[:k])
    return sum(1 for g in set(gold) if g in top) / len(set(gold))


def reciprocal_rank(retrieved: Sequence[str], gold: Sequence[str]) -> float | None:
    """1 / rank of the first gold chunk in the ranking (0 if absent); ``None`` without gold."""
    if not gold:
        return None
    gold_set = set(gold)
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in gold_set:
            return 1.0 / rank
    return 0.0
