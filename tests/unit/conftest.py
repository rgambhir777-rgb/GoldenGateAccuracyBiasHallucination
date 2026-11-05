"""Shared fixtures: isolated workspaces (empty or seeded with the demo releases)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from goldengate.releases import db

_ENV_KEYS = ("GOLDENGATE_WORKSPACE", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOLDENGATE_JUDGE_MODE",
             "GOLDENGATE_BOOTSTRAP_SAMPLES")


def _isolate(path: Path) -> dict[str, str | None]:
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    os.environ["GOLDENGATE_WORKSPACE"] = str(path)
    os.environ["GOLDENGATE_BOOTSTRAP_SAMPLES"] = "200"
    db.dispose_engines()
    return saved


def _restore(saved: dict[str, str | None]) -> None:
    db.dispose_engines()
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def workspace(tmp_path: Path) -> Iterator[Path]:
    """Empty, isolated workspace (database, runs, gates.yaml, .env, golden copy)."""
    saved = _isolate(tmp_path)
    yield tmp_path
    _restore(saved)


@pytest.fixture(scope="session")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Workspace seeded once with the full demo (four releases, baseline release_1.0)."""
    path = tmp_path_factory.mktemp("seeded")
    saved = _isolate(path)
    from goldengate.demo import seed_demo

    seed_demo()
    yield path
    _restore(saved)


@pytest.fixture()
def seeded_env(seeded: Path) -> Iterator[Path]:
    """Point the process at the seeded workspace for one test."""
    saved = _isolate(seeded)
    yield seeded
    _restore(saved)
