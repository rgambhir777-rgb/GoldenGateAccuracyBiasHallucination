"""Citation quality: precision, recall, fabricated and missing citations."""

from __future__ import annotations

from collections.abc import Container, Sequence
from dataclasses import dataclass

from goldengate.core.models import ClaimJudgment


@dataclass(frozen=True)
class CitationStats:
    cited: list[str]
    supporting: int
    fabricated: int
    gold_cited: int
    missing: bool

    @property
    def precision(self) -> float | None:
        """Share of citations that support at least one claim (fabricated IDs never do)."""
        return self.supporting / len(self.cited) if self.cited else None


def citation_stats(cited: Sequence[str], claims: Sequence[ClaimJudgment], gold: Sequence[str],
                   known_ids: Container[str]) -> CitationStats:
    """Compute citation statistics for one answer.

    ``cited`` is the deduplicated list of chunk IDs the answer cites. A citation
    is *supporting* when some claim was supported by that chunk; *fabricated*
    when the ID does not exist in the corpus. ``missing`` is true when the
    answer makes claims but cites nothing at all.
    """
    unique = list(dict.fromkeys(cited))
    supported_by = {cid for claim in claims if claim.label == "supported" for cid in claim.supporting_chunk_ids}
    supporting = sum(1 for cid in unique if cid in supported_by)
    fabricated = sum(1 for cid in unique if cid not in known_ids)
    gold_cited = len(set(gold) & set(unique))
    return CitationStats(cited=unique, supporting=supporting, fabricated=fabricated, gold_cited=gold_cited,
                         missing=bool(claims) and not unique)
