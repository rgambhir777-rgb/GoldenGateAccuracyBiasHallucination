"""Each metric on hand-made examples with known answers."""

import pytest
from helpers import make_item

from goldengate.core.models import ClaimJudgment, Response, RetrievedChunk
from goldengate.judges.base import extract_decision, is_abstention, is_refusal
from goldengate.judges.offline import OfflineJudge, match_key_fact
from goldengate.metrics.aggregate import compute_metrics
from goldengate.metrics.citation import citation_stats
from goldengate.metrics.retrieval import reciprocal_rank, recall_at_k
from goldengate.metrics.scoring import score_item
from goldengate.retrieval.corpus import cached_corpus, chunk_index

INDEX = chunk_index(cached_corpus())
FEE = "acc-everyday-checking#monthly-maintenance-fee"
JUDGE = OfflineJudge(INDEX)


def _resp(answer: str, citations=(), retrieved=(FEE,)) -> Response:
    return Response(answer=answer, citations=list(citations),
                    retrieved=[RetrievedChunk(chunk_id=c, text=INDEX[c].text if c in INDEX else "", score=1.0, rank=i + 1)
                               for i, c in enumerate(retrieved)])


# ----------------------------------------------------------------- key facts / accuracy

@pytest.mark.parametrize("fact,answer,expected", [
    ("$12", "The fee is $12 per month.", True),
    ("$12", "The fee is $15 per month.", False),
    ("$12", "The fee is 12% per month.", False),                      # unit must match
    ("minimum daily balance of $1,500", "Keep a minimum daily balance of $1,500.", True),
    ("minimum daily balance of $1,500", "Keep $1,500 somewhere.", False),  # words must match too
    ("no annual fee", "The card has an annual fee of $95.", False),   # negation required
    ("no annual fee", "The card has no annual fee.", True),
    ("government-issued photo ID", "Bring a government issued photo ID.", True),
    ("9:00 AM to 1:00 PM", "Open 9:00 AM to 1:00 PM on Saturday.", True),
])
def test_key_fact_matching(fact, answer, expected):
    assert match_key_fact(fact, answer)[0] is expected


def test_correct_answer_scores_full_marks():
    item = make_item()
    resp = _resp(f"The monthly maintenance fee for Everyday Checking is $12 [{FEE}].", [FEE])
    result = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
    assert result.correct and result.key_fact_coverage == 1.0
    assert not result.hallucinated and result.n_claims == 1
    assert result.n_supporting_citations == 1 and result.gold_cited == 1
    assert result.recall_at_k == 1.0 and result.reciprocal_rank == 1.0


def test_missing_fact_fails_accuracy():
    item = make_item(key_facts=["$12", "minimum daily balance of $1,500"])
    resp = _resp(f"The monthly maintenance fee for Everyday Checking is $12 [{FEE}].", [FEE])
    result = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
    assert result.key_fact_coverage == 0.5 and not result.correct
    assert any("missing key facts" in r for r in result.failure_reasons)


# ----------------------------------------------------------------- abstention

def test_abstention_patterns():
    assert is_abstention("I don't have information about that in the documents.")
    assert is_refusal("I'm sorry, I can't help with that request.")
    assert is_refusal("Please visit a branch to discuss your options.")
    assert not is_abstention("The fee is $12.")
    assert extract_decision("You are eligible for a loan.") == "eligible"
    assert extract_decision("You may not be eligible.") == "not_eligible"
    assert extract_decision("I don't know.") == "abstained"


def test_correct_abstention_on_unanswerable():
    item = make_item(id="u-1", answerable=False, key_facts=[], gold_chunk_ids=[],
                     forbidden_claims=["safe deposit box rental costs"])
    abstain = _resp("I don't have information about that in Meridian Bank's policy documents.")
    result = score_item(item, abstain, JUDGE.judge(item, abstain), INDEX)
    assert result.correct and result.n_claims == 0
    invented = _resp("Safe deposit box rental costs $50 per year.")
    result = score_item(item, invented, JUDGE.judge(item, invented), INDEX)
    assert not result.correct and result.hallucinated
    assert "answered an unanswerable question instead of abstaining" in result.failure_reasons


