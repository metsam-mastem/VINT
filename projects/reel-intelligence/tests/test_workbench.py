from pathlib import Path

ROOT = Path(__file__).parents[1]
WEB = ROOT / "web"


def test_static_workbench_is_installable_and_offline_capable():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    manifest = (WEB / "manifest.webmanifest").read_text(encoding="utf-8")
    worker = (WEB / "sw.js").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert 'rel="manifest"' in html
    assert 'name="theme-color"' in html
    assert "serviceWorker" in app
    assert "sha256.js" in html
    assert "sha256.js" in worker
    assert '"display": "standalone"' in manifest
    assert "addAll" in worker
    assert "icon.svg" in manifest
    assert (WEB / "icon.svg").is_file()


def test_workbench_hashes_files_in_bounded_browser_chunks():
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert "new RISha256()" in app
    assert "4 * 1024 * 1024" in app
    assert "file.slice(" in app
    assert "file.arrayBuffer()" not in app
    assert "URL.createObjectURL" in app
    assert "fetch(" not in app
    assert "XMLHttpRequest" not in app


def test_workbench_exposes_current_branch_checks_and_manual_workflow():
    html = (WEB / "index.html").read_text(encoding="utf-8")

    assert "pull/1/checks" in html
    assert "actions/workflows/ri-workbench.yml" in html
    assert "GitHub Actions" in html


def test_operator_workflow_is_manual_and_read_only():
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "ri-workbench.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "permissions:" in workflow
    assert "pytest" in workflow
    assert "upload-artifact" in workflow
    assert "path: projects/reel-intelligence/web/" in workflow
    assert "node --test" in workflow


def test_pages_deployment_is_static_and_scoped_to_workbench():
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "ri-pages.yml").read_text(encoding="utf-8")

    assert "actions/upload-pages-artifact@v3" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "path: projects/reel-intelligence/web" in workflow
    assert "id-token: write" in workflow


def test_extraction_cli_is_registered_in_project_metadata():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'ri-extract = "reel_intelligence.extraction_cli:main"' in project


def test_ci_packages_the_static_workbench_artifact():
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "ri-ci.yml").read_text(encoding="utf-8")

    assert "package-workbench:" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "reel-intelligence-workbench" in workflow
    assert "path: projects/reel-intelligence/web/" in workflow
    assert "node --test" in workflow
