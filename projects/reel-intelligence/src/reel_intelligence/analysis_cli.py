"""Command-line interface for a complete local multimodal analysis run."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .pipeline import PipelineError, run_local_analysis


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ri-analyze",
        description="Run a local media file through intake, optional modality processors, and evidence/timeline generation.",
    )
    parser.add_argument("input", help="Local media file (MP4, MP3, WAV, JPEG, PNG, PDF)")
    parser.add_argument("--output", "--output-dir", dest="output", required=True,
                        help="New output directory; existing runs are never overwritten")
    parser.add_argument("--ffmpeg", help="Path or command name for FFmpeg")
    parser.add_argument("--ffprobe", help="Path or command name for FFprobe")
    parser.add_argument("--whisper-model", "--asr-model", dest="whisper_model",
                        help="Path to an already-downloaded local whisper.cpp model")
    parser.add_argument("--whisper-cli", help="Path or command name for whisper.cpp")
    parser.add_argument("--tesseract", help="Path or command name for Tesseract")
    parser.add_argument("--pdftotext", help="Path or command name for Poppler pdftotext")
    parser.add_argument("--pdftoppm", help="Path or command name for Poppler pdftoppm")
    parser.add_argument("--ocr-languages", default="eng", help="Tesseract language code/list (e.g. eng+fas)")
    parser.add_argument("--no-ocr", action="store_true",
                        help="Disable image/video/scanned-PDF OCR; selectable PDF text extraction remains enabled")
    parser.add_argument("--no-scene-detection", "--no-scenes", dest="no_scene_detection", action="store_true",
                        help="Disable FFmpeg scene-change detection")
    parser.add_argument("--scene-threshold", type=float, default=0.35,
                        help="FFmpeg scene-change threshold in the range 0.01–0.99")
    parser.add_argument("--frame-interval", type=float, default=5.0,
                        help="Video frame sampling interval in seconds")
    parser.add_argument("--max-frames", type=int, default=120,
                        help="Maximum sampled frames (1–5000)")
    parser.add_argument("--max-ocr-frames", type=int, default=24,
                        help="Maximum video frames passed to OCR (1–1000)")
    parser.add_argument("--max-pdf-pages", type=int, default=100,
                        help="Maximum scanned-PDF pages rendered (1–1000)")
    parser.add_argument("--max-duration", type=float, default=3600.0,
                        help="Maximum audio/video duration processed in seconds")
    parser.add_argument("--ffmpeg-timeout", type=float, default=300.0,
                        help="FFmpeg/FFprobe timeout in seconds")
    parser.add_argument("--asr-timeout", type=float, default=1800.0,
                        help="ASR timeout in seconds")
    parser.add_argument("--ocr-timeout", type=float, default=60.0,
                        help="OCR and PDF processor timeout in seconds")
    parser.add_argument("--strict", action="store_true",
                        help="Stop and remove the new run when an optional processor fails")
    return parser


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    records = result.get("records", [])
    asset = result.get("asset", {})
    manifest = result.get("manifest", {})
    return {
        "status": manifest.get("status", "failed"),
        "asset_id": asset.get("asset_id"),
        "filename": asset.get("filename"),
        "counts": {
            "evidence": sum(item.get("record_type") == "evidence" for item in records),
            "timeline_events": sum(item.get("record_type") == "timeline_event" for item in records),
            "claims": sum(item.get("record_type") == "claim" for item in records),
            "artifacts": len(result.get("artifacts", [])),
        },
        "processors": result.get("processor_status", {}),
        "warnings": result.get("warnings", []),
        "output_dir": result.get("output_dir"),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_local_analysis(
            args.input,
            args.output,
            ffmpeg_path=args.ffmpeg,
            ffprobe_path=args.ffprobe,
            asr_model_path=args.whisper_model,
            whisper_executable=args.whisper_cli,
            tesseract_path=args.tesseract,
            pdftotext_path=args.pdftotext,
            pdftoppm_path=args.pdftoppm,
            ocr_languages=args.ocr_languages,
            enable_ocr=not args.no_ocr,
            enable_scene_detection=not args.no_scene_detection,
            scene_threshold=args.scene_threshold,
            frame_interval_seconds=args.frame_interval,
            max_frames=args.max_frames,
            max_ocr_frames=args.max_ocr_frames,
            max_pdf_pages=args.max_pdf_pages,
            max_duration_seconds=args.max_duration,
            ffmpeg_timeout_seconds=args.ffmpeg_timeout,
            asr_timeout_seconds=args.asr_timeout,
            ocr_timeout_seconds=args.ocr_timeout,
            fail_fast=args.strict,
        )
    except (PipelineError, OSError) as exc:
        print(f"ANALYSIS FAILED: {exc}", file=sys.stderr)
        return 2

    summary = _summary(result)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if summary["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
