#!/usr/bin/env bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="$ROOT/projects/reel-intelligence"
VENV="$(printenv RI_VENV 2>/dev/null || true)"
if [[ -z "$VENV" ]]; then VENV="$PROJECT/.venv"; fi
LOCAL_CLI="$VENV/bin/ri-analyze"

if [[ -x "$LOCAL_CLI" ]]; then
  exec "$LOCAL_CLI" "$@"
fi

if command -v ri-analyze >/dev/null 2>&1; then
  exec ri-analyze "$@"
fi

echo "ri-analyze is not installed. Run: bash \"$ROOT/scripts/bootstrap-local.sh\"" >&2
exit 2
