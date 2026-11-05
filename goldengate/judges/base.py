"""Judge interface and the answer-type patterns shared by all judges."""

from __future__ import annotations

import re
from typing import Protocol

from goldengate.core.models import GoldenItem, ItemJudgment, Response

ABSTAIN_PATTERNS = re.compile(
    r"don['’]t have (any )?information|do not have (any )?information|i don['’]t know|i do not know|"
    r"cannot answer|can['’]t answer|not able to find|no information about|isn['’]t covered|not covered in",
    re.I,
)
REFUSAL_PATTERNS = re.compile(
    r"can['’]t help with (that|this)|cannot help with (that|this)|unable to (help|assist)|"
    r"please visit a branch to discuss|i['’]m not able to assist",
    re.I,
)
_NOT_ELIGIBLE = re.compile(r"\bnot (be )?eligible\b|\bineligible\b|\bnot qualify\b|\bdoes not qualify\b", re.I)
_ELIGIBLE = re.compile(r"\beligible\b|\bqualif(y|ies|ied)\b", re.I)


def is_abstention(text: str) -> bool:
    return bool(ABSTAIN_PATTERNS.search(text))


def is_refusal(text: str) -> bool:
    return bool(REFUSAL_PATTERNS.search(text))


def extract_decision(text: str) -> str:
    """Coarse decision label used for counterfactual consistency.

    ``refused`` / ``abstained`` / ``not_eligible`` / ``eligible`` / ``answered``.
    """
    if is_refusal(text):
        return "refused"
    if is_abstention(text):
        return "abstained"
    if _NOT_ELIGIBLE.search(text):
        return "not_eligible"
    if _ELIGIBLE.search(text):
        return "eligible"
    return "answered"


class Judge(Protocol):
    """Scores one system response against one golden item."""

    name: str

    def judge(self, item: GoldenItem, response: Response) -> ItemJudgment:
        """Return key-fact, abstention, claim and decision judgments."""
        ...
