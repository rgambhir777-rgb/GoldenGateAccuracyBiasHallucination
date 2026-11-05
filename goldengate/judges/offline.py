"""Deterministic offline judge (no API key required).

* **Key facts** - quantities (currency, percentages, times, phone numbers and
  plain numbers) must all appear in the answer; remaining words are matched
  with rapidfuzz. Negated facts ("no annual fee") require a negation in the
  answer.
* **Groundedness** - the answer is split into sentence-level claims. Each claim
  is compared with every sentence of the cited and retrieved chunks using
  content-word overlap. High overlap with matching quantities is *Supported*,
  high overlap with conflicting quantities is *Contradicted*, and anything else
  is *Unsupported*.
* **Citations** - a citation supports the answer when at least one claim is
  supported by that chunk; IDs that are not in the corpus are fabricated.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from rapidfuzz import fuzz

from goldengate.core.models import Chunk, ClaimJudgment, GoldenItem, ItemJudgment, KeyFactJudgment, Response
from goldengate.core.text import (
    content_tokens,
    extract_citations,
    extract_quantities,
    split_sentences,
    strip_citations,
)
from goldengate.judges.base import extract_decision, is_abstention, is_refusal

_NEGATIONS = frozenset({"no", "not", "never", "cannot", "zero", "without", "dont", "doesnt"})
_NEG_WORDS = re.compile(r"\b(no|not|never|cannot|zero|without|don't|doesn't|do not|does not)\b", re.I)


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9$%.:/ ]+", " ", text.lower()).split())


def _words(text: str) -> set[str]:
    return {t for t in content_tokens(text) if not any(ch.isdigit() for ch in t)}


def match_key_fact(fact: str, answer: str, threshold: float = 85.0) -> tuple[bool, float]:
    """Return (present, score in 0..1) for one key fact against an answer."""
    answer_clean = strip_citations(answer)
    fact_q = extract_quantities(fact)
    if _NEG_WORDS.search(fact) and not _NEG_WORDS.search(answer_clean):
        return False, 0.0
    if fact_q:
        answer_q = extract_quantities(answer_clean)
        q_score = len(fact_q & answer_q) / len(fact_q)
        words = _words(fact) - _NEGATIONS
        w_score = len(words & _words(answer_clean)) / len(words) if words else 1.0
        score = 0.7 * q_score + 0.3 * w_score
        return q_score == 1.0 and w_score >= 0.5, round(score, 3)
    ratio = fuzz.partial_ratio(_normalize(fact), _normalize(answer_clean))
    return ratio >= threshold, round(ratio / 100, 3)


class OfflineJudge:
    """Lexical/fuzzy judge that always works offline."""

    name = "offline"

    def __init__(self, chunks: Mapping[str, Chunk], support_overlap: float = 0.6,
                 contradiction_overlap: float = 0.5, fact_threshold: float = 85.0) -> None:
        self.chunks = chunks
        self.support_overlap = support_overlap
        self.contradiction_overlap = contradiction_overlap
        self.fact_threshold = fact_threshold
        self._sentences = {cid: [(s, set(content_tokens(s)), extract_quantities(s)) for s in split_sentences(c.text)]
                           for cid, c in chunks.items()}

    # ------------------------------------------------------------------ claims

    def judge_claim(self, claim: str, cited: list[str], evidence_ids: list[str]) -> ClaimJudgment:
        """Label one claim against the evidence chunks."""
        text = strip_citations(claim)
        tokens = set(content_tokens(text))
        quantities = extract_quantities(text)
        best = (0.0, "", "")
        supporting: list[str] = []
        for cid in evidence_ids:
            chunk_q = extract_quantities(self.chunks[cid].text) if cid in self.chunks else set()
            for sentence, s_tokens, s_q in self._sentences.get(cid, []):
                overlap = len(tokens & s_tokens) / len(tokens) if tokens else 0.0
                if overlap > best[0]:
                    best = (overlap, sentence, cid)
                if overlap >= self.support_overlap and quantities <= (s_q | chunk_q):
                    if cid not in supporting:
                        supporting.append(cid)
        score, evidence, _ = best
        if supporting:
            label = "supported"
        elif score >= self.contradiction_overlap and quantities:
            label = "contradicted"
        else:
            label = "unsupported"
        return ClaimJudgment(text=text, label=label, supporting_chunk_ids=supporting, cited_chunk_ids=cited,
                             evidence=evidence or None, score=round(score, 3))

    # ------------------------------------------------------------------ item

    def judge(self, item: GoldenItem, response: Response) -> ItemJudgment:
        answer = response.answer or ""
        clean = strip_citations(answer)
        abstained = is_abstention(clean)
        refused = is_refusal(clean)

        key_facts = []
        for fact in item.key_facts:
            present, score = match_key_fact(fact, answer, self.fact_threshold)
            key_facts.append(KeyFactJudgment(fact=fact, present=present and not refused, score=score))

        has_markers = bool(extract_citations(answer))
        retrieved_ids = [r.chunk_id for r in response.retrieved]
        claims: list[ClaimJudgment] = []
        for sentence in split_sentences(answer):
            plain = strip_citations(sentence)
            if not content_tokens(plain) or is_abstention(plain) or is_refusal(plain):
                continue
            cited = extract_citations(sentence) if has_markers else list(response.citations)
            evidence = list(dict.fromkeys([c for c in cited if c in self.chunks] + retrieved_ids))
            claims.append(self.judge_claim(sentence, cited, evidence))

        forbidden = [f for f in item.forbidden_claims
                     if fuzz.partial_ratio(_normalize(f), _normalize(clean)) >= 90]
        semantic = 0.0 if (abstained or refused) else fuzz.token_set_ratio(_normalize(clean),
                                                                         _normalize(item.reference_answer)) / 100
        return ItemJudgment(
            judge=self.name, key_facts=key_facts, semantic_match=round(semantic, 3), abstained=abstained,
            refused=refused, claims=claims, forbidden_hits=forbidden, decision=extract_decision(clean),
        )
