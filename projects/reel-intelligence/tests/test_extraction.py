import json

import pytest

from reel_intelligence.extraction import ExtractionError, extract_media


def make_media(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00")
    return path


def executable(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def fake_ffprobe(tmp_path, streams=None):
    payload = {"format": {"duration": "8.0"}, "streams": streams if streams is not None else [
        {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
    ]}
    return executable(tmp_path, "ffprobe", "#!/usr/bin/env python3\nimport json\nprint(json.dumps(" + repr(payload) + "))\n")


def fake_ffmpeg(tmp_path, *, fail=False):
    failure = "import sys\nsys.exit(9)\n" if fail else ""
    source = """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv[1:]
""" + failure + """
if "-f" in args and args[args.index("-f") + 1] == "image2":
    target = pathlib.Path(args[-1].replace("%06d", "000001"))
    target.write_bytes(b"fake-jpeg")
elif "-f" in args and args[args.index("-f") + 1] == "wav":
    pathlib.Path(args[-1]).write_bytes(b"fake-wav")
"""
    return executable(tmp_path, "ffmpeg", source)


def test_extracts_video_frames_and_audio_to_new_workspace(tmp_path):
    media = make_media(tmp_path)
    output = tmp_path / "derived" / "clip-run"
    result = extract_media(
        media, output,
        ffprobe_path=fake_ffprobe(tmp_path),
        ffmpeg_path=fake_ffmpeg(tmp_path),
        interval_seconds=2,
        max_frames=10,
    )

    assert result["asset"]["filename"] == "clip.mp4"
    assert result["extraction"]["frame_count"] == 1
    assert result["extraction"]["audio_extracted"] is True
    assert result["files"][0]["path"] == "frames/frame-000001.jpg"
    assert (output / "frames" / "frame-000001.jpg").read_bytes() == b"fake-jpeg"
    assert (output / "audio.wav").read_bytes() == b"fake-wav"


def test_rejects_existing_output_directory_without_modifying_it(tmp_path):
    media = make_media(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ExtractionError, match="already exists"):
        extract_media(media, output, ffprobe_path=fake_ffprobe(tmp_path), ffmpeg_path=fake_ffmpeg(tmp_path))

    assert marker.read_text(encoding="utf-8") == "keep"


def test_rejects_media_without_extractable_streams(tmp_path):
    media = make_media(tmp_path)
    output = tmp_path / "out"

    with pytest.raises(ExtractionError, match="no supported"):
        extract_media(
            media, output,
            ffprobe_path=fake_ffprobe(tmp_path, []),
            ffmpeg_path=fake_ffmpeg(tmp_path),
        )

    assert not output.exists()


def test_cleans_new_output_directory_after_ffmpeg_failure(tmp_path):
    media = make_media(tmp_path)
    output = tmp_path / "failed-run"

    with pytest.raises(ExtractionError, match="ffmpeg exited"):
        extract_media(
            media, output,
            ffprobe_path=fake_ffprobe(tmp_path),
            ffmpeg_path=fake_ffmpeg(tmp_path, fail=True),
        )

    assert not output.exists()


@pytest.mark.parametrize("kwargs", [
    {"interval_seconds": 0},
    {"interval_seconds": float("nan")},
    {"max_frames": 0},
    {"max_duration_seconds": 0},
])
def test_rejects_invalid_extraction_limits(tmp_path, kwargs):
    with pytest.raises(ExtractionError):
        extract_media(make_media(tmp_path), tmp_path / "out", **kwargs)


def test_extraction_records_sha256_for_each_derived_file(tmp_path):
    media = make_media(tmp_path)
    output = tmp_path / "derived" / "hashes"
    result = extract_media(
        media, output,
        ffprobe_path=fake_ffprobe(tmp_path),
        ffmpeg_path=fake_ffmpeg(tmp_path),
        interval_seconds=2,
    )

    import hashlib

    for item in result["files"]:
        derived = output / item["path"]
        assert item["byte_size"] == derived.stat().st_size
        assert item["sha256"] == hashlib.sha256(derived.read_bytes()).hexdigest()


def test_extraction_rejects_symlinked_output_and_cleans_run_directory(tmp_path):
    media = make_media(tmp_path)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    ffmpeg = executable(tmp_path, "symlink_ffmpeg", """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv[1:]
if "-f" in args and args[args.index("-f") + 1] == "image2":
    target = pathlib.Path(args[-1].replace("%06d", "000001"))
    target.symlink_to(pathlib.Path(""" + repr(str(outside)) + """))
elif "-f" in args and args[args.index("-f") + 1] == "wav":
    pathlib.Path(args[-1]).write_bytes(b"fake-wav")
""")
    output = tmp_path / "derived" / "symlink-run"

    with pytest.raises(ExtractionError, match="symbolic|regular|inside"):
        extract_media(media, output, ffprobe_path=fake_ffprobe(tmp_path), ffmpeg_path=ffmpeg)

    assert outside.read_bytes() == b"outside"
    assert not output.exists()
