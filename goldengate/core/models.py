"""Pydantic data models shared across the suite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ClaimLabel = Literal["supported", "contradicted", "unsupported"]
Difficulty = Literal["easy", "medium", "hard"]

SLICE_DIMENSIONS = ("gender", "ethnicity", "age_group", "language", "tier", "region", "disability")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- corpus


class Chunk(BaseModel):
    """A retrievable passage of a corpus document."""

    chunk_id: str
    doc_id: str
    title: str
    heading: str
    category: str
    text: str

    @property
    def search_text(self) -> str:
        return f"{self.title}. {self.heading}. {self.text}"


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    rank: int


# --------------------------------------------------------------------------- system output


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Response(BaseModel):
    """What a RAG system returns for one question."""

    answer: str
    citations: list[str] = Field(default_factory=list, description="Cited chunk IDs")
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    latency_ms: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    error: str | None = None


# --------------------------------------------------------------------------- golden set


class GoldenItem(BaseModel):
    """One labelled evaluation example."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]+$")
    question: str = Field(min_length=5)
    reference_answer: str
    key_facts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    gold_chunk_ids: list[str] = Field(default_factory=list)
    category: str
    difficulty: Difficulty = "medium"
    answerable: bool = True
    tags: list[str] = Field(default_factory=list)
    slices: dict[str, str] = Field(default_factory=dict)
    counterfactual_group: str | None = None
    expected_decision: str | None = None
    user_context: dict[str, Any] = Field(default_factory=dict)

    @property
    def critical(self) -> bool:
        return "critical" in self.tags

    @field_validator("slices")
    @classmethod
    def _known_dimensions(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - set(SLICE_DIMENSIONS)
        if unknown:
            raise ValueError(f"unknown slice dimensions: {sorted(unknown)}")
        return value

    @model_validator(mode="after")
    def _consistency(self) -> GoldenItem:
        if self.answerable:
            if not self.key_facts:
                raise ValueError("answerable items need at least one key fact")
            if not self.gold_chunk_ids:
                raise ValueError("answerable items need at least one gold chunk id")
        elif self.gold_chunk_ids:
            raise ValueError("unanswerable items must not have gold chunks")
        return self


class GoldenManifest(BaseModel):
    version: str
    created: str
    description: str = ""
    changelog: list[str] = Field(default_factory=list)
    item_count: int
    content_hash: str
    frozen: bool = False
    parent: str | None = None


# --------------------------------------------------------------------------- judgments


class ClaimJudgment(BaseModel):
    text: str
    label: ClaimLabel
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    cited_chunk_ids: list[str] = Field(default_factory=list)
    evidence: str | None = None
    score: float = 0.0


class KeyFactJudgment(BaseModel):
    fact: str
    present: bool
    score: float = 0.0


class ItemJudgment(BaseModel):
    """Raw judge output for one item, before metric aggregation."""

    judge: str
    key_facts: list[KeyFactJudgment] = Field(default_factory=list)
    semantic_match: float = 0.0
    abstained: bool = False
    refused: bool = False
    claims: list[ClaimJudgment] = Field(default_factory=list)
    forbidden_hits: list[str] = Field(default_factory=list)
    decision: str | None = None
    notes: list[str] = Field(default_factory=list)


class ItemResult(BaseModel):
    """Everything recorded about one golden item in one run."""

    item_id: str
    question: str
    category: str
    difficulty: str
    answerable: bool
    critical: bool
    slices: dict[str, str] = Field(default_factory=dict)
    counterfactual_group: str | None = None
    expected_decision: str | None = None
    reference_answer: str
    key_facts: list[str] = Field(default_factory=list)
    gold_chunk_ids: list[str] = Field(default_factory=list)
    response: Response
    judgment: ItemJudgment
    # per-item metric values
    correct: bool
    key_fact_coverage: float
    hallucinated: bool
    n_claims: int
    n_bad_claims: int
    n_contradicted: int
    n_citations: int
    n_supporting_citations: int
    n_fabricated_citations: int
    gold_cited: int
    missing_citation: bool
    recall_at_k: float | None
    reciprocal_rank: float | None
    answer_words: int
    failure_reasons: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- runs and releases


class MetricValue(BaseModel):
    name: str
    value: float | None
    ci_low: float | None = None
    ci_high: float | None = None
    n: int = 0


class ReleaseInfo(BaseModel):
    release_id: str
    version: str
    description: str = ""
    system: str
    model: str
    prompt_hash: str
    retriever_config: dict[str, Any] = Field(default_factory=dict)
    released_at: str | None = None


class RunMeta(BaseModel):
    run_id: str
    release: ReleaseInfo
    golden_version: str
    golden_hash: str
    git_commit: str
    judge_mode: str
    judges_used: dict[str, int] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    n_items: int = 0
    warnings: list[str] = Field(default_factory=list)
