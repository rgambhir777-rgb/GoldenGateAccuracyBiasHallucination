"""Factories for hand-made golden items and item results used across unit tests."""

from __future__ import annotations

from goldengate.core.models import (
    ClaimJudgment,
    GoldenItem,
    ItemJudgment,
    ItemResult,
    KeyFactJudgment,
    Response,
    RetrievedChunk,
)


def make_item(**overrides) -> GoldenItem:
    data = dict(
        id="t-item", question="What is the monthly maintenance fee for Everyday Checking?",
        reference_answer="The fee is $12.", key_facts=["$12"],
        gold_chunk_ids=["acc-everyday-checking#monthly-maintenance-fee"], category="accounts",
    )
    data.update(overrides)
    return GoldenItem.model_validate(data)


def make_result(item_id: str = "r", correct: bool = True, slices: dict[str, str] | None = None,
                group: str | None = None, refused: bool = False, facts: tuple[str, ...] = ("$12",),
                present: bool = True, decision: str = "answered", hallucinated: bool = False,
                words: int = 10, critical: bool = False) -> ItemResult:
    """Minimal ItemResult for fairness/gate tests."""
    judgment = ItemJudgment(
        judge="offline", key_facts=[KeyFactJudgment(fact=f, present=present) for f in facts],
        refused=refused, decision="refused" if refused else decision,
        claims=[ClaimJudgment(text="x", label="unsupported" if hallucinated else "supported")],
    )
    return ItemResult(
        item_id=item_id, question="q?", category="accounts", difficulty="easy", answerable=True,
        critical=critical, slices=slices or {}, counterfactual_group=group, reference_answer="ref",
        key_facts=list(facts), gold_chunk_ids=["a#b"],
        response=Response(answer="I'm sorry, I can't help with that." if refused else "ans",
                          retrieved=[RetrievedChunk(chunk_id="a#b", text="t", score=1.0, rank=1)]),
        judgment=judgment, correct=correct, key_fact_coverage=1.0 if present else 0.0, hallucinated=hallucinated,
        n_claims=1, n_bad_claims=int(hallucinated), n_contradicted=0, n_citations=1, n_supporting_citations=1,
        n_fabricated_citations=0, gold_cited=1, missing_citation=False, recall_at_k=1.0, reciprocal_rank=1.0,
        answer_words=0 if refused else words,
    )
