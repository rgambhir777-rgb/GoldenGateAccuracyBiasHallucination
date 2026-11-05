"""Load the Markdown policy corpus and split it into section-level chunks."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from goldengate import paths
from goldengate.core.models import Chunk

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def slugify(text: str) -> str:
    """'Monthly Maintenance Fee' -> 'monthly-maintenance-fee'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def chunk_markdown(markdown: str, fallback_id: str) -> list[Chunk]:
    """Split one document into chunks, one per ``##`` section.

    Chunk IDs are ``<doc id>#<section slug>`` so they stay stable when sections
    are reordered. Text before the first ``##`` heading becomes an ``overview``
    chunk if it contains prose.
    """
    meta: dict[str, str] = {}
    match = _FRONT_MATTER.match(markdown)
    body = markdown
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        body = markdown[match.end():]
    doc_id = str(meta.get("id") or fallback_id)
    title = str(meta.get("title") or doc_id)
    category = str(meta.get("category") or "general")

    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("# "):
            continue
        else:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    used: set[str] = set()
    for heading, lines in sections:
        text = " ".join(" ".join(lines).split())
        if not text:
            continue
        slug = slugify(heading) or "section"
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        chunks.append(
            Chunk(chunk_id=f"{doc_id}#{slug}", doc_id=doc_id, title=title, heading=heading,
                  category=category, text=text)
        )
    return chunks


def load_corpus(directory: Path | None = None) -> list[Chunk]:
    """Load and chunk every ``*.md`` file in the corpus directory (sorted, deterministic)."""
    directory = directory or paths.corpus_dir()
    chunks: list[Chunk] = []
    for file in sorted(directory.glob("*.md")):
        chunks.extend(chunk_markdown(file.read_text(encoding="utf-8"), file.stem))
    return chunks


@lru_cache(maxsize=4)
def cached_corpus(directory: str | None = None) -> tuple[Chunk, ...]:
    """Process-wide cached corpus keyed by directory path."""
    return tuple(load_corpus(Path(directory) if directory else None))


def chunk_index(chunks: tuple[Chunk, ...] | list[Chunk]) -> dict[str, Chunk]:
    return {c.chunk_id: c for c in chunks}
