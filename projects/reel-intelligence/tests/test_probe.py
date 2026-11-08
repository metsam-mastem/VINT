import json
import os
import sys

import pytest

from reel_intelligence.probe import ProbeError, probe_media


def media_file(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00")
    return path


def executable(tmp_path, source):
    path = tmp_path / "fake_ffprobe"
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def test_probe_returns_sanitized_format_and_stream_metadata(tmp_path):
    media = media_file(tmp_path)
    fake = executable(tmp_path, """#!/usr/bin/env python3
import json
print(json.dumps({
  "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.5", "size": "4096", "bit_rate": "8000", "tags": {"title": "private"}},
  "streams": [
    {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
    {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}
  ]
}))
""")

    result = probe_media(media, ffprobe_path=fake)

    assert result["asset"]["filename"] == "clip.mp4"
    assert result["probe"]["format"]["duration_seconds"] == 12.5
    assert result["probe"]["format"]["size_bytes"] == 4096
    assert result["probe"]["streams"][0]["codec_name"] == "h264"
    assert "tags" not in result["probe"]["format"]


def test_probe_rejects_missing_ffprobe(tmp_path):
    with pytest.raises(ProbeError, match="not found"):
        probe_media(media_file(tmp_path), ffprobe_path="ri-ffprobe-does-not-exist")


def test_probe_enforces_timeout(tmp_path):
    media = media_file(tmp_path)
    fake = executable(tmp_path, """#!/usr/bin/env python3
import time
time.sleep(2)
""")
    with pytest.raises(ProbeError, match="timed out"):
        probe_media(media, ffprobe_path=fake, timeout_seconds=0.05)


def test_probe_reports_ffprobe_failure_without_shell_execution(tmp_path):
    media = media_file(tmp_path)
    fake = executable(tmp_path, """#!/usr/bin/env python3
import sys
sys.stderr.write("invalid media stream")
sys.exit(7)
""")
    with pytest.raises(ProbeError, match="invalid media stream"):
        probe_media(media, ffprobe_path=fake)


def test_probe_rejects_invalid_json_output(tmp_path):
    media = media_file(tmp_path)
    fake = executable(tmp_path, """#!/usr/bin/env python3
print("not json")
""")
    with pytest.raises(ProbeError, match="valid JSON"):
        probe_media(media, ffprobe_path=fake)


def test_probe_rejects_invalid_timeout(tmp_path):
    with pytest.raises(ProbeError, match="timeout"):
        probe_media(media_file(tmp_path), ffprobe_path="ffprobe", timeout_seconds=0)
