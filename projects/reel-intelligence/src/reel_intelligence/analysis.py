"""Evidence-first conversion of local processor outputs into canonical records."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable
import shutil

from .contracts import ContractError, validate_bundle, validate_record

SCHEMA_VERSION = "1.0"
DEFAULT_PIPELINE_VERSION = "0.2.0"


class AnalysisError(ValueError):
    """Raised when processor output cannot be represented as canonical evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stable_id(prefix: str, value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalysisError(f"{label} must be a non-negative integer")
    return value


def _relative_locator_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError("OCR source path must be a non-empty relative path")
    # Check both path grammars: bundles can be moved between Windows and POSIX.
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts or ".." in windows.parts:
        raise AnalysisError("OCR source path must be a safe relative path")
    if "\x00" in value:
        raise AnalysisError("OCR source path contains a NUL byte")
    normalized = posix.as_posix()
    if normalized in {"", "."}:
        raise AnalysisError("OCR source path must identify a file")
    return normalized


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"{label} text must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > 250_000:
        raise AnalysisError(f"{label} text exceeds the 250000-character safety limit")
    return cleaned


def _confidence(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise AnalysisError(f"{label} confidence must be between 0 and 1")
    return float(value)


def build_analysis_bundle(
    asset: dict[str, Any],
    *,
    transcript_segments: Iterable[dict[str, Any]] | None = None,
    ocr_observations: Iterable[dict[str, Any]] | None = None,
    scene_boundaries_ms: Iterable[int] | None = None,
    warnings: Iterable[str] | None = None,
    toolchain: dict[str, Any] | None = None,
    pipeline_version: str = DEFAULT_PIPELINE_VERSION,
) -> dict[str, Any]:
    """Create a self-validating AnalysisManifest, Evidence, and Timeline bundle.

    No claims or semantic conclusions are generated here. Each timeline event is
    anchored to one evidence record and retains its modality-specific locator.
    """
    try:
        validated_asset = validate_record(asset)
    except ContractError as exc:
        raise AnalysisError(f"invalid source asset: {exc}") from exc
    if validated_asset["record_type"] != "asset":
        raise AnalysisError("analysis input must be an Asset record")
    if not isinstance(pipeline_version, str) or not pipeline_version.strip():
        raise AnalysisError("pipeline_version must be a non-empty string")
    if toolchain is not None and not isinstance(toolchain, dict):
        raise AnalysisError("toolchain must be an object")

    def materialize(items: Iterable[Any] | None, label: str) -> list[Any]:
        if items is None:
            return []
        if isinstance(items, (str, bytes, dict)):
            raise AnalysisError(f"{label} must be an iterable of objects, not a string or object")
        try:
            result = list(items)
        except TypeError as exc:
            raise AnalysisError(f"{label} must be iterable") from exc
        if len(result) > 50_000:
            raise AnalysisError(f"{label} exceeds the 50000-record safety limit")
        return result

    transcript_items = materialize(transcript_segments, "transcript_segments")
    ocr_items = materialize(ocr_observations, "ocr_observations")
    scene_items = materialize(scene_boundaries_ms, "scene_boundaries_ms")
    warning_items = materialize(warnings, "warnings")
    if len(warning_items) > 100:
        raise AnalysisError("warnings exceeds the 100-item safety limit")
    clean_warnings = []
    for warning in warning_items:
        if not isinstance(warning, str) or not warning.strip() or len(warning) > 1000:
            raise AnalysisError("each warning must be a non-empty string of at most 1000 characters")
        clean_warnings.append(warning.strip())

    timestamp = _now()
    asset_id = validated_asset["asset_id"]
    evidence_records: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    event_ids: set[str] = set()

    def add_observation(
        *,
        modality: str,
        locator: dict[str, Any],
        observation: str,
        extractor: str,
        event_type: str,
        start_ms: int,
        end_ms: int,
        confidence: float | None = None,
        content_hash: str | None = None,
    ) -> None:
        evidence_key = {
            "asset_id": asset_id,
            "modality": modality,
            "locator": locator,
            "observation": observation,
            "extractor": extractor,
        }
        evidence_id = _stable_id("evidence", evidence_key)
        if evidence_id in evidence_ids:
            return
        evidence_ids.add(evidence_id)
        evidence = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "evidence",
            "evidence_id": evidence_id,
            "asset_id": asset_id,
            "modality": modality,
            "locator": locator,
            "observation": observation,
            "extractor": extractor,
            "created_at": timestamp,
        }
        if confidence is not None:
            evidence["confidence"] = confidence
        if content_hash is not None:
            if not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
                raise AnalysisError("content_hash must be a lowercase SHA-256 digest")
            evidence["content_hash"] = content_hash
        evidence_records.append(evidence)

        event_key = {
            "asset_id": asset_id,
            "event_type": event_type,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "evidence_id": evidence_id,
        }
        event_id = _stable_id("event", event_key)
        if event_id in event_ids:
            return
        event_ids.add(event_id)
        event = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "timeline_event",
            "event_id": event_id,
            "asset_id": asset_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "event_type": event_type,
            "text": observation,
            "evidence_ids": [evidence_id],
            "producer": extractor,
            "created_at": timestamp,
        }
        if confidence is not None:
            event["confidence"] = confidence
        event_records.append(event)

    for index, item in enumerate(transcript_items):
        if not isinstance(item, dict):
            raise AnalysisError(f"transcript segment {index} must be an object")
        start_ms = _non_negative_integer(item.get("start_ms"), f"transcript segment {index} start_ms")
        end_ms = _non_negative_integer(item.get("end_ms"), f"transcript segment {index} end_ms")
        if end_ms <= start_ms:
            raise AnalysisError(f"transcript segment {index} interval must have end_ms greater than start_ms")
        text = _text(item.get("text"), "transcript segment")
        confidence = _confidence(item.get("confidence"), "transcript segment")
        extractor = str(item.get("extractor") or (toolchain or {}).get("asr") or "asr")
        add_observation(
            modality="audio",
            locator={"start_ms": start_ms, "end_ms": end_ms},
            observation=text,
            extractor=extractor,
            event_type="transcription_segment",
            start_ms=start_ms,
            end_ms=end_ms,
            confidence=confidence,
            content_hash=item.get("content_hash"),
        )

    for index, item in enumerate(ocr_items):
        if not isinstance(item, dict):
            raise AnalysisError(f"OCR observation {index} must be an object")
        text = _text(item.get("text"), "OCR observation")
        timestamp_ms = _non_negative_integer(item.get("timestamp_ms", item.get("start_ms", 0)), f"OCR observation {index} timestamp_ms")
        locator: dict[str, Any] = {"start_ms": timestamp_ms}
        if "path" in item:
            locator["path"] = _relative_locator_path(item["path"])
        if "page" in item:
            locator["page"] = _non_negative_integer(item["page"], f"OCR observation {index} page")
            if locator["page"] < 1:
                raise AnalysisError("OCR page number must start at 1")
        if "path" not in item and "page" not in item:
            raise AnalysisError("OCR observation must provide a relative path or a page number")
        if "path" not in item:
            locator.pop("start_ms")
        if "bbox" in item:
            bbox = item["bbox"]
            if not isinstance(bbox, dict):
                raise AnalysisError("OCR bbox must be an object")
            allowed = {"x", "y", "width", "height"}
            if set(bbox) - allowed or not {"x", "y", "width", "height"}.issubset(bbox):
                raise AnalysisError("OCR bbox must contain x, y, width, and height")
            locator["region"] = {
                key: _non_negative_integer(bbox[key], f"OCR bbox {key}")
                for key in ("x", "y", "width", "height")
            }
        confidence = _confidence(item.get("confidence"), "OCR observation")
        extractor = str(item.get("extractor") or (toolchain or {}).get("ocr") or "ocr")
        add_observation(
            modality="image" if "path" in item else "document",
            locator=locator,
            observation=text,
            extractor=extractor,
            event_type="ocr_text" if "path" in item else "document_text",
            start_ms=timestamp_ms,
            end_ms=timestamp_ms,
            confidence=confidence,
            content_hash=item.get("content_hash"),
        )

    for index, item in enumerate(scene_items):
        if isinstance(item, dict):
            boundary = item.get("start_ms")
            extractor = str(item.get("extractor") or (toolchain or {}).get("scene") or "ffmpeg-scene-detect")
        else:
            boundary = item
            extractor = str((toolchain or {}).get("scene") or "ffmpeg-scene-detect")
        start_ms = _non_negative_integer(boundary, f"scene boundary {index}")
        add_observation(
            modality="video",
            locator={"start_ms": start_ms},
            observation="Scene transition detected by the configured scene-change processor.",
            extractor=extractor,
            event_type="scene_boundary",
            start_ms=start_ms,
            end_ms=start_ms,
        )

    status = "partial" if clean_warnings else "completed"

    manifest_id = _stable_id(
        "manifest",
        {
            "asset_id": asset_id,
            "pipeline_version": pipeline_version,
            "evidence_ids": sorted(evidence_ids),
            "warnings": clean_warnings,
            "toolchain": toolchain or {},
            "created_at": timestamp,
        },
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "analysis_manifest",
        "manifest_id": manifest_id,
        "asset_id": asset_id,
        "pipeline_version": pipeline_version,
        "status": status,
        "started_at": timestamp,
        "finished_at": timestamp,
        "created_at": timestamp,
        "toolchain": toolchain or {},
        "output_refs": sorted(evidence_ids),
        "warnings": clean_warnings,
    }

    records = [manifest, *evidence_records, *event_records]
    try:
        validate_bundle([validated_asset, *records])
    except ContractError as exc:
        raise AnalysisError(f"generated analysis bundle failed canonical validation: {exc}") from exc

    return {
        "manifest": manifest,
        "evidence": evidence_records,
        "timeline_events": event_records,
        "records": records,
    }


