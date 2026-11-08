"""Bounded FFmpeg extraction of sampled video frames and normalized audio."""
from __future__ import annotations

import hashlib
import math
import os
import stat
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .probe import ProbeError, probe_media


class ExtractionError(ValueError):
    """Raised when temporal media extraction cannot be completed safely."""


def _describe_derived_file(path: Path, *, root: Path, kind: str, relative_path: str) -> dict[str, Any]:
    """Validate, stream-hash, and describe one processor-created derivative."""
    if path.is_symlink():
        raise ExtractionError("ffmpeg produced a symbolic-link output")
    try:
        resolved = path.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
        details = path.stat()
    except OSError as exc:
        raise ExtractionError(f"cannot inspect derived output: {exc}") from exc
    if not resolved.is_relative_to(root_resolved):
        raise ExtractionError("derived output escaped the extraction directory")
    if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
        raise ExtractionError("ffmpeg output must be a non-empty regular file")

    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as stream:
            before = os.fstat(stream.fileno())
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ExtractionError(f"cannot hash derived output: {exc}") from exc

    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ExtractionError("derived output changed while being hashed")

    return {
        "kind": kind,
        "path": relative_path,
        "byte_size": after.st_size,
        "sha256": digest.hexdigest(),
    }


def _resolve_executable(value: str | os.PathLike[str] | None) -> str:
    requested = os.fspath(value) if value is not None else "ffmpeg"
    executable = shutil.which(requested)
    if executable is None:
        raise ExtractionError(f"ffmpeg executable not found: {requested}")
    return executable


def _run(command: list[str], *, timeout_seconds: float) -> None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_seconds),
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(f"ffmpeg timed out after {timeout_seconds} seconds") from exc
    except OSError as exc:
        raise ExtractionError(f"failed to execute ffmpeg: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[:500]
        suffix = f": {detail}" if detail else ""
        raise ExtractionError(f"ffmpeg exited with status {completed.returncode}{suffix}")


def _validate_limits(interval_seconds: float, max_frames: int,
                     max_duration_seconds: float, timeout_seconds: float) -> None:
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)) or not math.isfinite(interval_seconds) or not 0.1 <= interval_seconds <= 3600:
        raise ExtractionError("interval_seconds must be finite and between 0.1 and 3600")
    if isinstance(max_frames, bool) or not isinstance(max_frames, int) or not 1 <= max_frames <= 5000:
        raise ExtractionError("max_frames must be an integer between 1 and 5000")
    if isinstance(max_duration_seconds, bool) or not isinstance(max_duration_seconds, (int, float)) or not math.isfinite(max_duration_seconds) or not 1 <= max_duration_seconds <= 86400:
        raise ExtractionError("max_duration_seconds must be finite and between 1 and 86400")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ExtractionError("timeout_seconds must be finite and greater than zero")


def extract_media(
    path: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    *,
    ffmpeg_path: str | os.PathLike[str] | None = None,
    ffprobe_path: str | os.PathLike[str] | None = None,
    interval_seconds: float = 5.0,
    max_frames: int = 120,
    max_duration_seconds: float = 3600.0,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Extract sampled JPEG frames and mono 16 kHz WAV audio into a new directory.

    The destination must not already exist. On failure, only the newly-created
    destination directory is removed. Source media is never modified.
    """
    _validate_limits(interval_seconds, max_frames, max_duration_seconds, timeout_seconds)

    source = Path(path)
    try:
        source_path = source.resolve(strict=True)
    except OSError as exc:
        raise ExtractionError(f"cannot access source media: {exc}") from exc
    if not source_path.is_file() or source.is_symlink():
        raise ExtractionError("source must be a regular, non-symbolic-link file")

    destination = Path(output_dir)
    if destination.exists() or destination.is_symlink():
        raise ExtractionError("output directory already exists")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.parent.resolve(strict=True) / destination.name
    except OSError as exc:
        raise ExtractionError(f"cannot prepare output parent: {exc}") from exc

    try:
        inspected = probe_media(source_path, ffprobe_path=ffprobe_path, timeout_seconds=min(timeout_seconds, 60.0))
    except ProbeError as exc:
        raise ExtractionError(str(exc)) from exc

    streams = inspected["probe"]["streams"]
    has_video = any(item.get("codec_type") == "video" for item in streams)
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    if not has_video and not has_audio:
        raise ExtractionError("media has no supported audio or video streams")

    ffmpeg = _resolve_executable(ffmpeg_path)
    try:
        destination.mkdir(mode=0o700)
    except OSError as exc:
        raise ExtractionError(f"cannot create output directory: {exc}") from exc

    generated: list[dict[str, Any]] = []
    try:
        if has_video:
            frames_dir = destination / "frames"
            frames_dir.mkdir()
            frame_pattern = frames_dir / "frame-%06d.jpg"
            command = [
                ffmpeg, "-nostdin", "-hide_banner", "-v", "error",
                "-i", str(source_path), "-t", str(max_duration_seconds),
                "-map", "0:v:0", "-vf", f"fps=1/{interval_seconds}",
                "-frames:v", str(max_frames), "-q:v", "2",
                "-f", "image2", str(frame_pattern),
            ]
            _run(command, timeout_seconds=timeout_seconds)
            frame_paths = sorted(frames_dir.glob("frame-*.jpg"))
            if len(frame_paths) > max_frames:
                raise ExtractionError("ffmpeg produced more frames than the configured limit")
            for index, frame in enumerate(frame_paths, start=1):
                item = _describe_derived_file(
                    frame,
                    root=destination,
                    kind="video_frame",
                    relative_path=f"frames/{frame.name}",
                )
                item["timestamp_ms"] = round((index - 1) * interval_seconds * 1000)
                generated.append(item)

        audio_extracted = False
        if has_audio:
            audio_path = destination / "audio.wav"
            command = [
                ffmpeg, "-nostdin", "-hide_banner", "-v", "error",
                "-i", str(source_path), "-t", str(max_duration_seconds),
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", "-f", "wav", str(audio_path),
            ]
            _run(command, timeout_seconds=timeout_seconds)
            audio_item = _describe_derived_file(
                audio_path,
                root=destination,
                kind="normalized_audio",
                relative_path="audio.wav",
            )
            audio_item["sample_rate"] = 16000
            audio_item["channels"] = 1
            generated.append(audio_item)
            audio_extracted = True

        if not generated:
            raise ExtractionError("ffmpeg produced no extractable media outputs")

        return {
            "asset": inspected["asset"],
            "probe": inspected["probe"],
            "extraction": {
                "extraction_version": 1,
                "tool": "ffmpeg",
                "frame_interval_seconds": float(interval_seconds),
                "max_frames": max_frames,
                "max_duration_seconds": float(max_duration_seconds),
                "frame_count": sum(item["kind"] == "video_frame" for item in generated),
                "audio_extracted": audio_extracted,
            },
            "files": generated,
        }
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