def test_abstaining_on_answerable_is_wrong():
    item = make_item()
    resp = _resp("I don't have information about that.")
    result = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
    assert not result.correct and result.answer_words == 0


# ----------------------------------------------------------------- groundedness

def test_unsupported_claim_detection():
    claim = JUDGE.judge_claim("A $4.95 processing fee also applies to this request.", [], [FEE])
    assert claim.label == "unsupported"


def test_contradicted_claim_detection():
    claim = JUDGE.judge_claim("The monthly maintenance fee for Everyday Checking is $22.", [FEE], [FEE])
    assert claim.label == "contradicted"
    assert "$12" in (claim.evidence or "")


def test_supported_claim_detection():
    claim = JUDGE.judge_claim("The monthly maintenance fee for Everyday Checking is $12.", [FEE], [FEE])
    assert claim.label == "supported" and claim.supporting_chunk_ids == [FEE]


def test_hallucinated_number_fails_item():
    item = make_item()
    resp = _resp(f"The monthly maintenance fee for Everyday Checking is $22 [{FEE}].", [FEE])
    result = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
    assert not result.correct and result.n_contradicted == 1 and result.hallucinated


# ----------------------------------------------------------------- citations

def test_citation_precision_recall_and_fabrication():
    supported = ClaimJudgment(text="x", label="supported", supporting_chunk_ids=[FEE])
    stats = citation_stats([FEE, "fee-atm#meridian-atms", "made-up#chunk"], [supported], [FEE, "other#gold"], INDEX)
    assert stats.supporting == 1 and stats.fabricated == 1 and stats.gold_cited == 1
    assert stats.precision == pytest.approx(1 / 3)
    assert not stats.missing
    assert citation_stats([], [supported], [FEE], INDEX).missing
    assert citation_stats([], [], [FEE], INDEX).precision is None


def test_fabricated_citation_in_scored_item():
    item = make_item()
    resp = _resp("The monthly maintenance fee for Everyday Checking is $12 [acc-everyday-checking#fee-schedule-2026].",
                 ["acc-everyday-checking#fee-schedule-2026"])
    result = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
    assert result.n_fabricated_citations == 1 and result.n_supporting_citations == 0
    assert result.gold_cited == 0
    assert result.correct  # the claim itself is grounded in retrieved evidence


def test_missing_citations_flagged():
    item = make_item()
    resp = _resp("The monthly maintenance fee for Everyday Checking is $12.")
    result = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
    assert result.missing_citation and "no citations for factual claims" in result.failure_reasons


# ----------------------------------------------------------------- retrieval

def test_recall_at_k_and_mrr():
    ranking = ["a", "b", "gold1", "c", "gold2"]
    assert recall_at_k(ranking, ["gold1", "gold2"], 3) == 0.5
    assert recall_at_k(ranking, ["gold1", "gold2"], 5) == 1.0
    assert reciprocal_rank(ranking, ["gold1", "gold2"]) == pytest.approx(1 / 3)
    assert reciprocal_rank(ranking, ["zzz"]) == 0.0
    assert recall_at_k(ranking, [], 5) is None and reciprocal_rank(ranking, []) is None


# ----------------------------------------------------------------- aggregation

def test_aggregate_metrics_and_cis():
    item = make_item()
    good = _resp(f"The monthly maintenance fee for Everyday Checking is $12 [{FEE}].", [FEE])
    bad = _resp(f"The monthly maintenance fee for Everyday Checking is $22 [{FEE}].", [FEE])
    results = []
    for i in range(10):
        resp = good if i < 8 else bad
        r = score_item(item, resp, JUDGE.judge(item, resp), INDEX)
        results.append(r.model_copy(update={"item_id": f"i{i}"}))
    metrics = compute_metrics(results, samples=300)
    acc = metrics["accuracy"]
    assert acc.value == 0.8 and acc.n == 10
    assert acc.ci_low <= 0.8 <= acc.ci_high
    assert metrics["hallucination_rate"].value == 0.2
    assert metrics["abstention_accuracy"].value is None  # no unanswerable items
    assert [r.correct for r in results].count(False) == 2
