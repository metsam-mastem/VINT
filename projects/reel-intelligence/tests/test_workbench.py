from pathlib import Path

ROOT = Path(__file__).parents[1]
WEB = ROOT / "web"


def test_static_workbench_is_installable_and_offline_capable():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    manifest = (WEB / "manifest.webmanifest").read_text(encoding="utf-8")
    worker = (WEB / "sw.js").read_text(encoding="utf-8")

    assert 'rel="manifest"' in html
    assert 'name="theme-color"' in html
    assert "serviceWorker" in html
    assert '"display": "standalone"' in manifest
    assert "addAll" in worker


def test_workbench_keeps_file_processing_in_browser():
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert "crypto.subtle.digest" in app
    assert "file.arrayBuffer()" in app
    assert "URL.createObjectURL" in app
    assert "fetch(" not in app
    assert "XMLHttpRequest" not in app


def test_workbench_has_safe_github_actions_handoff():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert "RI Workbench Control" in html
    assert "actions/workflows/ri-workbench.yml" in html
    assert "actions/workflows/ri-workbench.yml" in html
    assert "GitHub Actions" in html


def test_operator_workflow_is_manual_and_read_only():
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "ri-workbench.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "permissions:" in workflow
    assert "pytest" in workflow
    assert "upload-artifact" in workflow
