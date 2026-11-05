"""Shared text utilities: tokenization, sentence splitting and quantity extraction."""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """
    a an the and or but if then so of to in on at by for with from into onto about as is are was
    were be been being do does did doing have has had having i me my mine we us our you your yours
    he she it its they them their this that these those there here what which who whom whose when
    where why how can could should would will shall may might must not no nor than too very just
    also any all each every some such own same other only both more most much many please tell
    know want need get got let im ive id am pm et hi hello hey thanks thank sorry okay ok kindly
    help like way still really one does dont doesnt cant isnt arent meridian bank long quickly take
    soon
    """.split()
)

# Informal spellings normalized before retrieval (common in chat-style questions).
INFORMAL = {
    "pls": "please",
    "plz": "please",
    "u": "you",
    "ur": "your",
    "wat": "what",
    "wht": "what",
    "abt": "about",
    "hw": "how",
    "thx": "thanks",
    "acct": "account",
}

_WORD = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_CITATION = re.compile(r"\s*\[([A-Za-z0-9_\-]+#[A-Za-z0-9_\-]+)\]")

_PHONE = re.compile(r"\b1-\d{3}-\d{3}-\d{4}\b")
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]\.?")
_CURRENCY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_NUMBER = re.compile(r"(?<![\w.$])(\d[\d,]*(?:\.\d+)?)(?![\d%])")


def stem(token: str) -> str:
    """Light suffix stripping so 'fees'/'fee' and 'removing'/'remove' share a stem."""
    if token.isdigit():
        return token
    if len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed") and not token.endswith("eed"):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")):
        token = token[:-1]
    if len(token) > 3 and token.endswith("e"):
        token = token[:-1]
    return token


_INFORMAL_WORD = re.compile(r"\b[A-Za-z]+\b")


def normalize_informal(text: str) -> str:
    """Expand common informal spellings (``pls`` -> ``please``)."""
    return _INFORMAL_WORD.sub(lambda m: INFORMAL.get(m.group(0).lower(), m.group(0)), text)


def content_tokens(text: str) -> list[str]:
    """Stemmed tokens with stopwords removed (order preserved, duplicates kept).

    Stopwords are removed before stemming so that e.g. 'does' never becomes 'doe'.
    """
    words = _WORD.findall(normalize_informal(text).lower().replace("’", "'"))
    out: list[str] = []
    for word in words:
        word = word.replace("'", "")
        if word in STOPWORDS or (len(word) < 2 and not word.isdigit()):
            continue
        out.append(stem(word))
    return out


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences; keeps citation markers attached to their sentence."""
    text = " ".join(text.split())
    if not text:
        return []
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def extract_citations(text: str) -> list[str]:
    """Return chunk IDs referenced as ``[doc-id#section]`` markers, in order, deduplicated."""
    seen: list[str] = []
    for match in _CITATION.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def strip_citations(text: str) -> str:
    """Remove ``[doc#section]`` markers from text."""
    return _CITATION.sub("", text).strip()


def _num(value: str) -> str:
    cleaned = value.replace(",", "")
    try:
        number = float(cleaned)
    except ValueError:
        return cleaned
    return str(int(number)) if number.is_integer() else f"{number:g}"


def extract_quantities(text: str) -> set[str]:
    """Extract normalized quantities: currency, percentages, times, phone numbers, numbers.

    Each quantity is returned as a typed string such as ``$1500``, ``3.75%``,
    ``09:00am``, ``tel:18005550100`` or ``#60`` so that ``$3`` and ``3%`` are
    never considered equal.
    """
    found: set[str] = set()
    remaining = text
    for match in _PHONE.findall(remaining):
        found.add("tel:" + match.replace("-", ""))
    remaining = _PHONE.sub(" ", remaining)
    for hour, minute, half in _TIME.findall(remaining):
        found.add(f"{int(hour):02d}:{minute}{half.lower()}m")
    remaining = _TIME.sub(" ", remaining)
    for value in _CURRENCY.findall(remaining):
        found.add("$" + _num(value))
    remaining = _CURRENCY.sub(" ", remaining)
    for value in _PERCENT.findall(remaining):
        found.add(_num(value) + "%")
    remaining = _PERCENT.sub(" ", remaining)
    for value in _NUMBER.findall(remaining):
        found.add("#" + _num(value))
    return found


def word_count(text: str) -> int:
    """Number of whitespace-separated words after removing citation markers."""
    return len(strip_citations(text).split())
