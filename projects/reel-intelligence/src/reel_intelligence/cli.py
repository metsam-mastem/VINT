"""Command-line entry point for canonical JSON contract validation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contracts import ContractError, validate_bundle, validate_record


def _load(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ri-validate",
        description="Validate a REEL INTELLIGENCE record or a JSON array of linked records.",
    )
    parser.add_argument("input", help="JSON file path, or '-' to read stdin")
    args = parser.parse_args()
    try:
        payload = _load(args.input)
        if isinstance(payload, list):
            result = validate_bundle(payload)
            count = len(result)
        else:
            validate_record(payload)
            count = 1
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(f"VALID: {count} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
