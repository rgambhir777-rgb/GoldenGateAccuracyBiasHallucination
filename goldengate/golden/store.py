"""Versioned golden datasets: loading, validation, diffing and freezing.

Layout::

    golden/
      v1/
        items.jsonl      one GoldenItem per line
        manifest.json    version, created, changelog, item_count, content_hash, frozen

Rules enforced here (and documented in the README):

* A version's ``content_hash`` is the SHA-256 of ``items.jsonl`` bytes.
* Once ``frozen`` is true, any edit to ``items.jsonl`` makes validation fail;
  changes must go into a new version with a changelog entry.
* Item IDs are unique within a version; gold chunk IDs must exist in the corpus.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from goldengate import paths
from goldengate.core.models import GoldenItem, GoldenManifest
from goldengate.retrieval.corpus import cached_corpus


class GoldenError(Exception):
    """Raised when a golden version cannot be loaded or fails integrity checks."""


def _root(root: Path | None) -> Path:
    return root or paths.golden_dir()


def list_versions(root: Path | None = None) -> list[str]:
    """All versions with a manifest, sorted numerically (v1, v2, ..., v10)."""
    base = _root(root)
    found = [p.name for p in base.iterdir() if (p / "manifest.json").exists()] if base.exists() else []

    def key(v: str) -> tuple[int, str]:
        digits = "".join(ch for ch in v if ch.isdigit())
        return (int(digits) if digits else 0, v)

    return sorted(found, key=key)


def latest_version(root: Path | None = None) -> str:
    versions = list_versions(root)
    if not versions:
        raise GoldenError("No golden versions found")
    return versions[-1]


def resolve_version(version: str | None, root: Path | None = None) -> str:
    """Accept ``v2``, ``2`` or ``latest``/``None``."""
    if version in (None, "", "latest"):
        return latest_version(root)
    version = version if version.startswith("v") else f"v{version}"
    if version not in list_versions(root):
        raise GoldenError(f"Golden version '{version}' not found (available: {', '.join(list_versions(root))})")
    return version


def items_path(version: str, root: Path | None = None) -> Path:
    return _root(root) / version / "items.jsonl"


def manifest_path(version: str, root: Path | None = None) -> Path:
    return _root(root) / version / "manifest.json"


def content_hash(version: str, root: Path | None = None) -> str:
    return hashlib.sha256(items_path(version, root).read_bytes()).hexdigest()


def load_manifest(version: str, root: Path | None = None) -> GoldenManifest:
    path = manifest_path(version, root)
    if not path.exists():
        raise GoldenError(f"Missing manifest for {version}")
    return GoldenManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_items(version: str, root: Path | None = None) -> list[GoldenItem]:
    """Load and schema-validate all items; raises :class:`GoldenError` on any problem."""
    path = items_path(version, root)
    if not path.exists():
        raise GoldenError(f"Missing items.jsonl for {version}")
    items: list[GoldenItem] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(GoldenItem.model_validate_json(line))
        except ValidationError as exc:
            raise GoldenError(f"{version} line {lineno}: {exc.errors()[0]['msg']}") from exc
    return items


@dataclass
class ValidationReport:
    version: str
    ok: bool
    item_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(version: str, root: Path | None = None, known_chunk_ids: set[str] | None = None) -> ValidationReport:
    """Schema, integrity and referential checks for one golden version."""
    report = ValidationReport(version=version, ok=False)
    try:
        manifest = load_manifest(version, root)
        items = load_items(version, root)
    except (GoldenError, ValidationError, json.JSONDecodeError) as exc:
        report.errors.append(str(exc))
        return report
    report.item_count = len(items)
    chunk_ids = known_chunk_ids if known_chunk_ids is not None else {c.chunk_id for c in cached_corpus()}

    actual_hash = content_hash(version, root)
    if manifest.frozen and actual_hash != manifest.content_hash:
        report.errors.append(
            f"{version} is frozen but items.jsonl was modified (hash {actual_hash[:12]} != "
            f"{manifest.content_hash[:12]}). Create a new version instead of editing a frozen one."
        )
    elif not manifest.frozen and actual_hash != manifest.content_hash:
        report.warnings.append(f"{version} is not frozen and its content hash is out of date; run 'golden freeze'.")
    if manifest.item_count != len(items):
        report.errors.append(f"manifest item_count {manifest.item_count} != {len(items)} items")

    seen: set[str] = set()
    groups: dict[str, list[GoldenItem]] = {}
    for item in items:
        if item.id in seen:
            report.errors.append(f"duplicate item id {item.id}")
        seen.add(item.id)
        for cid in item.gold_chunk_ids:
            if cid not in chunk_ids:
                report.errors.append(f"{item.id}: gold chunk '{cid}' does not exist in the corpus")
        if item.counterfactual_group:
            groups.setdefault(item.counterfactual_group, []).append(item)
    for group, members in groups.items():
        if len(members) < 2:
            report.errors.append(f"counterfactual group {group} has fewer than 2 variants")
        if len({tuple(m.key_facts) for m in members}) > 1 or len({m.expected_decision for m in members}) > 1:
            report.errors.append(f"counterfactual group {group} variants must share key facts and decision")
    report.ok = not report.errors
    return report


@dataclass
class GoldenDiff:
    a: str
    b: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, list[str]] = field(default_factory=dict)
    details: dict[str, dict[str, dict[str, object]]] = field(default_factory=dict)
    unchanged: int = 0


def diff(a: str, b: str, root: Path | None = None) -> GoldenDiff:
    """Items added, removed and changed (with the fields that changed) from ``a`` to ``b``."""
    old = {i.id: i for i in load_items(a, root)}
    new = {i.id: i for i in load_items(b, root)}
    result = GoldenDiff(a=a, b=b)
    result.added = sorted(set(new) - set(old))
    result.removed = sorted(set(old) - set(new))
    common = sorted(set(old) & set(new))
    for item_id in common:
        before, after = old[item_id].model_dump(), new[item_id].model_dump()
        fields = [k for k in before if before[k] != after[k]]
        if fields:
            result.changed[item_id] = fields
            result.details[item_id] = {f: {"before": before[f], "after": after[f]} for f in fields}
    result.unchanged = len(common) - len(result.changed)
    return result


def freeze(version: str, root: Path | None = None) -> GoldenManifest:
    """Record the current content hash and mark the version frozen.

    Refuses to re-freeze a frozen version whose content has changed, because
    that would silently bless an edit to a published dataset.
    """
    manifest = load_manifest(version, root)
    items = load_items(version, root)
    actual = content_hash(version, root)
    if manifest.frozen and manifest.content_hash != actual:
        raise GoldenError(f"{version} is already frozen and has been modified; create a new version instead")
    manifest.content_hash = actual
    manifest.item_count = len(items)
    manifest.frozen = True
    manifest_path(version, root).write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def create_version(version: str, items: list[GoldenItem], changelog: list[str], parent: str | None,
                   root: Path | None = None, description: str = "") -> GoldenManifest:
    """Write a new, unfrozen golden version (used by tests and dataset tooling)."""
    folder = _root(root) / version
    if folder.exists():
        raise GoldenError(f"Golden version {version} already exists")
    folder.mkdir(parents=True)
    body = "".join(json.dumps(i.model_dump(), sort_keys=True, ensure_ascii=False) + "\n" for i in items)
    (folder / "items.jsonl").write_text(body, encoding="utf-8", newline="\n")
    manifest = GoldenManifest(
        version=version, created=date.today().isoformat(), description=description, changelog=changelog,
        item_count=len(items), content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        frozen=False, parent=parent,
    )
    (folder / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest
