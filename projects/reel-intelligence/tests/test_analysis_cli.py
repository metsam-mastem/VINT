import json

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
