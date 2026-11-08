"""CLI for FFprobe-based local media metadata inspection."""
from __future__ import annotations

import argparse
import json
import sys

from .probe import ProbeError, probe_media


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ri-probe",
        description="Extract container and stream metadata from a local audio/video file using FFprobe.",
    )
    parser.add_argument("input", help="Local MP4, MP3, or WAV file")
    parser.add_argument("--root", help="Optional permitted root directory")
    parser.add_argument("--ffprobe", help="Path or command name for the FFprobe executable")
    parser.add_argument("--timeout", type=float, default=20.0, help="Maximum FFprobe runtime in seconds")
    args = parser.parse_args(argv)
    try:
        result = probe_media(
            args.input,
            ffprobe_path=args.ffprobe,
            root=args.root,
            timeout_seconds=args.timeout,
        )
    except (ProbeError, OSError) as exc:
        print(f"PROBE FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
