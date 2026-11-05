"""Aggregate metric catalogue with bootstrap confidence intervals.

Every metric is a ratio of per-item numerators and denominators, so one
bootstrap routine (resampling items) serves all of them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from goldengate.core.models import ItemResult, MetricValue
from goldengate.metrics.bootstrap import ratio_ci

Extractor = Callable[[ItemResult], tuple[float, float] | None]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    label: str
    higher_is_better: bool
    kind: str  # "rate" (0..1) or "value"
    group: str
    formula: str
    extract: Extractor


def _ans(fn: Callable[[ItemResult], tuple[float, float]]) -> Extractor:
    return lambda r: fn(r) if r.answerable else None


def _non_answer(r: ItemResult) -> bool:
    return r.judgment.abstained or r.judgment.refused


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec("accuracy", "Accuracy", True, "rate", "accuracy",
               "correct items / all items",
               lambda r: (float(r.correct), 1.0)),
    MetricSpec("key_fact_coverage", "Key-fact coverage", True, "rate", "accuracy",
               "mean(matched key facts / key facts) over answerable items",
               _ans(lambda r: (r.key_fact_coverage, 1.0))),
    MetricSpec("semantic_match", "Semantic match", True, "rate", "accuracy",
               "mean token-set similarity to the reference answer (answerable items)",
               _ans(lambda r: (r.judgment.semantic_match, 1.0))),
    MetricSpec("abstention_accuracy", "Correct abstention", True, "rate", "accuracy",
               "unanswerable items correctly declined / unanswerable items",
               lambda r: None if r.answerable else (float(r.correct), 1.0)),
    MetricSpec("false_refusal_rate", "False refusal rate", False, "rate", "accuracy",
               "answerable items abstained or refused / answerable items",
               _ans(lambda r: (float(_non_answer(r)), 1.0))),
    MetricSpec("hallucination_rate", "Hallucination rate (items)", False, "rate", "groundedness",
               "items with >=1 unsupported or contradicted claim / items with claims",
               lambda r: (float(r.hallucinated), 1.0) if r.n_claims else None),
    MetricSpec("claim_hallucination_rate", "Hallucination rate (claims)", False, "rate", "groundedness",
               "unsupported + contradicted claims / all claims",
               lambda r: (float(r.n_bad_claims), float(r.n_claims)) if r.n_claims else None),
    MetricSpec("contradiction_rate", "Contradiction rate (claims)", False, "rate", "groundedness",
               "contradicted claims / all claims",
               lambda r: (float(r.n_contradicted), float(r.n_claims)) if r.n_claims else None),
    MetricSpec("citation_precision", "Citation precision", True, "rate", "citations",
               "citations supporting a claim / all citations",
               lambda r: (float(r.n_supporting_citations), float(r.n_citations)) if r.n_citations else None),
    MetricSpec("citation_recall", "Citation recall", True, "rate", "citations",
               "gold chunks cited / gold chunks (answered, answerable items)",
               lambda r: (float(r.gold_cited), float(len(set(r.gold_chunk_ids))))
               if r.answerable and r.gold_chunk_ids and not _non_answer(r) else None),
    MetricSpec("missing_citation_rate", "Missing citations", False, "rate", "citations",
               "answers with claims but no citations / answers with claims",
               lambda r: (float(r.missing_citation), 1.0) if r.n_claims else None),
    MetricSpec("fabricated_citation_rate", "Fabricated citations", False, "rate", "citations",
               "cited IDs not in the corpus / all citations",
               lambda r: (float(r.n_fabricated_citations), float(r.n_citations)) if r.n_citations else None),
    MetricSpec("retrieval_recall_at_k", "Retrieval recall@k", True, "rate", "retrieval",
               "gold chunks in top-k / gold chunks",
               lambda r: (r.recall_at_k, 1.0) if r.recall_at_k is not None else None),
    MetricSpec("mrr", "MRR", True, "rate", "retrieval",
               "mean of 1 / rank of first gold chunk",
               lambda r: (r.reciprocal_rank, 1.0) if r.reciprocal_rank is not None else None),
    MetricSpec("avg_answer_words", "Avg answer length (words)", True, "value", "operational",
               "mean words per answered item",
               lambda r: (float(r.answer_words), 1.0) if not _non_answer(r) else None),
    MetricSpec("avg_latency_ms", "Avg latency (ms)", False, "value", "operational",
               "mean system latency",
               lambda r: (r.response.latency_ms, 1.0)),
    MetricSpec("avg_total_tokens", "Avg tokens", False, "value", "operational",
               "mean prompt + completion tokens",
               lambda r: (float(r.response.usage.total), 1.0)),
)
METRIC_BY_NAME = {m.name: m for m in METRICS}


def compute_metric(spec: MetricSpec, results: Sequence[ItemResult], samples: int = 1000,
                   seed: int = 7) -> MetricValue:
    pairs = [p for p in (spec.extract(r) for r in results) if p is not None]
    value, low, high = ratio_ci([p[0] for p in pairs], [p[1] for p in pairs], samples, seed)
    rnd = 4 if spec.kind == "rate" else 2
    return MetricValue(name=spec.name, value=None if value is None else round(value, rnd),
                       ci_low=None if low is None else round(low, rnd),
                       ci_high=None if high is None else round(high, rnd), n=len(pairs))


def compute_metrics(results: Sequence[ItemResult], samples: int = 1000, seed: int = 7) -> dict[str, MetricValue]:
    """All catalogue metrics for a run."""
    return {spec.name: compute_metric(spec, results, samples, seed) for spec in METRICS}
