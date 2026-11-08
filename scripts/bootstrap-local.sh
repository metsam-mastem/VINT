#!/usr/bin/env bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="$ROOT/projects/reel-intelligence"
VENV="$(printenv RI_VENV 2>/dev/null || true)"
PYTHON_BIN="$(printenv PYTHON 2>/dev/null || true)"
if [[ -z "$VENV" ]]; then VENV="$PROJECT/.venv"; fi
if [[ -z "$PYTHON_BIN" ]]; then PYTHON_BIN="python3"; fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.10+ was not found. Set PYTHON to a compatible interpreter." >&2
  exit 2
fi

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)' || {
  echo "Python 3.10 or newer is required." >&2
  exit 2
}

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e "$PROJECT[dev]"

echo
echo "REEL INTELLIGENCE Python environment is ready."
echo "Activate with: source \"$VENV/bin/activate\""
echo "Run tests with: \"$VENV/bin/python\" -m pytest -q \"$PROJECT/tests\""
echo "Check optional tools with: bash \"$ROOT/scripts/check-local-tools.sh\""
echo "Run analysis with: \"$VENV/bin/ri-analyze\" INPUT --output OUTPUT"
