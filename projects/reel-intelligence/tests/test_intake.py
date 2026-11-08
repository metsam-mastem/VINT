import pytest

from reel_intelligence.contracts import validate_record
from reel_intelligence.intake import IntakeError, inspect_file


SAMPLES = [
    (".mp4", b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00", "video"),
    (".mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00audio", "audio"),
    (".wav", b"RIFF\x24\x00\x00\x00WAVEfmt ", "audio"),
    (".jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", "image"),
    (".png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image"),
    (".pdf", b"%PDF-1.7\n%test", "document"),
]


@pytest.mark.parametrize("extension,payload,media_type", SAMPLES)
def test_intakes_supported_local_formats(tmp_path, extension, payload, media_type):
    source = tmp_path / f"sample{extension}"
    source.write_bytes(payload)

    asset = inspect_file(source, root=tmp_path)

    assert asset["media_type"] == media_type
    assert asset["filename"] == source.name
    assert asset["byte_size"] == len(payload)
    assert asset["source"] == {"kind": "local_file"}
    assert asset["sha256"]
    assert validate_record(asset) == asset


def test_asset_id_is_content_addressed_and_path_is_not_leaked(tmp_path):
    first = tmp_path / "first.mp3"
    second_dir = tmp_path / "nested"
    second_dir.mkdir()
    second = second_dir / "renamed.mp3"
    payload = b"ID3\x04\x00\x00\x00\x00\x00\x00same"
    first.write_bytes(payload)
    second.write_bytes(payload)

    a = inspect_file(first, root=tmp_path)
    b = inspect_file(second, root=tmp_path)

    assert a["asset_id"] == b["asset_id"]
    assert str(tmp_path) not in str(a["source"])


def test_rejects_empty_file(tmp_path):
    source = tmp_path / "empty.png"
    source.write_bytes(b"")
    with pytest.raises(IntakeError, match="empty"):
        inspect_file(source, root=tmp_path)


def test_rejects_extension_signature_mismatch(tmp_path):
    source = tmp_path / "fake.png"
    source.write_bytes(b"%PDF-1.7\n")
    with pytest.raises(IntakeError, match="mismatch"):
        inspect_file(source, root=tmp_path)


def test_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "archive.zip"
    source.write_bytes(b"PK\x03\x04")
    with pytest.raises(IntakeError, match="unsupported"):
        inspect_file(source, root=tmp_path)


def test_rejects_symlink_input(tmp_path):
    target = tmp_path / "target.png"
    target.write_bytes(SAMPLES[4][1])
    link = tmp_path / "linked.png"
    link.symlink_to(target)
    with pytest.raises(IntakeError, match="symbolic link"):
        inspect_file(link, root=tmp_path)


def test_enforces_root_boundary(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(SAMPLES[4][1])
    with pytest.raises(IntakeError, match="outside"):
        inspect_file(outside, root=root)
