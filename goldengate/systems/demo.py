"""Deterministic, offline demo RAG pipelines over the Meridian Bank corpus.

The "generator" is extractive: it retrieves chunks with BM25, picks the
sentences that best match the question and cites the chunk each sentence came
from. Four release configurations reproduce realistic drift:

* ``release_1.0`` - baseline. Two best sentences, abstains when retrieval does
  not cover the question.
* ``release_1.1`` - a *prompt change* ("be brief, always answer, mention fees").
  Sometimes truncates answers, invents fees, alters numbers, drops or invents
  citations and stops abstaining.
* ``release_1.2`` - a *model change*. Better answers overall (three sentences),
  but it reacts to segment cues in the question: non-native phrasing gets
  shorter answers or refusals, and retirees asking about loans are redirected
  to a branch instead of being answered.
* ``release_1.3`` - the fix: the 1.2 model with the bias removed.

Every perturbation is chosen with a stable hash of (seed, release, top chunk),
so runs are reproducible and counterfactual variants that retrieve the same
evidence receive the same treatment unless the release is deliberately biased.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from goldengate.core.models import Chunk, ReleaseInfo, Response, RetrievedChunk, TokenUsage
from goldengate.core.text import content_tokens, normalize_informal, split_sentences
from goldengate.retrieval.corpus import cached_corpus, chunk_index
from goldengate.retrieval.retrievers import build_retriever
from goldengate.systems.base import ABSTAIN_TEXT, RAGSystem, stable_hash

PROMPTS_DIR = Path(__file__).parent / "prompts"

REFUSAL_TEXT = "I'm sorry, I can't help with that request, so please visit a branch for assistance."
DEFLECTION_TEXT = (
    "Loan decisions depend on individual circumstances, so please visit a branch "
    "to discuss your options with an advisor."
)
FAKE_FEE_SENTENCE = "A $4.95 processing fee also applies to this request."

_NON_NATIVE_CUES = re.compile(r"my english|english is not|english not|\bpls\b|\bplz\b|sorry for my", re.I)
_RETIREE_CUES = re.compile(r"\bretire(e|d|ment)?\b|\bpension\b", re.I)


@dataclass(frozen=True)
class Perturbations:
    """Probabilities of the failure modes injected by the 1.1 prompt change."""

    answer_unanswerable: bool = False
    truncate: float = 0.0
    fake_fee: float = 0.0
    number_swap: float = 0.0
    drop_citations: float = 0.0
    fabricate_citation: float = 0.0
    wrong_citation: float = 0.0


@dataclass(frozen=True)
class DemoReleaseConfig:
    """Static description of one demo release."""

    release_id: str
    version: str
    description: str
    model: str
    prompt_file: str
    released_at: str
    n_sentences: int = 2
    candidate_chunks: int = 3
    min_coverage: float = 0.55
    segment_bias: bool = False
    perturb: Perturbations = field(default_factory=Perturbations)


DEMO_RELEASES: dict[str, DemoReleaseConfig] = {
    cfg.release_id: cfg
    for cfg in (
        DemoReleaseConfig(
            release_id="release_1.0", version="1.0",
            description="Baseline extractive assistant with strict citation and abstention rules.",
            model="meridian-extractive-1", prompt_file="demo_v1.md", released_at="2026-08-04",
        ),
        DemoReleaseConfig(
            release_id="release_1.1", version="1.1",
            description="Prompt change: 'be brief, always answer, mention fees'.",
            model="meridian-extractive-1", prompt_file="demo_v2.md", released_at="2026-08-25",
            perturb=Perturbations(answer_unanswerable=True, truncate=0.2, fake_fee=0.12, number_swap=0.08,
                                  drop_citations=0.12, fabricate_citation=0.08, wrong_citation=0.12),
        ),
        DemoReleaseConfig(
            release_id="release_1.2", version="1.2",
            description="Model change to meridian-extractive-2 (longer answers, better coverage).",
            model="meridian-extractive-2", prompt_file="demo_v1.md", released_at="2026-09-15",
            n_sentences=3, segment_bias=True,
        ),
        DemoReleaseConfig(
            release_id="release_1.3", version="1.3",
            description="Fix: meridian-extractive-2 with a fairness-hardened prompt.",
            model="meridian-extractive-2", prompt_file="demo_v3.md", released_at="2026-10-06",
            n_sentences=3,
        ),
    )
}


def core_query(question: str) -> str:
    """Keep only the interrogative sentences of a question.

    Customers often introduce themselves ("Hi, I'm Jamal. I'm retired.")
    before asking. Those statements do not change the policy answer, so the
    retriever only sees sentences that end with a question mark.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalize_informal(question)) if s.strip()]
    asked = [s for s in sentences if s.endswith("?")]
    return " ".join(asked or sentences)


