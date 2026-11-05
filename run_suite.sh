#!/usr/bin/env bash
# Run the regression suite and release gates in the terminal.
# Usage: ./run_suite.sh [release_1.0|release_1.1|release_1.2|release_1.3|llm] [golden version]
# Exit code: 0 = SHIP, 1 = BLOCKED, 2 = error.
set -uo pipefail
cd "$(dirname "$0")"
SYSTEM="${1:-release_1.3}"
GOLDEN="${2:-v2}"
export PYTHONIOENCODING=utf-8

if [ ! -x ".venv/bin/python" ]; then
  echo "[GoldenGate] Creating virtual environment..."
  python3 -m venv .venv || exit 2
  .venv/bin/python -m pip install --disable-pip-version-check -q -e . -c requirements-lock.txt || exit 2
fi
GG=".venv/bin/python -m goldengate"

$GG golden validate || exit 2
if ! $GG baseline show >/dev/null 2>&1; then
  $GG run --system release_1.0 --golden "$GOLDEN" >/dev/null || exit 2
  $GG baseline set --release release_1.0 || exit 2
fi
$GG run --system "$SYSTEM" --golden "$GOLDEN" || exit 2
$GG compare --baseline baseline --current "$SYSTEM"
$GG report --run "$SYSTEM" --format html
$GG gate --run "$SYSTEM"
