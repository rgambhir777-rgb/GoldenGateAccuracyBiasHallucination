"""Filesystem locations for bundled resources and the writable workspace.

Two roots are distinguished:

* **resource root** - read-only inputs shipped with the project (corpus, golden
  sets, rubrics, the built dashboard). In a source checkout this is the
  repository root; inside a PyInstaller bundle it is ``sys._MEIPASS``.
* **workspace** - writable state (SQLite database, run JSON files, ``.env``,
  ``gates.yaml``). In a source checkout this is also the repository root; for
  the frozen executable it is the folder that contains ``GoldenGate.exe``.

Both can be overridden with ``GOLDENGATE_ROOT`` and ``GOLDENGATE_WORKSPACE``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Directory holding corpus/, golden/, rubrics/ and frontend/dist/."""
    env = os.environ.get("GOLDENGATE_ROOT")
    if env:
        return Path(env).resolve()
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return _PACKAGE_DIR.parent


def workspace() -> Path:
    """Writable directory for the database, run outputs and editable config."""
    env = os.environ.get("GOLDENGATE_WORKSPACE")
    if env:
        path = Path(env).resolve()
    elif is_frozen():
        path = Path(sys.executable).resolve().parent / "goldengate_workspace"
    else:
        path = _PACKAGE_DIR.parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def corpus_dir() -> Path:
    return resource_root() / "corpus"


def golden_dir() -> Path:
    """Golden sets live in the workspace when frozen so they can be frozen/edited."""
    target = workspace() / "golden"
    source = resource_root() / "golden"
    if not target.exists() and source.exists() and source != target:
        shutil.copytree(source, target)
    return target if target.exists() else source


def rubrics_dir() -> Path:
    return resource_root() / "rubrics"


def frontend_dist() -> Path:
    return resource_root() / "frontend" / "dist"


def data_dir() -> Path:
    path = workspace() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    path = data_dir() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = data_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "goldengate.db"


def env_file() -> Path:
    return workspace() / ".env"


def gates_file() -> Path:
    """Editable gate config; seeded from the bundled default when missing."""
    target = workspace() / "gates.yaml"
    source = resource_root() / "gates.yaml"
    if not target.exists() and source.exists() and source != target:
        shutil.copyfile(source, target)
    return target


def baselines_dir() -> Path:
    path = workspace() / "baselines"
    path.mkdir(parents=True, exist_ok=True)
    return path
