import json
import os
import stat

import pytest

from reel_intelligence.analysis import AnalysisError, analyze_media


def executable(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def make_pdf(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.7\n%fixture")
    return path


def make_png(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    return path


def test_scanned_pdf_uses_bounded_poppler_render_and_tesseract_fallback(tmp_path):
    pdf = make_pdf(tmp_path)
    pdftotext = executable(tmp_path, "pdftotext-empty", """#!/usr/bin/env python3
print("\\f")
""")
    pdftoppm = executable(tmp_path, "pdftoppm", """#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(sys.argv[-1] + "-1.png").write_bytes(b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR")
""")
    tesseract = executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext")
print("5\\t1\\t1\\t1\\t1\\t1\\t10\\t20\\t100\\t25\\t96\\tScanned")
""")
    output = tmp_path / "scanned-pdf-run"

    report = analyze_media(
        pdf, output,
        pdftotext_path=pdftotext,
        pdftoppm_path=pdftoppm,
        tesseract_path=tesseract,
    )

    evidence = [item for item in report["records"] if item["record_type"] == "evidence"]
    assert report["manifest"]["status"] == "completed"
    assert any(item["observation"] == "Scanned" and item["modality"] == "document" for item in evidence)
    assert any(item["kind"] == "pdf_page" and item["sha256"] for item in report["artifacts"])
    assert (output / "pdf-pages" / "page-1.png").is_file()


def test_pdf_selectable_text_extraction_is_independent_of_ocr_toggle(tmp_path):
    from_pdf = make_pdf(tmp_path)
    pdftotext = executable(tmp_path, "pdftotext", """#!/usr/bin/env python3
print("متن انتخاب‌پذیر PDF\\f")
""")
    report = analyze_media(
        from_pdf,
        tmp_path / "text-only-pdf",
        pdftotext_path=pdftotext,
        enable_ocr=False,
    )

    evidence = [item for item in report["records"] if item["record_type"] == "evidence"]
    assert any(item["observation"] == "متن انتخاب‌پذیر PDF" for item in evidence)
    assert report["processor_results"][0]["processor"] == "pdftotext"


def test_analysis_artifacts_include_hashes_and_report_is_private(tmp_path):
    image = make_png(tmp_path)
    tesseract = executable(tmp_path, "tesseract", """#!/usr/bin/env python3
print("level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext")
print("5\\t1\\t1\\t1\\t1\\t1\\t10\\t20\\t100\\t25\\t96\\tPrivate")
""")
    output = tmp_path / "private-run"
    report = analyze_media(image, output, tesseract_path=tesseract)

    assert report["asset"]["sha256"]
    assert (output / "run_manifest.json").is_file()
    assert str(tmp_path) not in (output / "analysis.json").read_text(encoding="utf-8")
    assert stat.S_IMODE((output / "analysis.json").stat().st_mode) & 0o077 == 0
    assert json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))["asset_sha256"] == report["asset"]["sha256"]


def test_analysis_detects_source_mutation_during_ocr_and_discards_run(tmp_path):
    image = make_png(tmp_path)
    tesseract = executable(tmp_path, "mutating-tesseract", """#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(sys.argv[1]).write_bytes(b"changed-source")
print("level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext")
print("5\\t1\\t1\\t1\\t1\\t1\\t10\\t20\\t100\\t25\\t96\\tMutated")
""")
    output = tmp_path / "mutation-run"

    with pytest.raises(AnalysisError, match="changed during processing"):
        analyze_media(image, output, tesseract_path=tesseract)

    assert not output.exists()
