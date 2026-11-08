"""CLI for bounded FFmpeg temporal extraction."""
from __future__ import annotations

import argparse
import json
import sys

from .extraction import ExtractionError, extract_media


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ri-extract",
        description="Extract sampled JPEG frames and normalized mono WAV audio from local media.",
    )
    parser.add_argument("input", help="Local MP4, MP3, or WAV file")
    parser.add_argument("--output", required=True, help="New output directory; it must not already exist")
    parser.add_argument("--ffmpeg", help="Path or command name for the FFmpeg executable")
    parser.add_argument("--ffprobe", help="Path or command name for the FFprobe executable")
    parser.add_argument("--interval", type=float, default=5.0, help="Frame sampling interval in seconds (0.1–3600)")
    parser.add_argument("--max-frames", type=int, default=120, help="Maximum number of sampled frames (1–5000)")
    parser.add_argument("--max-duration", type=float, default=3600.0, help="Maximum media duration to process in seconds")
    parser.add_argument("--timeout", type=float, default=300.0, help="Maximum runtime for each FFmpeg operation")
    args = parser.parse_args(argv)
    try:
        result = extract_media(
            args.input,
            args.output,
            ffmpeg_path=args.ffmpeg,
            ffprobe_path=args.ffprobe,
            interval_seconds=args.interval,
            max_frames=args.max_frames,
            max_duration_seconds=args.max_duration,
            timeout_seconds=args.timeout,
        )
    except (ExtractionError, OSError) as exc:
        print(f"EXTRACTION FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
