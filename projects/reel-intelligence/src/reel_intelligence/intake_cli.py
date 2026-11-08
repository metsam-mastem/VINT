"""CLI for local file intake."""
from __future__ import annotations

import argparse
import json
import sys

from .intake import IntakeError, inspect_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ri-intake",
        description="Inspect and hash one supported local media file without copying it.",
    )
    parser.add_argument("input", help="Path to a local MP4, MP3, WAV, JPEG, PNG, or PDF file")
    parser.add_argument("--root", help="Optional permitted root directory for path containment")
    args = parser.parse_args(argv)
    try:
        asset = inspect_file(args.input, root=args.root)
    except (IntakeError, OSError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asset, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
