"""Optional, local-only OCR, PDF text, ASR, and scene-detection processors."""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .intake import IntakeError, inspect_file


class ProcessorError(ValueError):
    """Raised when a local modality processor cannot complete safely."""


def _resolve_executable(value: str | os.PathLike[str] | None, default: str) -> str:
    requested = os.fspath(value) if value is not None else default
    executable = shutil.which(requested)
    if executable is None:
        raise ProcessorError(f"processor executable not found: {requested}")
    return executable


def _check_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ProcessorError("timeout must be a finite number greater than zero")
    return float(value)


def _inspect(path: str | os.PathLike[str], expected: set[str]) -> dict[str, Any]:
    try:
        asset = inspect_file(path)
    except IntakeError as exc:
        raise ProcessorError(str(exc)) from exc
    if asset["media_type"] not in expected:
        expected_names = ", ".join(sorted(expected))
        raise ProcessorError(f"processor requires {expected_names} input")
    return asset


def _run(
    command: list[str],
    *,
    timeout: float,
    max_output_bytes: int = 64 * 1024 * 1024,
) -> subprocess.CompletedProcess[str]:
    """Execute a local tool without a shell and spool its output to bounded temp files."""
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes < 1024:
        raise ProcessorError("max_output_bytes must be an integer of at least 1024")
    try:
        with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(mode="w+b") as stderr_file:
            try:
                completed = subprocess.run(
                    command,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=timeout,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ProcessorError(f"processor timed out after {timeout:g} seconds") from exc
            except OSError as exc:
                raise ProcessorError(f"processor could not be started: {exc}") from exc

            stdout_size = stdout_file.tell()
            stderr_size = stderr_file.tell()
            if stdout_size + stderr_size > max_output_bytes:
                raise ProcessorError("processor output exceeds the configured byte limit")
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")

        result = subprocess.CompletedProcess(command, completed.returncode, stdout, stderr)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:500]
            suffix = f": {detail}" if detail else ""
            raise ProcessorError(f"processor exited with status {result.returncode}{suffix}")
        return result
    except ProcessorError:
        raise
    except OSError as exc:
        raise ProcessorError(f"processor output could not be collected: {exc}") from exc


