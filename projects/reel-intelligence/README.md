# REEL INTELLIGENCE

Platform-independent, local-first multimodal intelligence workbench.

## Implemented increments

- **RI-001 — Canonical Contract Validator**
- **RI-002 — Safe Local File Intake**
- **RI-003 — FFprobe Metadata Inspection**
- **RI-004 — Local SQLite Asset Catalog**
- **RI-005 — Bounded Temporal Extraction**
- **RI-WEB — Offline Browser Workbench**
- **GitHub Actions — CI, manual operator, artifact packaging, and Pages publisher**

## Install

From this directory:

```bash
python -m pip install -e ".[dev]"
```

## RI-001 — Canonical contracts

Strict validation for Asset, Analysis Manifest, Timeline Event, Evidence, and Claim records, including timezone-aware timestamps, SHA-256 validation, non-negative media offsets, interval ordering, and cross-record references.

```bash
ri-validate path/to/asset.json
ri-validate path/to/bundle.json
cat bundle.json | ri-validate -
```

Exit codes: `0` valid; `2` invalid or unreadable input.

## RI-002 — Local file intake

Supports MP4, MP3, WAV, JPEG, PNG, and PDF. Uses streaming SHA-256 hashing, extension/signature checks, content-addressed IDs, safe path handling, deterministic directory intake, and duplicate elimination. It does not copy, move, upload, decode, or modify source files.

```bash
ri-intake path/to/sample.mp4
ri-intake /path/to/media
ri-intake /path/to/media --no-recursive
```

## RI-003 — FFprobe metadata

Optional FFprobe integration extracts container and stream metadata such as duration, size, bitrate, codec, dimensions, sample rate, and channels. FFprobe must be installed separately. Calls use argument arrays, no shell, bounded timeouts, and sanitized output. This stage does not decode or semantically understand media.

```bash
ri-probe path/to/sample.mp4
ri-probe path/to/sample.mp4 --ffprobe /usr/bin/ffprobe --timeout 15
```

## RI-004 — SQLite catalog

Local SQLite persistence for canonical Asset records and normalized probe metadata. Supports idempotent insertion, hash uniqueness, media-type filtering, pagination, lookup, versioned schema, and transactions.

```bash
ri-catalog init --db .reel-intelligence/catalog.sqlite3
ri-catalog add path/to/sample.mp4 --db .reel-intelligence/catalog.sqlite3
ri-catalog add path/to/sample.mp4 --db .reel-intelligence/catalog.sqlite3 --probe
ri-catalog list --db .reel-intelligence/catalog.sqlite3 --media-type video
ri-catalog show asset-id --db .reel-intelligence/catalog.sqlite3
```

Keep local catalog databases out of the public repository.

## RI-005 — Bounded temporal extraction

Optional FFmpeg integration for local MP4, MP3, and WAV files:

- Samples video frames as JPEG at a configurable interval, with a hard frame-count cap.
- Extracts the first audio stream as mono 16 kHz PCM WAV, with a maximum processing duration.
- Uses argument-array subprocess execution, no shell, and bounded timeouts.
- Requires a new output directory. On failure, only the destination created by that attempt is removed.
- Source media is never modified. The returned manifest contains relative paths and approximate frame timestamps.
- FFmpeg and FFprobe are external optional executables.

```bash
ri-extract input.mp4 --output ./derived/clip-001 --interval 5 --max-frames 120
```

Native FFmpeg integration with real media remains NOT RUN; automated tests use fake executables to verify command behavior and failure handling.

## RI-WEB — Offline browser workbench

A dependency-free, responsive RTL static web app is available in `web/`.

### Open and install

- Open `web/index.html` from a local static HTTP server, or publish the folder with GitHub Pages.
- For PWA installation and service-worker caching, use an HTTPS origin (GitHub Pages provides HTTPS).
- After the first successful load, the service worker caches the app shell for later offline use.
- On Android, open the HTTPS deployment in the browser and use **Add to Home screen**.

### Local Engine

1. Switch **LOCAL ENGINE** on.
2. Select or drop MP4, MP3, WAV, JPEG, PNG, or PDF files.
3. The browser checks extension and file signature, computes SHA-256, and reads browser-exposed image/audio/video metadata.
4. Export a JSON report.

The file inspection flow does not upload media, call a remote API, or persist selected file bytes. Browser hashing currently reads the selected file into memory; very large media may exceed mobile-browser memory. Use smaller files on low-memory devices.

The browser workbench is a local intake/inspection surface, not the complete semantic engine. It does not perform ASR, OCR, scene understanding, or evidence/claim generation. Browser-generated Asset records use `source.kind=browser_local_file`; they are reports and are not silently inserted into the Python SQLite catalog.

## GitHub Actions operator

The manual operator workflow is `.github/workflows/ri-workbench.yml`.

- `self_check`: installs the project, compiles Python, runs tests, verifies CLIs, and checks static web files.
- `validate_project`: performs the same checks and packages the static workbench as a downloadable ZIP artifact (14-day retention).

The dashboard links to the current PR Checks page for the feature branch. Once a check run completes, a repository writer can use GitHub's **Re-run jobs** control. The manual `workflow_dispatch` operator becomes available after its workflow definition is present on the default branch; GitHub requires that for manually dispatched workflows.

No token is embedded in the web app. The workflow uses read-only repository permissions and does not receive personal media files. Jobs run on temporary GitHub-hosted runners, which are decommissioned after completion.

The CI workflow also packages the static workbench and uploads it as an artifact after the Python matrix passes.

## GitHub Pages deployment

A dedicated publisher is provided at `.github/workflows/ri-pages.yml`. After merging to the default branch:

1. Open repository **Settings → Pages**.
2. Set **Build and deployment → Source** to **GitHub Actions**.
3. Run the Pages workflow manually or push a relevant change to `main`.

Only `projects/reel-intelligence/web/` is published. No always-on server, API service, or database is required. The deployment URL is reported by the workflow.

## Run tests

```bash
python -m pytest -q
```

GitHub Actions tests Python 3.10, 3.12, and 3.13, compiles the package, and checks all five CLI entry points.

## Current status and limitations

- RI-001 through RI-005: implemented; latest CI verification for the current head is pending.
- RI-WEB: static PWA shell and local file-inspection surface implemented; browser runtime/E2E verification NOT RUN.
- ZIP/archive inspection and safe extraction: not implemented.
- ASR, OCR, scene detection, multimodal inference, evidence/claim generation, semantic timeline, and search/index: not implemented.
- Native FFmpeg/FFprobe integration with real media: NOT RUN.
- Android/Windows packaging and Redmi/Lenovo device benchmarks: NOT RUN.
- GitHub Pages publishing: workflow is present; deployment requires Pages configuration and the workflow on the default branch.
- GitHub Actions remote operator: workflow is present on this feature branch; manual dispatch requires it to be merged to the default branch.

Do not infer full semantic understanding or product completion from the implemented foundations.

## Local-first and privacy

The Python intake reads only paths supplied by the operator and does not transmit data. Asset records avoid absolute source paths. FFprobe output is normalized and omits arbitrary metadata tags. Do not commit source media, transcripts, personal data, credentials, or local caches to this public repository.
