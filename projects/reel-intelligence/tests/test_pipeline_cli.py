import json

import pytest

import reel_intelligence.analysis_cli as cli
from reel_intelligence.pipeline import PipelineError


def test_analyze_cli_forwards_local_processor_options(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_run(input_path, output_dir, **kwargs):
        captured.update({"input": input_path, "output": output_dir, **kwargs})
        return {
            "asset": {"asset_id": "asset-123", "filename": "clip.mp4"},
            "manifest": {"status": "partial"},
            "records": [
                {"record_type": "evidence", "evidence_id": "e1"},
                {"record_type": "timeline_event", "event_id": "t1"},
            ],
            "warnings": ["OCR unavailable"],
            "output_dir": str(output_dir),
        }

    monkeypatch.setattr(cli, "run_local_analysis", fake_run)
    code = cli.main([
        "clip.mp4",
        "--output", str(tmp_path / "run"),
        "--whisper-model", str(tmp_path / "tiny.bin"),
        "--whisper-cli", "/tools/whisper-cli",
        "--tesseract", "/tools/tesseract",
        "--no-scene-detection",
        "--frame-interval", "3",
        "--max-frames", "16",
        "--max-ocr-frames", "4",
    ])

    assert code == 0
    assert captured["asr_model_path"] == str(tmp_path / "tiny.bin")
    assert captured["whisper_executable"] == "/tools/whisper-cli"
    assert captured["tesseract_path"] == "/tools/tesseract"
    assert captured["enable_scene_detection"] is False
    assert captured["frame_interval_seconds"] == 3
    assert captured["max_frames"] == 16
    assert captured["max_ocr_frames"] == 4
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "partial"
    assert result["counts"] == {"evidence": 1, "timeline_events": 1}


def test_analyze_cli_uses_strict_mode_and_reports_pipeline_failures(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        raise PipelineError("optional processor failed")

    monkeypatch.setattr(cli, "run_local_analysis", fake_run)
    code = cli.main(["input.png", "--output", str(tmp_path / "run"), "--strict"])

    assert code == 2
    assert captured["fail_fast"] is True
    assert "optional processor failed" in capsys.readouterr().err


def test_analyze_cli_returns_nonzero_for_failed_manifest(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "run_local_analysis", lambda *args, **kwargs: {
        "asset": {"asset_id": "asset-1", "filename": "bad.png"},
        "manifest": {"status": "failed"},
        "records": [],
        "warnings": ["No processor could run"],
        "output_dir": str(tmp_path / "run"),
    })

    code = cli.main(["bad.png", "--output", str(tmp_path / "run")])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_analyze_cli_rejects_invalid_numbers(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["input.mp4", "--output", str(tmp_path / "run"), "--max-frames", "0"])
    assert exc.value.code == 2


def test_analyze_cli_help_is_available(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "ri-analyze" in capsys.readouterr().out