class OCRProcessor:
    """Extract page/word text and geometry from JPEG/PNG files using Tesseract TSV."""

    def __init__(
        self,
        *,
        tesseract_path: str | os.PathLike[str] | None = None,
        timeout_seconds: float = 60.0,
        max_text_chars: int = 2_000_000,
    ) -> None:
        self.tesseract_path = tesseract_path
        self.timeout_seconds = _check_timeout(timeout_seconds)
        if isinstance(max_text_chars, bool) or not isinstance(max_text_chars, int) or max_text_chars < 1:
            raise ProcessorError("max_text_chars must be a positive integer")
        self.max_text_chars = max_text_chars

    @staticmethod
    def _validate_languages(languages: str) -> str:
        if not isinstance(languages, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", languages):
            raise ProcessorError("language must be a safe Tesseract language code or plus-separated list")
        return languages

    def process(self, path: str | os.PathLike[str], *, languages: str = "eng") -> dict[str, Any]:
        asset = _inspect(path, {"image"})
        if asset["metadata"]["detected_format"] not in {"jpeg", "png"}:
            raise ProcessorError("OCR processor requires a JPEG or PNG image")
        language_arg = self._validate_languages(languages)
        executable = _resolve_executable(self.tesseract_path, "tesseract")
        result = _run(
            [executable, str(Path(path).resolve(strict=True)), "stdout", "-l", language_arg, "tsv"],
            timeout=self.timeout_seconds,
            max_output_bytes=self.max_text_chars * 8 + 4096,
        )
        if len(result.stdout) > self.max_text_chars * 8 + 4096:
            raise ProcessorError("OCR TSV output exceeds the configured processing limit")

        pages: dict[int, dict[str, Any]] = {}
        try:
            reader = csv.DictReader(io.StringIO(result.stdout), delimiter="\t")
            required = {"level", "page_num", "left", "top", "width", "height", "conf", "text"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ProcessorError("Tesseract did not return the expected TSV columns")
            for row in reader:
                if row.get("level") != "5" or not (row.get("text") or "").strip():
                    continue
                try:
                    page_number = int(row["page_num"])
                    bbox = {
                        "x": int(row["left"]),
                        "y": int(row["top"]),
                        "width": int(row["width"]),
                        "height": int(row["height"]),
                    }
                    confidence = float(row["conf"])
                except (TypeError, ValueError, KeyError) as exc:
                    raise ProcessorError("Tesseract returned malformed word geometry") from exc
                if page_number < 1 or not math.isfinite(confidence):
                    raise ProcessorError("Tesseract returned invalid page or confidence data")
                confidence = max(0.0, min(100.0, confidence))
                page = pages.setdefault(page_number, {"page": page_number, "words": []})
                page["words"].append({
                    "text": row["text"].strip(),
                    "confidence": confidence,
                    "bbox": bbox,
                })
        except csv.Error as exc:
            raise ProcessorError(f"cannot parse Tesseract TSV output: {exc}") from exc

        output_pages = []
        for page_number in sorted(pages):
            words = pages[page_number]["words"]
            page_text = " ".join(item["text"] for item in words)
            output_pages.append({"page": page_number, "text": page_text, "words": words})
        text = "\n".join(item["text"] for item in output_pages)
        if len(text) > self.max_text_chars:
            raise ProcessorError("OCR text exceeds the configured processing limit")
        return {
            "processor": "tesseract",
            "processor_version": 1,
            "asset": asset,
            "language": language_arg,
            "page_count": len(output_pages),
            "pages": output_pages,
            "text": text,
        }


class PDFTextProcessor:
    """Extract selectable text from a PDF using Poppler's pdftotext utility."""

    def __init__(
        self,
        *,
        pdftotext_path: str | os.PathLike[str] | None = None,
        timeout_seconds: float = 60.0,
        max_text_chars: int = 5_000_000,
    ) -> None:
        self.pdftotext_path = pdftotext_path
        self.timeout_seconds = _check_timeout(timeout_seconds)
        if isinstance(max_text_chars, bool) or not isinstance(max_text_chars, int) or max_text_chars < 1:
            raise ProcessorError("max_text_chars must be a positive integer")
        self.max_text_chars = max_text_chars

    def process(self, path: str | os.PathLike[str]) -> dict[str, Any]:
        asset = _inspect(path, {"document"})
        if asset["metadata"]["detected_format"] != "pdf":
            raise ProcessorError("PDF text processor requires a PDF file")
        executable = _resolve_executable(self.pdftotext_path, "pdftotext")
        result = _run(
            [executable, "-layout", "-enc", "UTF-8", str(Path(path).resolve(strict=True)), "-"],
            timeout=self.timeout_seconds,
            max_output_bytes=self.max_text_chars + 4096,
        )
        if len(result.stdout) > self.max_text_chars:
            raise ProcessorError("PDF text exceeds the configured processing limit")
        raw_pages = result.stdout.split("\f")
        while raw_pages and not raw_pages[-1].strip():
            raw_pages.pop()
        pages = [
            {"page": index, "text": page.strip()}
            for index, page in enumerate(raw_pages, start=1)
            if page.strip()
        ]
        return {
            "processor": "pdftotext",
            "processor_version": 1,
            "asset": asset,
            "page_count": len(pages),
            "pages": pages,
            "text": "\n".join(item["text"] for item in pages),
        }


def _whisper_time(value: Any, *, milliseconds: bool) -> int:
    if isinstance(value, bool):
        raise ProcessorError("ASR segment timestamp must be numeric")
    if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
        return int(round(value if milliseconds else value * 1000))
    if isinstance(value, str):
        match = re.fullmatch(r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})", value)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            millis = int(match.group(4))
            return ((hours * 3600 + minutes * 60 + seconds) * 1000) + millis
    raise ProcessorError("ASR segment timestamp has an unsupported format")


class ASRProcessor:
    """Run whisper.cpp locally with an explicitly supplied model file."""

    def __init__(
        self,
        *,
        model_path: str | os.PathLike[str],
        executable: str | os.PathLike[str] | None = None,
        timeout_seconds: float = 1800.0,
        max_segments: int = 100_000,
        max_text_chars: int = 5_000_000,
    ) -> None:
        self.model_path = Path(model_path)
        self.executable = executable
        self.timeout_seconds = _check_timeout(timeout_seconds)
        if isinstance(max_segments, bool) or not isinstance(max_segments, int) or max_segments < 1:
            raise ProcessorError("max_segments must be a positive integer")
        if isinstance(max_text_chars, bool) or not isinstance(max_text_chars, int) or max_text_chars < 1:
            raise ProcessorError("max_text_chars must be a positive integer")
        self.max_segments = max_segments
        self.max_text_chars = max_text_chars

    def process(self, path: str | os.PathLike[str]) -> dict[str, Any]:
        asset = _inspect(path, {"audio"})
        try:
            model = self.model_path.resolve(strict=True)
        except OSError as exc:
            raise ProcessorError("ASR model file does not exist") from exc
        if not model.is_file() or model.stat().st_size <= 0:
            raise ProcessorError("ASR model must be a non-empty local model file")
        executable = _resolve_executable(self.executable, "whisper-cli")

        with tempfile.TemporaryDirectory(prefix="ri-asr-") as temporary:
            prefix = Path(temporary) / "transcript"
            _run(
                [executable, "-m", str(model), "-f", str(Path(path).resolve(strict=True)), "-oj", "-of", str(prefix)],
                timeout=self.timeout_seconds,
                max_output_bytes=8 * 1024 * 1024,
            )
            json_path = prefix.with_suffix(".json")
            try:
                if json_path.stat().st_size > self.max_text_chars * 16 + 1_000_000:
                    raise ProcessorError("ASR JSON exceeds the configured processing limit")
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise ProcessorError("whisper.cpp did not create its JSON transcript") from exc
            except json.JSONDecodeError as exc:
                raise ProcessorError("whisper.cpp returned malformed JSON") from exc
            except OSError as exc:
                raise ProcessorError(f"cannot read whisper.cpp transcript: {exc}") from exc

        if not isinstance(payload, dict):
            raise ProcessorError("ASR JSON root must be an object")
        raw_segments = payload.get("transcription", payload.get("segments"))
        if not isinstance(raw_segments, list):
            raise ProcessorError("ASR JSON must contain a transcription or segments array")
        if len(raw_segments) > self.max_segments:
            raise ProcessorError("ASR segment count exceeds the configured processing limit")

        segments = []
        for item in raw_segments:
            if not isinstance(item, dict):
                raise ProcessorError("ASR segment must be an object")
            offsets = item.get("offsets")
            timestamps = item.get("timestamps")
            if isinstance(offsets, dict):
                start = _whisper_time(offsets.get("from"), milliseconds=True)
                end = _whisper_time(offsets.get("to"), milliseconds=True)
            elif isinstance(timestamps, dict):
                start = _whisper_time(timestamps.get("from"), milliseconds=False)
                end = _whisper_time(timestamps.get("to"), milliseconds=False)
            else:
                start = _whisper_time(item.get("start"), milliseconds=False)
                end = _whisper_time(item.get("end"), milliseconds=False)
            text = item.get("text")
            if not isinstance(text, str):
                raise ProcessorError("ASR segment text must be a string")
            text = text.strip()
            if not text or end < start:
                raise ProcessorError("ASR segment text or interval is invalid")
            segments.append({"start_ms": start, "end_ms": end, "text": text})

        transcript = " ".join(item["text"] for item in segments)
        if len(transcript) > self.max_text_chars:
            raise ProcessorError("ASR transcript exceeds the configured processing limit")
        return {
            "processor": "whisper.cpp",
            "processor_version": 1,
            "asset": asset,
            "model": {"filename": model.name, "byte_size": model.stat().st_size},
            "segment_count": len(segments),
            "segments": segments,
            "text": transcript,
        }


class SceneDetectionProcessor:
    """Use FFmpeg's scene-change filter and showinfo to emit timestamp-only markers."""

    def __init__(
        self,
        *,
        ffmpeg_path: str | os.PathLike[str] | None = None,
        threshold: float = 0.35,
        max_scenes: int = 2000,
        max_duration_seconds: float = 7200.0,
        timeout_seconds: float = 600.0,
    ) -> None:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0.01 <= threshold <= 0.99:
            raise ProcessorError("threshold must be between 0.01 and 0.99")
        if isinstance(max_scenes, bool) or not isinstance(max_scenes, int) or not 1 <= max_scenes <= 50_000:
            raise ProcessorError("max_scenes must be between 1 and 50000")
        if isinstance(max_duration_seconds, bool) or not isinstance(max_duration_seconds, (int, float)) or not math.isfinite(max_duration_seconds) or not 1 <= max_duration_seconds <= 86_400:
            raise ProcessorError("max_duration_seconds must be between 1 and 86400")
        self.ffmpeg_path = ffmpeg_path
        self.threshold = float(threshold)
        self.max_scenes = max_scenes
        self.max_duration_seconds = float(max_duration_seconds)
        self.timeout_seconds = _check_timeout(timeout_seconds)

    def process(self, path: str | os.PathLike[str]) -> dict[str, Any]:
        asset = _inspect(path, {"video"})
        if asset["metadata"]["detected_format"] != "mp4":
            raise ProcessorError("scene detection currently requires MP4 video")
        executable = _resolve_executable(self.ffmpeg_path, "ffmpeg")
        filter_expression = f"select='gt(scene,{self.threshold:.4f})',showinfo"
        result = _run(
            [
                executable, "-nostdin", "-hide_banner", "-i", str(Path(path).resolve(strict=True)),
                "-t", str(self.max_duration_seconds), "-vf", filter_expression,
                "-an", "-f", "null", "-",
            ],
            timeout=self.timeout_seconds,
            max_output_bytes=32 * 1024 * 1024,
        )
        matches = re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr)
        timestamps = []
        previous = -1
        for raw in matches:
            milliseconds = int(round(float(raw) * 1000))
            if milliseconds < 0 or milliseconds <= previous:
                continue
            timestamps.append({"start_ms": milliseconds, "event_type": "scene_change"})
            previous = milliseconds
            if len(timestamps) >= self.max_scenes:
                break
        return {
            "processor": "ffmpeg-scene-detect",
            "processor_version": 1,
            "asset": asset,
            "threshold": self.threshold,
            "scene_count": len(timestamps),
            "scenes": timestamps,
            "truncated": len(matches) > len(timestamps),
        }


