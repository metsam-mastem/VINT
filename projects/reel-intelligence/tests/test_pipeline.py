import json

import pytest

from reel_intelligence.pipeline import PipelineError, run_local_analysis


def executable(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def make_image(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    return path


def make_pdf(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.7\n%test")
    return path


def make_video(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00")
    return path


def fake_tesseract(tmp_path):
    return executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext")
print("5\t1\t1\t1\t1\t1\t12\t18\t90\t24\t97.5\tHello")
""")


def test_image_pipeline_runs_local_ocr_and_writes_canonical_report(tmp_path):
    image = make_image(tmp_path)
    output = tmp_path / "runs" / "image-001"

    result = run_local_analysis(
        image,
        output,
        tesseract_path=fake_tesseract(tmp_path),
        enable_scene_detection=False,
    )

    analysis = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert result["manifest"]["status"] == "completed"
    assert any(item["record_type"] == "evidence" and item["modality"] == "image" for item in result["records"])
    assert analysis["asset"]["asset_id"] == result["asset"]["asset_id"]
    assert run_manifest["asset_sha256"] == result["asset"]["sha256"]
    assert str(tmp_path) not in json.dumps(run_manifest)


def test_video_pipeline_runs_extraction_asr_ocr_and_scene_detection(tmp_path):
    video = make_video(tmp_path)
    model = tmp_path / "tiny-q5.bin"
    model.write_bytes(b"local-model")
    ffprobe = executable(tmp_path, "ffprobe", """#!/usr/bin/env python3
import json
print(json.dumps({"format":{"duration":"6.0"},"streams":[
 {"codec_type":"video","codec_name":"h264","width":640,"height":360},
 {"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":2}
]}))
""")
    ffmpeg = executable(tmp_path, "ffmpeg", """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv[1:]
if "-f" in args and args[args.index("-f") + 1] == "image2":
    pathlib.Path(args[-1].replace("%06d", "000001")).write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
elif "-f" in args and args[args.index("-f") + 1] == "wav":
    pathlib.Path(args[-1]).write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
else:
    sys.stderr.write("pts_time:2.500\n")
""")
    whisper = executable(tmp_path, "whisper-cli", """#!/usr/bin/env python3
import json, pathlib, sys
prefix = sys.argv[sys.argv.index("-of") + 1]
pathlib.Path(prefix + ".json").write_text(json.dumps({"transcription":[
 {"offsets":{"from":250,"to":1250},"text":" hello from media"}
]}), encoding="utf-8")
""")
    output = tmp_path / "runs" / "video-001"

    result = run_local_analysis(
        video,
        output,
        ffprobe_path=ffprobe,
        ffmpeg_path=ffmpeg,
        asr_model_path=model,
        whisper_executable=whisper,
        tesseract_path=fake_tesseract(tmp_path),
        enable_scene_detection=True,
        frame_interval_seconds=2,
        max_frames=5,
    )

    modalities = {
        item["modality"] for item in result["records"]
        if item["record_type"] == "evidence"
    }
    assert modalities == {"audio", "image", "video"}
    assert result["manifest"]["status"] == "completed"
    assert (output / "derived" / "audio.wav").is_file()
    assert (output / "extraction.json").is_file()
    assert (output / "analysis.json").is_file()


def test_pdf_pipeline_falls_back_to_page_rendering_and_ocr(tmp_path):
    pdf = make_pdf(tmp_path)
    pdftotext = executable(tmp_path, "pdftotext", """#!/usr/bin/env python3
print("\\f")
""")
    pdftoppm = executable(tmp_path, "pdftoppm", """#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(sys.argv[-1] + "-1.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
""")
    output = tmp_path / "runs" / "pdf-001"

    result = run_local_analysis(
        pdf,
        output,
        pdftotext_path=pdftotext,
        pdftoppm_path=pdftoppm,
        tesseract_path=fake_tesseract(tmp_path),
        enable_scene_detection=False,
    )

    evidence = [item for item in result["records"] if item["record_type"] == "evidence"]
    assert result["manifest"]["status"] == "completed"
    assert any(item["modality"] == "image" for item in evidence)
    assert (output / "pdf-pages" / "page-1.png").is_file()


def test_pipeline_refuses_to_overwrite_a_previous_run(tmp_path):
    image = make_image(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(PipelineError, match="already exists"):
        run_local_analysis(image, output, tesseract_path=fake_tesseract(tmp_path))

    assert marker.read_text(encoding="utf-8") == "keep"


def test_pipeline_reports_missing_optional_tools_as_partial_result(tmp_path):
    image = make_image(tmp_path)
    output = tmp_path / "missing-tool-run"

    result = run_local_analysis(
        image,
        output,
        tesseract_path="tool-that-does-not-exist-ri",
        enable_scene_detection=False,
        fail_fast=False,
    )

    assert result["manifest"]["status"] == "failed"
    assert result["manifest"]["warnings"]
    assert (output / "run_manifest.json").is_file()
