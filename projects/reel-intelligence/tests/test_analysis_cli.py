import json

import pytest

import reel_intelligence.analysis_cli as cli
from reel_intelligence.analysis import AnalysisError
from reel_intelligence.analysis_cli import main


def executable(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def make_image(tmp_path):
    path = tmp_path / "sample.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    return path


def test_analyze_cli_writes_report_and_prints_relative_summary(tmp_path, capsys):
    image = make_image(tmp_path)
    tesseract = executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext")
print("5\t1\t1\t1\t1\t1\t1\t1\t20\t10\t95\tready")
""")
    output = tmp_path / "analysis"

    assert main([str(image), "--output", str(output), "--tesseract", tesseract]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "completed"
    assert summary["analysis_file"] == "analysis.json"
    assert summary["evidence_count"] == 1
    assert str(tmp_path) not in json.dumps(summary)
    assert (output / "analysis.json").is_file()


def test_analyze_cli_returns_error_for_existing_output_and_strict_backend_failure(tmp_path, capsys):
    image = make_image(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()

    assert main([str(image), "--output", str(existing)]) == 2
    assert "already exists" in capsys.readouterr().err

    assert main([
        str(image), "--output", str(tmp_path / "strict"),
        "--tesseract", str(tmp_path / "missing"), "--strict",
    ]) == 2
    assert "Tesseract" in capsys.readouterr().err or "tesseract" in capsys.readouterr().err


def test_cli_forwards_local_processor_settings(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_analyze(input_path, output_dir, **kwargs):
        captured.update({"input": input_path, "output": output_dir, **kwargs})
        return {
            "asset": {"asset_id": "asset-123", "filename": "clip.mp4"},
            "manifest": {"status": "partial", "warnings": ["OCR skipped"]},
            "records": [
                {"record_type": "asset", "asset_id": "asset-123"},
                {"record_type": "evidence", "evidence_id": "ev1"},
                {"record_type": "timeline_event", "event_id": "te1"},
            ],
            "processor_results": [{"processor": "ffmpeg", "status": "completed"}],
            "artifacts": [{"path": "derivatives/frame-000001.jpg", "kind": "video_frame"}],
            "claims": [],
        }

    monkeypatch.setattr(cli, "analyze_media", fake_analyze)
    code = cli.main([
        "clip.mp4", "--output", str(tmp_path / "run"),
        "--whisper-model", str(tmp_path / "tiny.bin"),
        "--whisper-cli", "/tools/whisper-cli",
        "--tesseract", "/tools/tesseract",
        "--ffmpeg", "/tools/ffmpeg",
        "--ffprobe", "/tools/ffprobe",
        "--no-scenes", "--no-ocr",
        "--frame-interval", "3", "--max-frames", "16",
        "--max-ocr-frames", "4", "--max-duration", "120",
    ])

    assert code == 0
    assert captured["whisper_model"] == str(tmp_path / "tiny.bin")
    assert captured["whisper_path"] == "/tools/whisper-cli"
    assert captured["tesseract_path"] == "/tools/tesseract"
    assert captured["ffmpeg_path"] == "/tools/ffmpeg"
    assert captured["ffprobe_path"] == "/tools/ffprobe"
    assert captured["enable_scenes"] is False
    assert captured["enable_ocr"] is False
    assert captured["frame_interval_seconds"] == 3
    assert captured["max_frames"] == 16
    assert captured["max_ocr_frames"] == 4
    assert captured["max_duration_seconds"] == 120
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "partial"
    assert summary["counts"]["evidence"] == 1
    assert summary["counts"]["timeline_events"] == 1


def test_cli_strict_mode_and_failed_manifest_return_nonzero(monkeypatch, capsys, tmp_path):
    def fake_analyze(*args, **kwargs):
        if kwargs["strict"]:
            raise AnalysisError("required processor failed")
        return {
            "asset": {"asset_id": "asset-1", "filename": "bad.png"},
            "manifest": {"status": "failed", "warnings": ["No evidence could be produced"]},
            "records": [{"record_type": "asset", "asset_id": "asset-1"}],
            "processor_results": [],
            "artifacts": [],
            "claims": [],
        }

    monkeypatch.setattr(cli, "analyze_media", fake_analyze)
    assert cli.main(["input.png", "--output", str(tmp_path / "strict"), "--strict"]) == 2
    assert "required processor failed" in capsys.readouterr().err
    assert cli.main(["bad.png", "--output", str(tmp_path / "failed")]) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "failed"


def test_cli_help_is_available(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "ri-analyze" in capsys.readouterr().out
