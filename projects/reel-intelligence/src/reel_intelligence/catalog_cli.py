"""CLI for the local REEL INTELLIGENCE SQLite asset catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import AssetCatalog, CatalogError
from .intake import IntakeError, inspect_directory, inspect_file
from .probe import ProbeError, probe_media


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ri-catalog",
        description="Manage a local SQLite catalog of canonical REEL INTELLIGENCE Asset records.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create or verify a catalog database")
    init.add_argument("--db", required=True, help="SQLite database path")

    add = commands.add_parser("add", help="Intake a file or directory into the catalog")
    add.add_argument("input", help="Local file or directory")
    add.add_argument("--db", required=True, help="SQLite database path")
    add.add_argument("--root", help="Optional permitted root for a single-file path")
    add.add_argument("--no-recursive", action="store_true", help="Scan only the top-level directory")
    add.add_argument("--probe", action="store_true", help="Run FFprobe for a single audio/video file")
    add.add_argument("--ffprobe", help="Path or command name for FFprobe")
    add.add_argument("--timeout", type=float, default=20.0, help="FFprobe timeout in seconds")

    listing = commands.add_parser("list", help="List cataloged assets")
    listing.add_argument("--db", required=True, help="SQLite database path")
    listing.add_argument("--media-type", choices=["video", "audio", "image", "document", "text", "archive", "other"])
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)

    show = commands.add_parser("show", help="Show one asset and its probe metadata")
    show.add_argument("asset_id")
    show.add_argument("--db", required=True, help="SQLite database path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        catalog = AssetCatalog(args.db)
        if args.command == "init":
            result = {"status": "ready", "database": str(Path(args.db).resolve())}
        elif args.command == "add":
            source = Path(args.input)
            if source.is_dir():
                if args.root is not None or args.probe:
                    raise CatalogError("--root and --probe are supported only for single-file intake")
                if args.no_recursive:
                    assets = inspect_directory(source, recursive=False)
                else:
                    assets = inspect_directory(source)
                if not assets:
                    raise CatalogError("no supported media files found")
                inserted = sum(1 for asset in assets if catalog.add_asset(asset))
                result = {"discovered": len(assets), "inserted": inserted, "duplicates": len(assets) - inserted}
            else:
                if args.no_recursive:
                    raise CatalogError("--no-recursive is only valid for directory intake")
                if args.probe:
                    probed = probe_media(
                        args.input,
                        ffprobe_path=args.ffprobe,
                        root=args.root,
                        timeout_seconds=args.timeout,
                    )
                    asset = probed["asset"]
                    is_new = catalog.add_asset(asset, probe=probed["probe"])
                else:
                    asset = inspect_file(args.input, root=args.root)
                    is_new = catalog.add_asset(asset)
                result = {"inserted": is_new, "asset_id": asset["asset_id"], "filename": asset["filename"]}
        elif args.command == "list":
            result = catalog.list_assets(
                media_type=args.media_type,
                limit=args.limit,
                offset=args.offset,
            )
        else:
            result = catalog.get_asset(args.asset_id)
            if result is None:
                raise CatalogError(f"asset not found: {args.asset_id}")
    except (CatalogError, IntakeError, ProbeError, OSError) as exc:
        print(f"CATALOG ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
