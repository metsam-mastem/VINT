import json

import pytest

from reel_intelligence.processors import (
    ASRProcessor,
    OCRProcessor,
    PDFTextProcessor,
    ProcessorError,
    SceneDetectionProcessor,
)


def executable(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def make_image(tmp_path):
    path = tmp_path / "sample.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    return path


def make_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.7\n%test")
    return path


def make_wav(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    return path


def make_video(tmp_path):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00")
    return path


def test_ocr_extracts_words_and_page_geometry_without_absolute_paths(tmp_path):
    image = make_image(tmp_path)
    tesseract = executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext")
print("5\t1\t1\t1\t1\t1\t12\t18\t90\t24\t97.5\tEvidence")
""")
    result = OCRProcessor(tesseract_path=tesseract).process(image)

    assert result["text"] == "Evidence"
    assert result["pages"][0]["words"][0]["confidence"] == 97.5
    assert result["pages"][0]["words"][0]["bbox"] == {"x": 12, "y": 18, "width": 90, "height": 24}
    assert str(tmp_path) not in json.dumps(result)


def test_ocr_rejects_non_image_and_bounds_language_parameter(tmp_path):
    pdf = make_pdf(tmp_path)
    with pytest.raises(ProcessorError, match="image"):
        OCRProcessor(tesseract_path="tesseract").process(pdf)
    with pytest.raises(ProcessorError, match="language"):
        OCRProcessor(tesseract_path="tesseract").process(make_image(tmp_path), languages="eng;rm -rf")


def test_ocr_enforces_output_limit(tmp_path):
    image = make_image(tmp_path)
    tesseract = executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext")
print("5\t1\t1\t1\t1\t1\t1\t1\t1\t1\t90\toversized")
""")
    with pytest.raises(ProcessorError, match="exceeds"):
        OCRProcessor(tesseract_path=tesseract, max_text_chars=4).process(image)


def test_pdf_text_extraction_splits_pages_and_preserves_unicode(tmp_path):
    pdf = make_pdf(tmp_path)
    pdftotext = executable(tmp_path, "pdftotext", """#!/usr/bin/env python3
print("صفحه اول\fPage two\f")
""")
    result = PDFTextProcessor(pdftotext_path=pdftotext).process(pdf)

    assert [page["text"] for page in result["pages"]] == ["صفحه اول", "Page two"]
    assert result["page_count"] == 2


def test_asr_normalizes_whisper_cpp_json_segments(tmp_path):
    audio = make_wav(tmp_path)
    model = tmp_path / "ggml-tiny.bin"
    model.write_bytes(b"model-placeholder")
    whisper = executable(tmp_path, "whisper-cli", """#!/usr/bin/env python3
import json, pathlib, sys
prefix = sys.argv[sys.argv.index("-of") + 1]
pathlib.Path(prefix + ".json").write_text(json.dumps({"transcription":[
  {"offsets":{"from":250,"to":1200},"text":" hello"},
  {"offsets":{"from":1200,"to":2400},"text":" world"}
]}), encoding="utf-8")
""")
    result = ASRProcessor(model_path=model, executable=whisper).process(audio)

    assert result["text"] == "hello world"
    assert result["segments"][0] == {"start_ms": 250, "end_ms": 1200, "text": "hello"}
    assert result["model"]["filename"] == model.name


def test_asr_rejects_missing_model_and_malformed_json(tmp_path):
    audio = make_wav(tmp_path)
    with pytest.raises(ProcessorError, match="model"):
        ASRProcessor(model_path=tmp_path / "missing.bin").process(audio)

    model = tmp_path / "model.bin"
    model.write_bytes(b"m")
    whisper = executable(tmp_path, "bad-whisper", """#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(sys.argv[sys.argv.index("-of") + 1] + ".json").write_text("{", encoding="utf-8")
""")
    with pytest.raises(ProcessorError, match="JSON"):
        ASRProcessor(model_path=model, executable=whisper).process(audio)


def test_scene_detection_returns_sorted_bounded_timestamps(tmp_path):
    video = make_video(tmp_path)
    ffmpeg = executable(tmp_path, "ffmpeg", """#!/usr/bin/env python3
import sys
sys.stderr.write("[Parsed_showinfo] n:0 pts_time:2.500\\n[Parsed_showinfo] n:1 pts_time:5.250\\n")
""")
    result = SceneDetectionProcessor(ffmpeg_path=ffmpeg, threshold=0.35, max_scenes=1).process(video)

    assert result["scene_count"] == 1
    assert result["scenes"][0]["start_ms"] == 2500
    assert result["threshold"] == 0.35


def test_scene_detection_rejects_invalid_threshold_and_non_video(tmp_path):
    image = make_image(tmp_path)
    with pytest.raises(ProcessorError, match="video"):
        SceneDetectionProcessor(ffmpeg_path="ffmpeg").process(image)
    with pytest.raises(ProcessorError, match="threshold"):
        SceneDetectionProcessor(ffmpeg_path="ffmpeg", threshold=1.1)


def test_processors_reject_non_positive_timeout(tmp_path):
    with pytest.raises(ProcessorError, match="timeout"):
        OCRProcessor(timeout_seconds=0)
    with pytest.raises(ProcessorError, match="timeout"):
        PDFTextProcessor(timeout_seconds=0)


def test_pdf_page_renderer_returns_hashed_relative_page_files(tmp_path):
    from reel_intelligence.processors import PDFPageRenderer

    pdf = make_pdf(tmp_path)
    renderer_tool = executable(tmp_path, "pdftoppm", """#!/usr/bin/env python3
import pathlib, sys
prefix = pathlib.Path(sys.argv[-1])
for page in (1, 2):
    pathlib.Path(str(prefix) + f"-{page}.png").write_bytes(b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR")
""")
    output = tmp_path / "rendered"
    result = PDFPageRenderer(pdftoppm_path=renderer_tool).process(pdf, output)

    assert result["page_count"] == 2
    assert result["pages"][0]["page"] == 1
    assert result["pages"][0]["path"] == "page-1.png"
    assert len(result["pages"][0]["sha256"]) == 64
    assert str(tmp_path) not in json.dumps(result)


def test_pdf_page_renderer_refuses_to_overwrite_existing_output(tmp_path):
    from reel_intelligence.processors import PDFPageRenderer

    pdf = make_pdf(tmp_path)
    output = tmp_path / "rendered"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ProcessorError, match="already exists"):
        PDFPageRenderer(pdftoppm_path="pdftoppm").process(pdf, output)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_tesseract_output_is_bounded_before_reading_into_memory(tmp_path):
    image = make_image(tmp_path)
    tesseract = executable(tmp_path, "large-tesseract", """#!/usr/bin/env python3
print("X" * 20000)
""")
    with pytest.raises(ProcessorError, match="output exceeds"):
        OCRProcessor(tesseract_path=tesseract, max_text_chars=100).process(image)
