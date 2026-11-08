"""Local-first, content-addressed intake for supported media files."""
from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import validate_record

class IntakeError(ValueError):
    """Raised when a local file cannot be safely accepted as an asset."""


_FORMATS = {
    ".mp4": ("mp4", "video"),
    ".mp3": ("mp3", "audio"),
    ".wav": ("wav", "audio"),
    ".jpg": ("jpeg", "image"),
    ".jpeg": ("jpeg", "image"),
    ".png": ("png", "image"),
    ".pdf": ("pdf", "document"),
}


def _detected_format(prefix: bytes) -> str | None:
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        return "mp4"
    if prefix.startswith(b"ID3") or (
        len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0
    ):
        return "mp3"
    if len(prefix) >= 12 and prefix[:4] in {b"RIFF", b"RF64"} and prefix[8:12] == b"WAVE":
        return "wav"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if prefix.startswith(b"%PDF-"):
        return "pdf"
    return None


def inspect_file(path: str | os.PathLike[str], *, root: str | os.PathLike[str] | None = None,
                 chunk_size: int = 1024 * 1024) -> dict[str, Any]:
    """Hash and identify one supported file without copying or exposing its absolute path.

    If root is provided, the resolved file must remain beneath that directory.
    Symbolic links and non-regular files are rejected.
    """
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 4096:
        raise IntakeError("chunk_size must be an integer >= 4096")

    candidate = Path(path)
    if root is not None and not candidate.is_absolute():
        candidate = Path(root) / candidate

    try:
        root_path = Path(root).resolve(strict=True) if root is not None else None
        if root_path is not None and not root_path.is_dir():
            raise IntakeError("root must be an existing directory")
        entry_stat = candidate.lstat()
    except OSError as exc:
        raise IntakeError(f"cannot access input path: {exc}") from exc

    if stat.S_ISLNK(entry_stat.st_mode):
        raise IntakeError("symbolic link inputs are not accepted")

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise IntakeError(f"cannot resolve input path: {exc}") from exc

    if root_path is not None and not resolved.is_relative_to(root_path):
        raise IntakeError("input path is outside the permitted root")
    if resolved.suffix.lower() not in _FORMATS:
        raise IntakeError(f"unsupported file extension: {resolved.suffix or '(none)'}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise IntakeError(f"cannot open input safely: {exc}") from exc

    digest = hashlib.sha256()
    prefix = b""
    try:
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise IntakeError("input must be a regular file")
            if before.st_size <= 0:
                raise IntakeError("empty files are not accepted")
            first = stream.read(chunk_size)
            prefix = first[:32]
            digest.update(first)
            while True:
                block = stream.read(chunk_size)
                if not block:
                    break
                digest.update(block)
            after = os.fstat(stream.fileno())
            identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if identity_before != identity_after:
                raise IntakeError("file changed while it was being inspected")
    except OSError as exc:
        raise IntakeError(f"failed while reading input: {exc}") from exc

    expected_format, media_type = _FORMATS[resolved.suffix.lower()]
    actual_format = _detected_format(prefix)
    if actual_format is None:
        raise IntakeError("file signature is not a supported format")
    if actual_format != expected_format:
        raise IntakeError(
            f"extension/signature mismatch: expected {expected_format}, detected {actual_format}"
        )

    sha256 = digest.hexdigest()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    asset = {
        "schema_version": "1.0",
        "record_type": "asset",
        "asset_id": f"asset-{sha256[:24]}",
        "sha256": sha256,
        "media_type": media_type,
        "filename": resolved.name,
        "byte_size": after.st_size,
        "source": {"kind": "local_file"},
        "created_at": created_at,
        "metadata": {
            "detected_format": actual_format,
            "extension": resolved.suffix.lower(),
        },
    }
    return validate_record(asset)
