"""CLI for local file and directory intake."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .intake import IntakeError, inspect_directory, inspect_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ri-intake",
        description="Inspect and hash supported local media files without copying them.",
    )
    parser.add_argument("input", help="Path to a local file or directory")
    parser.add_argument("--root", help="Optional permitted root directory for a single-file path")
    parser.add_argument("--no-recursive", action="store_true", help="Do not scan nested directories")
    args = parser.parse_args(argv)
    try:
        if Path(args.input).is_dir():
            if args.root is not None:
                raise IntakeError("--root applies only to single-file intake")
            assets = inspect_directory(args.input, recursive=not args.no_recursive)
            if not assets:
                raise IntakeError("no supported media files found")
            result = assets
        else:
            if args.no_recursive:
                raise IntakeError("--no-recursive is only valid for directory intake")
            result = inspect_file(args.input, root=args.root)
    except (IntakeError, OSError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