class PDFPageRenderer:
    """Render PDF pages to PNG with Poppler in a new, isolated output directory."""

    def __init__(
        self,
        *,
        pdftoppm_path: str | os.PathLike[str] | None = None,
        dpi: int = 150,
        max_pages: int = 200,
        timeout_seconds: float = 180.0,
        max_page_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        if isinstance(dpi, bool) or not isinstance(dpi, int) or not 72 <= dpi <= 300:
            raise ProcessorError("dpi must be an integer between 72 and 300")
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 1000:
            raise ProcessorError("max_pages must be an integer between 1 and 1000")
        if isinstance(max_page_bytes, bool) or not isinstance(max_page_bytes, int) or max_page_bytes < 1024:
            raise ProcessorError("max_page_bytes must be an integer of at least 1024")
        self.pdftoppm_path = pdftoppm_path
        self.dpi = dpi
        self.max_pages = max_pages
        self.timeout_seconds = _check_timeout(timeout_seconds)
        self.max_page_bytes = max_page_bytes

    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()

    def process(self, path: str | os.PathLike[str], output_dir: str | os.PathLike[str]) -> dict[str, Any]:
        asset = _inspect(path, {"document"})
        if asset["metadata"]["detected_format"] != "pdf":
            raise ProcessorError("PDF page renderer requires a PDF file")

        destination = Path(output_dir)
        if destination.exists() or destination.is_symlink():
            raise ProcessorError("PDF render output directory already exists")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = destination.parent.resolve(strict=True) / destination.name
            destination.mkdir(mode=0o700)
        except OSError as exc:
            raise ProcessorError(f"cannot create PDF render output directory: {exc}") from exc

        try:
            executable = _resolve_executable(self.pdftoppm_path, "pdftoppm")
            prefix = destination / "page"
            _run(
                [
                    executable, "-png", "-r", str(self.dpi), "-f", "1", "-l",
                    str(self.max_pages), str(Path(path).resolve(strict=True)), str(prefix),
                ],
                timeout=self.timeout_seconds,
                max_output_bytes=1024 * 1024,
            )

            page_files = []
            pattern = re.compile(r"^page-(\d+)\.png$")
            for page_path in sorted(destination.glob("page-*.png"), key=lambda item: item.name.casefold()):
                if page_path.is_symlink() or not page_path.is_file():
                    raise ProcessorError("Poppler produced a non-regular PDF page image")
                match = pattern.match(page_path.name)
                if match is None:
                    raise ProcessorError("Poppler produced an unexpected page image filename")
                page_number = int(match.group(1))
                size = page_path.stat().st_size
                if page_number < 1 or page_number > self.max_pages or size <= 0:
                    raise ProcessorError("Poppler produced an invalid page number or empty image")
                if size > self.max_page_bytes:
                    raise ProcessorError("rendered PDF page exceeds the configured byte limit")
                page_files.append({
                    "page": page_number,
                    "path": page_path.name,
                    "byte_size": size,
                    "sha256": self._sha256(page_path),
                })
            page_files.sort(key=lambda item: item["page"])
            if len(page_files) > self.max_pages:
                raise ProcessorError("Poppler produced more pages than the configured limit")
            if not page_files:
                raise ProcessorError("Poppler did not render any PDF pages")
            return {
                "processor": "pdftoppm",
                "processor_version": 1,
                "asset": asset,
                "dpi": self.dpi,
                "page_count": len(page_files),
                "pages": page_files,
            }
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