def _unit(*parts: Any) -> float:
    """Stable pseudo-random number in [0, 1)."""
    return int(stable_hash(*parts, length=8), 16) / 16**8


class DemoRAGSystem(RAGSystem):
    """Extractive RAG pipeline configured by a :class:`DemoReleaseConfig`."""

    def __init__(self, config: DemoReleaseConfig, retriever: str = "bm25", top_k: int = 5,
                 seed: int = 7) -> None:
        self.config = config
        self.name = config.release_id
        self.top_k = top_k
        self.seed = seed
        self.chunks: tuple[Chunk, ...] = cached_corpus()
        self.index = chunk_index(self.chunks)
        self.retriever = build_retriever(retriever, self.chunks)
        self.prompt = (PROMPTS_DIR / config.prompt_file).read_text(encoding="utf-8")
        sentences = [content_tokens(s) for c in self.chunks for s in split_sentences(c.text)]
        df: Counter[str] = Counter()
        for tokens in sentences:
            df.update(set(tokens))
        self._idf = {t: math.log(1 + len(sentences) / d) for t, d in df.items()}

    # ------------------------------------------------------------------ metadata

    def release_info(self) -> ReleaseInfo:
        cfg = self.config
        retriever_config = {**self.retriever.config(), "top_k": self.top_k,
                            "candidate_chunks": cfg.candidate_chunks, "min_coverage": cfg.min_coverage}
        return ReleaseInfo(
            release_id=cfg.release_id, version=cfg.version, description=cfg.description,
            system="demo", model=cfg.model,
            prompt_hash=stable_hash(self.prompt, cfg.n_sentences, cfg.perturb.__dict__, cfg.segment_bias),
            retriever_config=retriever_config, released_at=cfg.released_at,
        )

    # ------------------------------------------------------------------ helpers

    def _chance(self, name: str, anchor: str) -> float:
        return _unit(self.seed, self.config.release_id, name, anchor)

    def _coverage(self, query: str, chunks: list[RetrievedChunk]) -> float:
        """Share of query content words found in the given chunks (abstention signal)."""
        terms = set(content_tokens(query))
        if not terms:
            return 0.0
        found: set[str] = set()
        for chunk in chunks:
            found |= set(content_tokens(self.index[chunk.chunk_id].search_text))
        return len(terms & found) / len(terms)

    def _select_sentences(self, query: str, retrieved: list[RetrievedChunk], n: int) -> list[tuple[str, str]]:
        """Chunk-first extraction: the top chunk's sentences, then the best others.

        The top-ranked chunk is quoted in document order (up to ``n`` sentences);
        remaining slots go to the sentences of the next candidate chunks with
        the highest IDF-weighted overlap with the query.
        """
        terms = set(content_tokens(query))
        top = retrieved[0]
        chosen = [(s, top.chunk_id) for s in split_sentences(top.text)][:n]
        scored: list[tuple[float, int, int, str, str]] = []
        for chunk in retrieved[1: self.config.candidate_chunks]:
            for pos, sentence in enumerate(split_sentences(chunk.text)):
                score = sum(self._idf.get(t, 0.0) for t in terms & set(content_tokens(sentence)))
                if score > 0:
                    scored.append((score, -chunk.rank, -pos, sentence, chunk.chunk_id))
        scored.sort(reverse=True)
        for _, _, _, sentence, chunk_id in scored:
            if len(chosen) >= n:
                break
            chosen.append((sentence, chunk_id))
        return chosen

    @staticmethod
    def _with_marker(sentence: str, chunk_id: str | None) -> str:
        if not chunk_id:
            return sentence
        body, punct = (sentence[:-1], sentence[-1]) if sentence[-1] in ".!?" else (sentence, ".")
        return f"{body} [{chunk_id}]{punct}"

    @staticmethod
    def _swap_number(sentence: str) -> str:
        match = re.search(r"\$(\d[\d,]*)", sentence)
        if match:
            value = int(match.group(1).replace(",", ""))
            return sentence[: match.start()] + f"${value + 10:,}" + sentence[match.end():]
        match = re.search(r"\b(\d+)\b", sentence)
        if match:
            return sentence[: match.start()] + str(int(match.group(1)) + 15) + sentence[match.end():]
        return sentence

    # ------------------------------------------------------------------ answering

    def answer(self, question: str, user_context: dict[str, Any] | None = None) -> Response:
        started = time.perf_counter()
        cfg, p = self.config, self.config.perturb
        query = core_query(question)
        retrieved = self.retriever.search(query, self.top_k)
        prompt_tokens = sum(len(c.text.split()) for c in retrieved) + len(self.prompt.split())

        def finish(answer: str, citations: list[str]) -> Response:
            return Response(
                answer=answer, citations=citations, retrieved=retrieved,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                usage=TokenUsage(prompt_tokens=int(prompt_tokens * 1.3),
                                 completion_tokens=int(len(answer.split()) * 1.3)),
            )

        if not retrieved:
            return finish(ABSTAIN_TEXT, [])
        anchor = retrieved[0].chunk_id
        covered = self._coverage(query, retrieved[:2]) >= cfg.min_coverage
        if not covered and not p.answer_unanswerable:
            return finish(ABSTAIN_TEXT, [])

        if cfg.segment_bias:
            if _RETIREE_CUES.search(question) and self.index[anchor].category == "loans":
                return finish(DEFLECTION_TEXT, [])
            if _NON_NATIVE_CUES.search(question):
                if self._chance("refuse", anchor) < 0.5:
                    return finish(REFUSAL_TEXT, [])
                n_sentences = 1
            else:
                n_sentences = cfg.n_sentences
        else:
            n_sentences = cfg.n_sentences
        if self._chance("truncate", anchor) < p.truncate:
            n_sentences = 1

        picked = self._select_sentences(query, retrieved, n_sentences)
        if not picked:
            return finish(ABSTAIN_TEXT, [])

        sentences = [s for s, _ in picked]
        cited = [c for _, c in picked]
        if self._chance("number_swap", anchor) < p.number_swap:
            sentences[0] = self._swap_number(sentences[0])
        if self._chance("wrong_citation", anchor) < p.wrong_citation:
            cited = [retrieved[-1].chunk_id for _ in cited]
        if self._chance("fabricate", anchor) < p.fabricate_citation:
            cited[0] = f"{self.index[anchor].doc_id}#fee-schedule-2026"
        drop = self._chance("drop_citations", anchor) < p.drop_citations
        parts = [self._with_marker(s, None if drop else c) for s, c in zip(sentences, cited)]
        if self._chance("fake_fee", anchor) < p.fake_fee or (not covered and p.answer_unanswerable):
            parts.append(FAKE_FEE_SENTENCE)
        citations = [] if drop else list(dict.fromkeys(cited))
        return finish(" ".join(parts), citations)


def demo_system(release_id: str, retriever: str = "bm25", top_k: int = 5, seed: int = 7) -> DemoRAGSystem:
    """Instantiate a demo release by ID (``release_1.0`` ... ``release_1.3``)."""
    if release_id not in DEMO_RELEASES:
        raise KeyError(f"Unknown demo release '{release_id}'. Choose from {sorted(DEMO_RELEASES)}")
    return DemoRAGSystem(DEMO_RELEASES[release_id], retriever=retriever, top_k=top_k, seed=seed)
