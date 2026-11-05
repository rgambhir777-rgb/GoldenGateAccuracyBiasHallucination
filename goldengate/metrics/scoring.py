"""Turn (item, response, judgment) into a fully scored :class:`ItemResult`."""

from __future__ import annotations

from collections.abc import Container

from goldengate.core.models import GoldenItem, ItemJudgment, ItemResult, Response
from goldengate.core.text import extract_citations, word_count
from goldengate.metrics.citation import citation_stats
from goldengate.metrics.retrieval import recall_at_k, reciprocal_rank

COVERAGE_THRESHOLD = 0.75


def score_item(item: GoldenItem, response: Response, judgment: ItemJudgment, known_ids: Container[str],
               k: int = 5, coverage_threshold: float = COVERAGE_THRESHOLD) -> ItemResult:
    """Score one answer.

    An answerable item is **correct** when the system answered (no abstention or
    refusal), covered at least ``coverage_threshold`` of the key facts, made no
    contradicted claims and stated no forbidden claim. An unanswerable item is
    correct when the system abstained (or declined) without a forbidden claim.
    """
    non_answer = judgment.abstained or judgment.refused
    matched = sum(1 for f in judgment.key_facts if f.present)
    coverage = matched / len(item.key_facts) if item.key_facts else 0.0
    bad = [c for c in judgment.claims if c.label != "supported"]
    contradicted = [c for c in judgment.claims if c.label == "contradicted"]
    cited = list(dict.fromkeys(list(response.citations) + extract_citations(response.answer)))
    stats = citation_stats(cited, judgment.claims, item.gold_chunk_ids, known_ids)
    retrieved_ids = [r.chunk_id for r in response.retrieved]

    reasons: list[str] = []
    if response.error:
        reasons.append(f"system error: {response.error}")
    if item.answerable:
        if judgment.abstained:
            reasons.append("abstained on an answerable question")
        if judgment.refused:
            reasons.append("refused or redirected an answerable question")
        missed = [f.fact for f in judgment.key_facts if not f.present]
        if missed and not non_answer:
            reasons.append("missing key facts: " + "; ".join(missed))
        correct = (not non_answer and coverage >= coverage_threshold and not contradicted
                   and not judgment.forbidden_hits and not response.error)
    else:
        if not non_answer:
            reasons.append("answered an unanswerable question instead of abstaining")
        correct = non_answer and not judgment.forbidden_hits
    if contradicted:
        reasons.append(f"{len(contradicted)} contradicted claim(s)")
    if len(bad) > len(contradicted):
        reasons.append(f"{len(bad) - len(contradicted)} unsupported claim(s)")
    if judgment.forbidden_hits:
        reasons.append("forbidden claim: " + "; ".join(judgment.forbidden_hits))
    if stats.fabricated:
        reasons.append(f"{stats.fabricated} fabricated citation(s)")
    if stats.missing:
        reasons.append("no citations for factual claims")

    return ItemResult(
        item_id=item.id, question=item.question, category=item.category, difficulty=item.difficulty,
        answerable=item.answerable, critical=item.critical, slices=item.slices,
        counterfactual_group=item.counterfactual_group, expected_decision=item.expected_decision,
        reference_answer=item.reference_answer, key_facts=item.key_facts, gold_chunk_ids=item.gold_chunk_ids,
        response=response, judgment=judgment, correct=correct, key_fact_coverage=round(coverage, 4),
        hallucinated=bool(bad), n_claims=len(judgment.claims), n_bad_claims=len(bad),
        n_contradicted=len(contradicted), n_citations=len(stats.cited), n_supporting_citations=stats.supporting,
        n_fabricated_citations=stats.fabricated, gold_cited=stats.gold_cited, missing_citation=stats.missing,
        recall_at_k=recall_at_k(retrieved_ids, item.gold_chunk_ids, k),
        reciprocal_rank=reciprocal_rank(retrieved_ids, item.gold_chunk_ids),
        answer_words=0 if non_answer else word_count(response.answer), failure_reasons=reasons,
    )
