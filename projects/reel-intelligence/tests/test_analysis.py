import json
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


def make_png(tmp_path):
    media = tmp_path / "sample.png"
    media.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    return media


def make_pdf(tmp_path):
    media = tmp_path / "sample.pdf"
    media.write_bytes(b"%PDF-1.7\n%test")
    return media


def make_wav(tmp_path):
    media = tmp_path / "sample.wav"
    media.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    return media


def make_executable(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def test_analyze_media_writes_image_evidence_report_without_absolute_path(tmp_path):
    from reel_intelligence.analysis import analyze_media

    image = make_png(tmp_path)
    tesseract = make_executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext")
print("5\t1\t1\t1\t1\t1\t10\t20\t100\t25\t96\tLaunch")
print("5\t1\t1\t1\t1\t2\t115\t20\t80\t25\t94\tchecklist")
""")
    output = tmp_path / "image-report"
    report = analyze_media(image, output, tesseract_path=tesseract)

    evidence = [item for item in report["records"] if item["record_type"] == "evidence"]
    assert report["manifest"]["status"] == "completed"
    assert len(evidence) == 1
    assert evidence[0]["observation"] == "Launch checklist"
    assert str(tmp_path) not in json.dumps(report, ensure_ascii=False)
    assert (output / "analysis.json").is_file()
    assert validate_bundle(report["records"]) == report["records"]


def test_analyze_media_extracts_pdf_pages(tmp_path):
    from reel_intelligence.analysis import analyze_media

    pdf = make_pdf(tmp_path)
    pdftotext = make_executable(tmp_path, "pdftotext", """#!/usr/bin/env python3
print("Page one\\fPage two\\f")
""")
    report = analyze_media(pdf, tmp_path / "pdf-report", pdftotext_path=pdftotext)
    evidence = [item for item in report["records"] if item["record_type"] == "evidence"]

    assert [item["locator"] for item in evidence] == [{"page": 1}, {"page": 2}]
    assert [item["observation"] for item in evidence] == ["Page one", "Page two"]


def test_analyze_media_creates_asr_evidence_and_timeline(tmp_path):
    from reel_intelligence.analysis import analyze_media

    audio = make_wav(tmp_path)
    model = tmp_path / "ggml-tiny.bin"
    model.write_bytes(b"model-placeholder")
    whisper = make_executable(tmp_path, "whisper-cli", """#!/usr/bin/env python3
import json, pathlib, sys
prefix = sys.argv[sys.argv.index("-of") + 1]
pathlib.Path(prefix + ".json").write_text(json.dumps({"transcription":[
  {"offsets":{"from":500,"to":1500},"text":"open the file"},
  {"offsets":{"from":1500,"to":2500},"text":"inspect metadata"}
]}), encoding="utf-8")
""")
    report = analyze_media(
        audio, tmp_path / "audio-report",
        whisper_model=model, whisper_path=whisper,
    )
    timeline = [item for item in report["records"] if item["record_type"] == "timeline_event"]
    assert len(timeline) == 2
    assert timeline[0]["start_ms"] == 500
    assert timeline[1]["text"] == "inspect metadata"


def test_analyze_media_records_partial_status_when_optional_backend_is_missing(tmp_path):
    from reel_intelligence.analysis import analyze_media

    report = analyze_media(
        make_png(tmp_path), tmp_path / "partial-report",
        tesseract_path=tmp_path / "missing-tesseract",
    )
    assert report["manifest"]["status"] == "partial"
    assert report["manifest"]["warnings"]


def test_analyze_media_never_overwrites_existing_output(tmp_path):
    from reel_intelligence.analysis import analyze_media

    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(AnalysisError, match="already exists"):
        analyze_media(make_png(tmp_path), output)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_ocr_page_locator_preserves_relative_path_page_number_and_hash(tmp_path):
    asset = make_asset(tmp_path)
    digest = "a" * 64
    bundle = build_analysis_bundle(
        asset,
        ocr_observations=[{
            "path": "pdf-pages/page-2.png",
            "page": 2,
            "timestamp_ms": 0,
            "text": "Page two",
            "modality": "document",
            "content_hash": digest,
        }],
    )
    evidence = next(item for item in bundle["records"] if item["record_type"] == "evidence")

    assert evidence["modality"] == "document"
    assert evidence["locator"]["page"] == 2
    assert evidence["locator"]["path"] == "pdf-pages/page-2.png"
    assert evidence["content_hash"] == digest


def test_warning_without_any_evidence_marks_analysis_failed(tmp_path):
    asset = make_asset(tmp_path)
    bundle = build_analysis_bundle(asset, warnings=["ASR executable unavailable"])
    manifest = bundle["manifest"]

    assert manifest["status"] == "failed"
