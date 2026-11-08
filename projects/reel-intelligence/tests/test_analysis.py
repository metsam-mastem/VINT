from datetime import datetime, timezone

import pytest

from reel_intelligence.analysis import AnalysisError, build_analysis_bundle
from reel_intelligence.contracts import validate_bundle
from reel_intelligence.intake import inspect_file


def make_asset(tmp_path):
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00test")
    return inspect_file(media)


def test_builds_canonical_evidence_and_timeline_from_modalities(tmp_path):
    asset = make_asset(tmp_path)
    bundle = build_analysis_bundle(
        asset,
        transcript_segments=[{"start_ms": 0, "end_ms": 1200, "text": "سلام دنیا"}],
        ocr_observations=[{"path": "frames/frame-000001.jpg", "timestamp_ms": 500, "text": "متن روی تصویر"}],
        scene_boundaries_ms=[2500],
        toolchain={"asr": "whisper.cpp", "ocr": "tesseract", "scene": "ffmpeg"},
    )

    validated = validate_bundle([asset, *bundle["records"]])
    evidence = [item for item in validated if item["record_type"] == "evidence"]
    events = [item for item in validated if item["record_type"] == "timeline_event"]
    manifests = [item for item in validated if item["record_type"] == "analysis_manifest"]

    assert len(evidence) == 3
    assert len(events) == 3
    assert len(manifests) == 1
    assert manifests[0]["status"] == "completed"
    assert {item["modality"] for item in evidence} == {"audio", "image", "video"}
    assert all(item["asset_id"] == asset["asset_id"] for item in evidence)
    assert all(len(item["evidence_ids"]) == 1 for item in events)


def test_analysis_evidence_ids_are_deterministic_for_same_observation(tmp_path):
    asset = make_asset(tmp_path)
    payload = {"transcript_segments": [{"start_ms": 5, "end_ms": 10, "text": "same"}]}

    first = build_analysis_bundle(asset, **payload)
    second = build_analysis_bundle(asset, **payload)

    first_ids = sorted(item["evidence_id"] for item in first["records"] if item["record_type"] == "evidence")
    second_ids = sorted(item["evidence_id"] for item in second["records"] if item["record_type"] == "evidence")
    assert first_ids == second_ids


def test_analysis_rejects_absolute_or_parent_traversal_ocr_paths(tmp_path):
    asset = make_asset(tmp_path)

    with pytest.raises(AnalysisError, match="relative"):
        build_analysis_bundle(
            asset,
            ocr_observations=[{"path": "../outside.png", "timestamp_ms": 0, "text": "private"}],
        )


def test_analysis_rejects_empty_transcript_and_invalid_intervals(tmp_path):
    asset = make_asset(tmp_path)

    with pytest.raises(AnalysisError, match="text"):
        build_analysis_bundle(
            asset,
            transcript_segments=[{"start_ms": 0, "end_ms": 100, "text": "  "}],
        )
    with pytest.raises(AnalysisError, match="interval"):
        build_analysis_bundle(
            asset,
            transcript_segments=[{"start_ms": 100, "end_ms": 50, "text": "bad"}],
        )


def test_analysis_partial_status_records_processor_warnings(tmp_path):
    asset = make_asset(tmp_path)
    bundle = build_analysis_bundle(
        asset,
        transcript_segments=[{"start_ms": 0, "end_ms": 10, "text": "hi"}],
        warnings=["OCR executable unavailable"],
    )
    manifest = next(item for item in bundle["records"] if item["record_type"] == "analysis_manifest")

    assert manifest["status"] == "partial"
    assert manifest["warnings"] == ["OCR executable unavailable"]
