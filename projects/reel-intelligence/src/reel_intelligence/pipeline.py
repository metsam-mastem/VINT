"""One-command, local-first media analysis orchestration."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import AnalysisError, build_analysis_bundle
from .extraction import ExtractionError, extract_media
from .intake import IntakeError, inspect_file
from .processors import (
    ASRProcessor,
    FFmpegSceneDetector,
    OCRProcessor,
    PDFPageRenderer,
    PDFTextProcessor,
    ProcessorError,
)


class PipelineError(ValueError):
    """Raised when a complete local analysis run cannot be safely created."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except (OSError, TypeError, ValueError) as exc:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise PipelineError(f"cannot write run report {path.name}: {exc}") from exc


def _safe_error(exc: Exception, paths: list[Path]) -> str:
    message = str(exc)
    for path in paths:
        try:
            absolute = str(path.resolve(strict=False))
        except OSError:
            absolute = str(path)
        if absolute:
            message = message.replace(absolute, path.name)
    home = str(Path.home())
    if home and home != "/":
        message = message.replace(home, "<HOME>")
    # Tool stderr sometimes embeds arbitrary absolute paths. Redact any remaining
    # POSIX or drive-qualified path fragments before writing a publicable report.
    message = re.sub(r"(?<![A-Za-z0-9])(?:/[A-Za-z0-9_.-]+){2,}", "<LOCAL_PATH>", message)
    message = re.sub(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*", "<LOCAL_PATH>", message)
    return message[:1000]


def _mean_ocr_confidence(page: dict[str, Any]) -> float | None:
    words = page.get("words", [])
    scores = [
        float(item["confidence"]) / 100.0
        for item in words
        if isinstance(item, dict)
        and isinstance(item.get("confidence"), (int, float))
        and math.isfinite(item["confidence"])
        and 0 <= item["confidence"] <= 100
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _ocr_page_observation(
    page: dict[str, Any],
    *,
    path: str,
    modality: str,
    timestamp_ms: int = 0,
    content_hash: str | None = None,
    extractor: str = "tesseract",
) -> dict[str, Any] | None:
    text = page.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    item: dict[str, Any] = {
        "path": path,
        "page": page.get("page", 1),
        "timestamp_ms": timestamp_ms,
        "text": text,
        "extractor": extractor,
        "modality": modality,
    }
    confidence = _mean_ocr_confidence(page)
    if confidence is not None:
        item["confidence"] = confidence
    if content_hash:
        item["content_hash"] = content_hash
    return item


def run_local_analysis(
    source_path: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    *,
    ffmpeg_path: str | os.PathLike[str] | None = None,
    ffprobe_path: str | os.PathLike[str] | None = None,
    asr_model_path: str | os.PathLike[str] | None = None,
    whisper_executable: str | os.PathLike[str] | None = None,
    tesseract_path: str | os.PathLike[str] | None = None,
    pdftotext_path: str | os.PathLike[str] | None = None,
    pdftoppm_path: str | os.PathLike[str] | None = None,
    ocr_languages: str = "eng",
    enable_ocr: bool = True,
    enable_scene_detection: bool = True,
    scene_threshold: float = 0.35,
    frame_interval_seconds: float = 5.0,
    max_frames: int = 120,
    max_ocr_frames: int = 24,
    max_pdf_pages: int = 100,
    max_duration_seconds: float = 3600.0,
    ffmpeg_timeout_seconds: float = 300.0,
    asr_timeout_seconds: float = 1800.0,
    ocr_timeout_seconds: float = 60.0,
    fail_fast: bool = False,
) -> dict[str, Any]:
    """Run intake → derivative extraction → local ASR/OCR/scenes → evidence bundle.

    Source media is read in place and never copied into the run directory. The
    destination must be new; generated derivatives and JSON reports are private
    to that directory. Optional processor failures are recorded as warnings unless
    fail_fast=True.
    """
    try:
        asset = inspect_file(source_path)
        source = Path(source_path).resolve(strict=True)
    except (IntakeError, OSError) as exc:
        raise PipelineError(f"cannot accept source media: {exc}") from exc

    destination = Path(output_dir)
    if destination.exists() or destination.is_symlink():
        raise PipelineError("output directory already exists; choose a new run directory")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.parent.resolve(strict=True) / destination.name
        destination.mkdir(mode=0o700)
    except OSError as exc:
        raise PipelineError(f"cannot create analysis output directory: {exc}") from exc

    started_at = _now()
    warnings: list[str] = []
    processor_status: dict[str, str] = {}
    toolchain: dict[str, Any] = {}
    transcript_segments: list[dict[str, Any]] = []
    ocr_observations: list[dict[str, Any]] = []
    scene_boundaries: list[dict[str, Any]] = []
    extraction_result: dict[str, Any] | None = None
    report_files: list[str] = ["asset.json", "analysis.json", "run_manifest.json"]

    def record_warning(name: str, exc: Exception) -> None:
        warning = f"{name}: {_safe_error(exc, [source, destination, Path(asr_model_path) if asr_model_path else source])}"
        warnings.append(warning)
        processor_status[name] = "failed"
        if fail_fast:
            raise PipelineError(warning) from exc

    try:
        _atomic_write_json(destination / "asset.json", asset)

        media_type = asset["media_type"]
        if media_type in {"audio", "video"}:
            try:
                extraction_result = extract_media(
                    source,
                    destination / "derived",
                    ffmpeg_path=ffmpeg_path,
                    ffprobe_path=ffprobe_path,
                    interval_seconds=frame_interval_seconds,
                    max_frames=max_frames,
                    max_duration_seconds=max_duration_seconds,
                    timeout_seconds=ffmpeg_timeout_seconds,
                )
                if extraction_result["asset"]["asset_id"] != asset["asset_id"]:
                    raise PipelineError("source media changed between intake and extraction")
                _atomic_write_json(destination / "extraction.json", extraction_result)
                report_files.append("extraction.json")
                toolchain["extraction"] = "ffmpeg+ffprobe"
                processor_status["extraction"] = "completed"
            except (ExtractionError, OSError, PipelineError) as exc:
                if isinstance(exc, PipelineError):
                    raise
                record_warning("media extraction", exc)

        normalized_audio = None
        extracted_frames: list[dict[str, Any]] = []
        if extraction_result is not None:
            for item in extraction_result.get("files", []):
                if item.get("kind") == "normalized_audio":
                    normalized_audio = destination / "derived" / item["path"]
                elif item.get("kind") == "video_frame":
                    extracted_frames.append(item)

        if asr_model_path is not None:
            if normalized_audio is None:
                record_warning("ASR", ProcessorError("no normalized audio is available for transcription"))
            else:
                try:
                    result = ASRProcessor(
                        model_path=asr_model_path,
                        executable=whisper_executable,
                        timeout_seconds=asr_timeout_seconds,
                    ).process(normalized_audio)
                    audio_hash = next(
                        item["sha256"] for item in extraction_result["files"]
                        if item["kind"] == "normalized_audio"
                    )
                    for segment in result["segments"]:
                        transcript_segments.append({
                            **segment,
                            "extractor": result["processor"],
                            "content_hash": audio_hash,
                        })
                    toolchain["asr"] = result["processor"]
                    processor_status["asr"] = "completed"
                except (ProcessorError, OSError, KeyError, StopIteration) as exc:
                    record_warning("ASR", exc)
        else:
            processor_status["asr"] = "not_configured"

        if enable_ocr and media_type == "image":
            try:
                result = OCRProcessor(
                    tesseract_path=tesseract_path,
                    timeout_seconds=ocr_timeout_seconds,
                ).process(source, languages=ocr_languages)
                for page in result["pages"]:
                    observation = _ocr_page_observation(
                        page,
                        path=source.name,
                        modality="image",
                        timestamp_ms=0,
                        content_hash=asset["sha256"],
                    )
                    if observation:
                        ocr_observations.append(observation)
                toolchain["ocr"] = result["processor"]
                processor_status["ocr"] = "completed"
            except (ProcessorError, OSError) as exc:
                record_warning("OCR", exc)

        elif enable_ocr and media_type == "video":
            if not extracted_frames:
                processor_status["ocr"] = "skipped"
            else:
                stride = max(1, math.ceil(len(extracted_frames) / max_ocr_frames))
                selected_frames = extracted_frames[::stride][:max_ocr_frames]
                processor = OCRProcessor(
                    tesseract_path=tesseract_path,
                    timeout_seconds=ocr_timeout_seconds,
                )
                failures = 0
                for frame in selected_frames:
                    relative_path = f"derived/{frame['path']}"
                    try:
                        result = processor.process(destination / relative_path, languages=ocr_languages)
                        for page in result["pages"]:
                            observation = _ocr_page_observation(
                                page,
                                path=relative_path,
                                modality="image",
                                timestamp_ms=frame["timestamp_ms"],
                                content_hash=frame.get("sha256"),
                            )
                            if observation:
                                ocr_observations.append(observation)
                    except (ProcessorError, OSError) as exc:
                        failures += 1
                        if fail_fast:
                            record_warning("OCR frame", exc)
                if failures:
                    warnings.append(f"OCR: {failures} of {len(selected_frames)} sampled frame(s) could not be processed.")
                toolchain["ocr"] = "tesseract"
                processor_status["ocr"] = "partial" if failures else "completed"

        elif enable_ocr and media_type == "document" and asset["metadata"].get("detected_format") == "pdf":
            text_pages: list[dict[str, Any]] = []
            try:
                text_result = PDFTextProcessor(
                    pdftotext_path=pdftotext_path,
                    timeout_seconds=ocr_timeout_seconds,
                ).process(source)
                text_pages = text_result["pages"]
                for page in text_pages:
                    if page["text"].strip():
                        ocr_observations.append({
                            "page": page["page"],
                            "text": page["text"],
                            "extractor": "pdftotext",
                            "modality": "document",
                            "content_hash": asset["sha256"],
                        })
                toolchain["pdf_text"] = text_result["processor"]
            except (ProcessorError, OSError) as exc:
                warnings.append(f"PDF text layer: {_safe_error(exc, [source, destination])}")

            if not text_pages:
                try:
                    render = PDFPageRenderer(
                        pdftoppm_path=pdftoppm_path,
                        max_pages=max_pdf_pages,
                        timeout_seconds=ocr_timeout_seconds * 3,
                    ).process(source, destination / "pdf-pages")
                    _atomic_write_json(destination / "pdf-render.json", render)
                    report_files.append("pdf-render.json")
                    toolchain["pdf_render"] = render["processor"]
                    ocr = OCRProcessor(
                        tesseract_path=tesseract_path,
                        timeout_seconds=ocr_timeout_seconds,
                    )
                    for page in render["pages"]:
                        relative_path = f"pdf-pages/{page['path']}"
                        result = ocr.process(destination / relative_path, languages=ocr_languages)
                        for output_page in result["pages"]:
                            observation = _ocr_page_observation(
                                output_page,
                                path=relative_path,
                                modality="document",
                                content_hash=page["sha256"],
                                extractor="tesseract-pdf-fallback",
                            )
                            if observation:
                                observation["page"] = page["page"]
                                ocr_observations.append(observation)
                    toolchain["ocr"] = "tesseract"
                    processor_status["ocr"] = "completed"
                except (ProcessorError, OSError) as exc:
                    record_warning("PDF OCR fallback", exc)
            else:
                processor_status["ocr"] = "completed"
        elif enable_ocr:
            processor_status["ocr"] = "not_applicable"
        else:
            processor_status["ocr"] = "disabled"

        if enable_scene_detection and media_type == "video":
            try:
                scene_result = FFmpegSceneDetector(
                    ffmpeg_path=ffmpeg_path,
                    threshold=scene_threshold,
                    max_duration_seconds=max_duration_seconds,
                    timeout_seconds=ffmpeg_timeout_seconds,
                ).process(source)
                source_hash = asset["sha256"]
                scene_boundaries = [
                    {
                        **item,
                        "extractor": scene_result["processor"],
                        "content_hash": source_hash,
                    }
                    for item in scene_result["scenes"]
                ]
                toolchain["scene"] = scene_result["processor"]
                processor_status["scene_detection"] = "completed"
            except (ProcessorError, OSError) as exc:
                record_warning("scene detection", exc)
        else:
            processor_status["scene_detection"] = "disabled" if not enable_scene_detection else "not_applicable"

        # Re-hash the source after all processing. This catches accidental or
        # concurrent source modification before publishing a canonical bundle.
        try:
            final_asset = inspect_file(source)
        except IntakeError as exc:
            raise PipelineError(f"source media became unreadable during processing: {exc}") from exc
        if final_asset["sha256"] != asset["sha256"]:
            raise PipelineError("source media changed during processing; analysis output discarded")

        bundle = build_analysis_bundle(
            asset,
            transcript_segments=transcript_segments,
            ocr_observations=ocr_observations,
            scene_boundaries_ms=scene_boundaries,
            warnings=warnings,
            toolchain=toolchain,
        )
        analysis_document = {
            "analysis_version": 1,
            "asset": asset,
            **bundle,
        }
        _atomic_write_json(destination / "analysis.json", analysis_document)

        finished_at = _now()
        run_manifest = {
            "run_version": 1,
            "status": bundle["manifest"]["status"],
            "asset_id": asset["asset_id"],
            "asset_sha256": asset["sha256"],
            "filename": asset["filename"],
            "started_at": started_at,
            "finished_at": finished_at,
            "processors": processor_status,
            "warnings": warnings,
            "outputs": report_files,
        }
        _atomic_write_json(destination / "run_manifest.json", run_manifest)

        return {
            "asset": asset,
            "manifest": bundle["manifest"],
            "records": bundle["records"],
            "warnings": warnings,
            "processor_status": processor_status,
            "run_manifest": run_manifest,
            "output_dir": str(destination),
            "extraction": extraction_result,
        }
    except (PipelineError, AnalysisError):
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise PipelineError(f"local analysis run failed: {type(exc).__name__}: {exc}") from exc
