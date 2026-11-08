"""Command-line interface for local multimodal evidence analysis."""
from __future__ import annotations

import argparse
import json
import sys

from .analysis import AnalysisError, analyze_media


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ri-analyze",
        description="Run available local OCR, PDF text, ASR, scene and temporal processors.",
    )
    parser.add_argument("input", help="One supported local media file")
    parser.add_argument("--output", required=True, help="New output directory for analysis.json and derived media")
    parser.add_argument("--tesseract", help="Path or command name for Tesseract")
    parser.add_argument("--pdftotext", help="Path or command name for Poppler pdftotext")
    parser.add_argument("--whisper-model", help="Local whisper.cpp model file; no model is downloaded automatically")
    parser.add_argument("--whisper-cli", help="Path or command name for whisper.cpp whisper-cli")
    parser.add_argument("--ffmpeg", help="Path or command name for FFmpeg")
    parser.add_argument("--ffprobe", help="Path or command name for FFprobe")
    parser.add_argument("--ocr-languages", default="eng", help="Tesseract language set, e.g. eng+fas")
    parser.add_argument("--no-scenes", action="store_true", help="Disable video scene-change detection")
    parser.add_argument("--no-video-extraction", action="store_true", help="Disable frame/audio extraction for video")
    parser.add_argument("--strict", action="store_true", help="Fail instead of returning partial results when an optional processor fails")
    args = parser.parse_args(argv)

    try:
        report = analyze_media(
            args.input,
            args.output,
            tesseract_path=args.tesseract,
            pdftotext_path=args.pdftotext,
            whisper_model=args.whisper_model,
            whisper_path=args.whisper_cli,
            ffmpeg_path=args.ffmpeg,
            ffprobe_path=args.ffprobe,
            ocr_languages=args.ocr_languages,
            enable_scenes=not args.no_scenes,
            enable_video_extraction=not args.no_video_extraction,
            strict=args.strict,
        )
    except (AnalysisError, OSError) as exc:
        print(f"ANALYSIS FAILED: {exc}", file=sys.stderr)
        return 2

    evidence_count = sum(item["record_type"] == "evidence" for item in report["records"])
    timeline_count = sum(item["record_type"] == "timeline_event" for item in report["records"])
    summary = {
        "status": report["manifest"]["status"],
        "asset_id": report["asset"]["asset_id"],
        "analysis_file": "analysis.json",
        "evidence_count": evidence_count,
        "timeline_count": timeline_count,
        "processor_results": report["processor_results"],
        "warnings": report["manifest"]["warnings"],
        "artifacts": report["artifacts"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
