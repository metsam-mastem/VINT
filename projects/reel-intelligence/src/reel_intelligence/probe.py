"""Bounded FFprobe metadata extraction for local audio/video assets."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .intake import IntakeError, inspect_file


class ProbeError(ValueError):
    """Raised when FFprobe is unavailable or cannot produce valid metadata."""


def _resolve_executable(value: str | os.PathLike[str] | None) -> str:
    requested = os.fspath(value) if value is not None else "ffprobe"
    executable = shutil.which(requested)
    if executable is None:
        raise ProbeError(f"ffprobe executable not found: {requested}")
    return executable


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(parsed, bool) or not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _clean_format(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("format_name", "format_long_name"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            result[field] = value
    for source, target, integer in (
        ("duration", "duration_seconds", False),
        ("size", "size_bytes", True),
        ("bit_rate", "bit_rate_bps", True),
    ):
        parsed = _number(raw.get(source), integer=integer)
        if parsed is not None:
            result[target] = parsed
    return result


def _clean_stream(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProbeError(f"ffprobe stream {index} is not an object")
    result: dict[str, Any] = {"stream_index": index}
    for field in ("codec_type", "codec_name", "codec_long_name", "profile", "sample_fmt",
                  "sample_aspect_ratio", "display_aspect_ratio", "avg_frame_rate",
                  "r_frame_rate", "channel_layout"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            result[field] = value
    for field in ("width", "height", "channels", "sample_rate", "bit_rate"):
        parsed = _number(raw.get(field), integer=True)
        if parsed is not None:
            result[field] = parsed
    for field in ("duration",):
        parsed = _number(raw.get(field))
        if parsed is not None:
            result[f"{field}_seconds"] = parsed
    return result


def probe_media(path: str | os.PathLike[str], *,
                ffprobe_path: str | os.PathLike[str] | None = None,
                root: str | os.PathLike[str] | None = None,
                timeout_seconds: float = 20.0) -> dict[str, Any]:
    """Inspect an audio/video file with FFprobe without decoding or modifying it."""
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ProbeError("timeout_seconds must be a finite number greater than zero")

    try:
        asset = inspect_file(path, root=root)
    except IntakeError as exc:
        raise ProbeError(str(exc)) from exc
    if asset["media_type"] not in {"audio", "video"}:
        raise ProbeError("FFprobe metadata extraction is limited to audio/video assets")

    executable = _resolve_executable(ffprobe_path)
    media_path = Path(path)
    if root is not None and not media_path.is_absolute():
        media_path = Path(root) / media_path
    try:
        resolved = media_path.resolve(strict=True)
        completed = subprocess.run(
            [executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(resolved)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_seconds),
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"ffprobe timed out after {timeout_seconds} seconds") from exc
    except OSError as exc:
        raise ProbeError(f"failed to execute ffprobe: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[:500]
        suffix = f": {detail}" if detail else ""
        raise ProbeError(f"ffprobe exited with status {completed.returncode}{suffix}")
    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProbeError("ffprobe did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProbeError("ffprobe JSON root must be an object")
    raw_format = payload.get("format", {})
    raw_streams = payload.get("streams", [])
    if not isinstance(raw_format, dict) or not isinstance(raw_streams, list):
        raise ProbeError("ffprobe JSON must contain a format object and streams array")

    return {
        "asset": asset,
        "probe": {
            "probe_version": 1,
            "tool": "ffprobe",
            "format": _clean_format(raw_format),
            "streams": [_clean_stream(item, index) for index, item in enumerate(raw_streams)],
        },
    }
