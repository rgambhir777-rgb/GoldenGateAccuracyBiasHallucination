#!/usr/bin/env bash
# GoldenGate one-command start for macOS/Linux: venv + install + demo data + dashboard at http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[GoldenGate] Python 3.11 or newer is required (https://www.python.org/downloads/)." >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[GoldenGate] Creating virtual environment..."
  "$PY" -m venv .venv
fi

echo "[GoldenGate] Installing dependencies (first run takes a minute)..."
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -q -e . -c requirements-lock.txt

echo "[GoldenGate] Seeding demo data (only if empty)..."
.venv/bin/python -m goldengate demo

echo "[GoldenGate] Starting dashboard (default http://localhost:8000)"
exec .venv/bin/python -m goldengate serve "$@"