def _local_executable_available(value: str | Path | None, default: str) -> bool:
    requested = str(value) if value is not None else default
    candidate = Path(requested)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return candidate.is_file()
    return shutil.which(requested) is not None


def analyze_media(
    path: str | Path,
    output_dir: str | Path,
    *,
    tesseract_path: str | Path | None = None,
    pdftotext_path: str | Path | None = None,
    whisper_model: str | Path | None = None,
    whisper_path: str | Path | None = None,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    ocr_languages: str = "eng",
    enable_scenes: bool = True,
    enable_video_extraction: bool = True,
    frame_interval_seconds: float = 5.0,
    max_frames: int = 120,
    max_duration_seconds: float = 3600.0,
    strict: bool = False,
) -> dict[str, Any]:
    """Run installed local processors and persist a validated analysis report.

    The output directory must be new. Optional processors are skipped with an
    explicit warning unless strict=True. Inputs never leave the local machine.
    """
    from .extraction import ExtractionError, extract_media
    from .intake import IntakeError, inspect_file
    from .processors import ASRProcessor, OCRProcessor, PDFTextProcessor, ProcessorError, SceneDetectionProcessor

    try:
        asset = inspect_file(path)
    except IntakeError as exc:
        raise AnalysisError(str(exc)) from exc

    destination = Path(output_dir)
    if destination.exists() or destination.is_symlink():
        raise AnalysisError("analysis output directory already exists")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.parent.resolve(strict=True) / destination.name
        destination.mkdir(mode=0o700)
    except OSError as exc:
        raise AnalysisError(f"cannot create analysis output directory: {exc}") from exc

    warnings: list[str] = []
    toolchain: dict[str, Any] = {}
    transcript_segments: list[dict[str, Any]] = []
    ocr_observations: list[dict[str, Any]] = []
    scene_boundaries: list[int] = []
    processor_results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []

    def warning(message: str) -> None:
        if strict:
            raise AnalysisError(message)
        warnings.append(message)

    def redact(value: str) -> str:
        sensitive_paths = [source, destination]
        for candidate in sensitive_paths:
            try:
                absolute = str(candidate.resolve(strict=False))
                if absolute:
                    value = value.replace(absolute, candidate.name or "<local-path>")
            except OSError:
                continue
        return value

    def attempt(name: str, operation):
        try:
            result = operation()
            processor_results.append({"processor": name, "status": "completed"})
            return result
        except (ProcessorError, ExtractionError, OSError) as exc:
            message = redact(f"{name} skipped or failed: {exc}")
            if strict:
                raise AnalysisError(message) from exc
            warnings.append(message)
            processor_results.append({"processor": name, "status": "failed", "warning": message})
            return None

    source = Path(path)
    try:
        media_type = asset["media_type"]
        if media_type == "image":
            if _local_executable_available(tesseract_path, "tesseract"):
                result = attempt(
                    "tesseract",
                    lambda: OCRProcessor(tesseract_path=tesseract_path).process(source, languages=ocr_languages),
                )
                if result is not None:
                    toolchain["ocr"] = "tesseract"
                    for page in result["pages"]:
                        if page["text"]:
                            ocr_observations.append({
                                "path": asset["filename"],
                                "text": page["text"],
                            })
            else:
                warning("OCR skipped: Tesseract is not installed or configured")

        elif media_type == "document" and asset["metadata"]["detected_format"] == "pdf":
            if _local_executable_available(pdftotext_path, "pdftotext"):
                result = attempt(
                    "pdftotext",
                    lambda: PDFTextProcessor(pdftotext_path=pdftotext_path).process(source),
                )
                if result is not None:
                    toolchain["pdf_text"] = "pdftotext"
                    for page in result["pages"]:
                        if page["text"]:
                            ocr_observations.append({"page": page["page"], "text": page["text"]})
            else:
                warning("PDF text extraction skipped: Poppler pdftotext is not installed or configured")

        elif media_type == "audio":
            if whisper_model is None:
                warning("ASR skipped: configure a local whisper.cpp model with --whisper-model")
            else:
                result = attempt(
                    "whisper.cpp",
                    lambda: ASRProcessor(model_path=whisper_model, executable=whisper_path).process(source),
                )
                if result is not None:
                    toolchain["asr"] = "whisper.cpp"
                    transcript_segments.extend(result["segments"])

        elif media_type == "video":
            if enable_scenes:
                if _local_executable_available(ffmpeg_path, "ffmpeg"):
                    result = attempt(
                        "ffmpeg_scene_detection",
                        lambda: SceneDetectionProcessor(ffmpeg_path=ffmpeg_path).process(source),
                    )
                    if result is not None:
                        toolchain["scene"] = "ffmpeg"
                        scene_boundaries.extend(item["start_ms"] for item in result["scenes"])
                else:
                    warning("Scene detection skipped: FFmpeg is not installed or configured")

            extraction_result = None
            if enable_video_extraction:
                if _local_executable_available(ffmpeg_path, "ffmpeg") and _local_executable_available(ffprobe_path, "ffprobe"):
                    extraction_result = attempt(
                        "ffmpeg_temporal_extraction",
                        lambda: extract_media(
                            source,
                            destination / "derivatives",
                            ffmpeg_path=ffmpeg_path,
                            ffprobe_path=ffprobe_path,
                            interval_seconds=frame_interval_seconds,
                            max_frames=max_frames,
                            max_duration_seconds=max_duration_seconds,
                        ),
                    )
                    if extraction_result is not None:
                        toolchain["video_extraction"] = "ffmpeg"
                        for item in extraction_result["files"]:
                            artifacts.append({"path": "derivatives/" + item["path"], "kind": item["kind"]})
                else:
                    warning("Temporal extraction skipped: FFmpeg and FFprobe are both required")

            if extraction_result is not None and _local_executable_available(tesseract_path, "tesseract"):
                for item in extraction_result["files"]:
                    if item["kind"] != "video_frame":
                        continue
                    frame_path = destination / "derivatives" / item["path"]
                    result = attempt(
                        "tesseract_frame_ocr",
                        lambda frame_path=frame_path: OCRProcessor(tesseract_path=tesseract_path).process(
                            frame_path, languages=ocr_languages
                        ),
                    )
                    if result is not None:
                        toolchain["ocr"] = "tesseract"
                        for page in result["pages"]:
                            if page["text"]:
                                ocr_observations.append({
                                    "path": "derivatives/" + item["path"],
                                    "timestamp_ms": item.get("timestamp_ms", 0),
                                    "text": page["text"],
                                })

            if whisper_model is not None:
                audio_artifact = next(
                    (item for item in (extraction_result or {}).get("files", []) if item["kind"] == "normalized_audio"),
                    None,
                )
                if audio_artifact is None:
                    warning("ASR skipped: no extracted audio stream is available")
                else:
                    audio_path = destination / "derivatives" / audio_artifact["path"]
                    result = attempt(
                        "whisper.cpp",
                        lambda: ASRProcessor(model_path=whisper_model, executable=whisper_path).process(audio_path),
                    )
                    if result is not None:
                        toolchain["asr"] = "whisper.cpp"
                        transcript_segments.extend(result["segments"])
        else:
            warning(f"No modality processor is registered for media type {media_type}")

        bundle = build_analysis_bundle(
            asset,
            transcript_segments=transcript_segments,
            ocr_observations=ocr_observations,
            scene_boundaries_ms=scene_boundaries,
            warnings=warnings,
            toolchain=toolchain,
        )
        report = {
            "report_version": "1.0",
            "pipeline_version": DEFAULT_PIPELINE_VERSION,
            "created_at": _now(),
            "asset": asset,
            "manifest": bundle["manifest"],
            "records": [asset, *bundle["records"]],
            "processor_results": processor_results,
            "artifacts": artifacts,
            "claims": [],
        }
        temporary = destination / ".analysis.json.tmp"
        final_path = destination / "analysis.json"
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(final_path)
        return report
    except (AnalysisError, ProcessorError, ExtractionError, ContractError, OSError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        if isinstance(exc, AnalysisError):
            raise
        raise AnalysisError(str(exc)) from exc
