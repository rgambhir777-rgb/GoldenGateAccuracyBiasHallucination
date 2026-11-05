import json
import shutil

import pytest
from pydantic import ValidationError

from goldengate import paths
from goldengate.core.models import GoldenItem
from goldengate.golden import store

BASE = dict(id="x-1", question="What is the fee?", reference_answer="$12", key_facts=["$12"],
            gold_chunk_ids=["acc-everyday-checking#monthly-maintenance-fee"], category="accounts")


def test_schema_accepts_valid_item():
    item = GoldenItem.model_validate(BASE)
    assert item.answerable and not item.critical


@pytest.mark.parametrize("change", [
    {"key_facts": []},                                  # answerable without facts
    {"gold_chunk_ids": []},                             # answerable without gold chunks
    {"answerable": False},                              # unanswerable with gold chunks
    {"id": "Bad ID"},                                   # id pattern
    {"slices": {"zodiac": "leo"}},                      # unknown slice dimension
    {"difficulty": "extreme"},                          # enum
    {"unexpected": 1},                                  # extra fields forbidden
])
def test_schema_rejects_invalid_items(change):
    with pytest.raises(ValidationError):
        GoldenItem.model_validate({**BASE, **change})


def test_shipped_versions_validate():
    assert store.list_versions() == ["v1", "v2"]
    for version, count in (("v1", 150), ("v2", 190)):
        report = store.validate(version)
        assert report.ok, report.errors
        assert report.item_count == count
        assert store.load_manifest(version).frozen


def test_resolve_version():
    assert store.resolve_version("latest") == "v2"
    assert store.resolve_version("1") == "v1"
    with pytest.raises(store.GoldenError):
        store.resolve_version("v9")


def test_diff_v1_v2_shows_additions_and_label_fixes():
    d = store.diff("v1", "v2")
    assert len(d.added) == 40 and not d.removed
    assert set(d.changed) == {"fact-cashier", "fact-drive", "fact-mort-preapp", "fact-stop-pay", "fact-travel-notice"}
    assert d.details["fact-cashier"]["key_facts"] == {"before": ["$12"], "after": ["$10"]}
    assert d.unchanged == 145


def test_freeze_and_hash_check(workspace):
    root = workspace / "golden"
    shutil.copytree(paths.resource_root() / "golden" / "v1", root / "v1", dirs_exist_ok=True)
    assert store.validate("v1", root).ok
    # editing a frozen version must fail validation and refuse re-freezing
    items_file = root / "v1" / "items.jsonl"
    lines = items_file.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["reference_answer"] = "edited"
    lines[0] = json.dumps(row, sort_keys=True)
    items_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = store.validate("v1", root)
    assert not report.ok and "frozen" in report.errors[0]
    with pytest.raises(store.GoldenError):
        store.freeze("v1", root)


def test_create_new_version_then_freeze(workspace):
    root = workspace / "golden-new"
    root.mkdir()
    items = [GoldenItem.model_validate(BASE)]
    manifest = store.create_version("v3", items, ["test version"], parent="v2", root=root)
    assert not manifest.frozen
    assert store.validate("v3", root).ok
    frozen = store.freeze("v3", root)
    assert frozen.frozen and frozen.content_hash == store.content_hash("v3", root)
    with pytest.raises(store.GoldenError):
        store.create_version("v3", items, [], parent=None, root=root)


def test_validate_reports_bad_references(workspace):
    root = workspace / "golden-bad"
    root.mkdir()
    bad = GoldenItem.model_validate({**BASE, "gold_chunk_ids": ["no-such#chunk"]})
    cf_a = GoldenItem.model_validate({**BASE, "id": "cf-a", "counterfactual_group": "g1"})
    store.create_version("v1", [bad, bad, cf_a], [], parent=None, root=root)
    report = store.validate("v1", root)
    joined = " ".join(report.errors)
    assert "duplicate item id" in joined
    assert "does not exist in the corpus" in joined
    assert "fewer than 2 variants" in joined
    assert report.warnings == []
