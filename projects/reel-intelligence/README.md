# REEL INTELLIGENCE

Platform-independent, local-first multimodal intelligence workbench.

This repository path currently contains four executable engineering increments:
- **RI-001 — Canonical Contract Validator**
- **RI-002 — Safe Local File Intake**
- **RI-003 — FFprobe Media Metadata Inspection**
- **RI-004 — Local SQLite Asset Catalog**\n- **RI-005 — Bounded Temporal Extraction**

The implementation is dependency-light. Media probing extracts technical metadata; it does not decode or semantically understand media.

## Current capabilities

### RI-001 — Canonical records
- Strict validation for Asset, Analysis Manifest, Timeline Event, Evidence, and Claim records.
- Timezone-aware ISO-8601 timestamps and SHA-256 validation.
- Non-negative media offsets and valid time intervals.
- Evidence references required for supported/contradicted claims.
- Cross-record validation for assets, evidence, claims, and timeline-to-asset consistency.
- JSON CLI for one record or a linked JSON bundle.
- Persian/Unicode text preserved as UTF-8 JSON content.

### RI-002 — Local file intake
- MP4, MP3, WAV, JPEG, PNG, and PDF.
- Streaming SHA-256 hashing; no full-file buffering and no file copying.
- Extension plus file-signature verification; mismatches and unsupported types are rejected.
- Empty files, symbolic links, non-regular files, and paths outside an optional permitted root are rejected.
- Content-addressed Asset IDs are stable for identical file bytes.
- Absolute source paths are not stored in the returned Asset record.
- Detects changes to the file during inspection.
- Recursive or top-level directory intake with deterministic ordering, content deduplication, and fail-closed symlink handling.

### RI-003 — FFprobe metadata inspection
- Optional FFprobe integration for local audio/video files.
- Extracts container and stream metadata such as duration, size, bitrate, codec, dimensions, sample rate, and channels.
- Uses an argument-array subprocess call, no shell, a bounded timeout, and sanitized JSON output.
- FFprobe is an external optional executable; it is not installed by the Python package.
- Does not decode, transcode, extract frames, or perform semantic analysis.

### RI-004 — Local SQLite catalog
- Stores canonical Asset records and normalized probe metadata in a local SQLite database.
- Supports idempotent insertion, content-hash uniqueness, media-type filtering, pagination, and asset lookup.
- Uses a versioned schema and SQLite transactions; no server or external database is required.
- Does not store absolute source paths.

## Install

From this directory:

```bash
python -m pip install -e ".[dev]"
```

## Validate canonical JSON

One record:

```bash
ri-validate path/to/asset.json
```

Linked record bundle:

```bash
ri-validate path/to/bundle.json
```

Read from standard input:

```bash
cat bundle.json | ri-validate -
```

Exit codes: `0` valid; `2` invalid or unreadable input.

## Intake local files or directories

One file:

```bash
ri-intake path/to/sample.mp4
```

Restrict a single-file path to a root directory:

```bash
ri-intake media/sample.mp4 --root /path/to/workspace
```

Recursively intake supported files in a folder:

```bash
ri-intake /path/to/media
```

Scan only the top-level folder:

```bash
ri-intake /path/to/media --no-recursive
```

The intake command prints canonical Asset JSON. It does not copy, move, upload, decode, or modify source files.

## Probe media metadata

FFprobe must be installed separately and available on PATH:

```bash
ri-probe path/to/sample.mp4
```

Override the executable or timeout:

```bash
ri-probe path/to/sample.mp4 --ffprobe /usr/bin/ffprobe --timeout 15
```

The command returns a sanitized JSON object containing the Asset record and normalized FFprobe metadata. Absolute local paths and FFprobe tags are not included.

## Catalog assets locally

Initialize a catalog database:

```bash
ri-catalog init --db .reel-intelligence/catalog.sqlite3
```

Add a single file or recursively import a directory:

```bash
ri-catalog add path/to/sample.mp4 --db .reel-intelligence/catalog.sqlite3
ri-catalog add /path/to/media --db .reel-intelligence/catalog.sqlite3
```

Probe before saving an audio/video file (requires FFprobe):

```bash
ri-catalog add path/to/sample.mp4 --db .reel-intelligence/catalog.sqlite3 --probe
```

List or inspect records:

```bash
ri-catalog list --db .reel-intelligence/catalog.sqlite3 --media-type video
ri-catalog show asset-id --db .reel-intelligence/catalog.sqlite3\nri-extract video.mp4 --output ./derived/video-001 --interval 5 --max-frames 120
```

The database remains local. Add the catalog directory to local ignore rules; do not commit personal asset databases.

## Run tests

```bash
python -m pytest -q
```

GitHub Actions runs the suite on Python 3.10, 3.12, and 3.13 and verifies all five CLI entry points.

### RI-005 — Temporal extraction

- Optional FFmpeg integration for local MP4, MP3, and WAV media.
- Samples video frames as JPEG at a configurable interval, with a hard frame-count cap.
- Extracts the first audio stream as mono 16 kHz PCM WAV, with a maximum processing duration.
- Uses argument-array subprocess execution, no shell, bounded timeouts, and sanitized output manifests.
- Requires a new, non-existing output directory; on failure, only the directory created by the current extraction attempt is removed.
- Source media is never modified. The manifest uses relative output paths and includes frame timestamps.
- FFmpeg and FFprobe remain external optional executables.
- CLI: `ri-extract`.

Example:

```bash
ri-extract input.mp4 --output ./derived/clip-001 --interval 5 --max-frames 120
```

## Browser Workbench (RI-WEB)

A dependency-free, installable static web app is available in `web/`.

### Open it

- Open `web/index.html` from a local static HTTP server, or publish the folder with GitHub Pages.
- For reliable PWA installation and offline caching, use an HTTPS origin (GitHub Pages provides HTTPS).
- On first load, the service worker caches the app shell. Subsequent visits can open the workbench offline.
- On Android, use the browser menu's **Add to Home screen** option after opening the HTTPS deployment.

### Local Engine

1. Switch **LOCAL ENGINE** on.
2. Select or drop MP4, MP3, WAV, JPEG, PNG, or PDF files.
3. The browser checks the extension and file signature, computes SHA-256, and reads browser-exposed media metadata (duration/dimensions where available).
4. Export the result as a JSON report.

The browser app does not upload media, call a remote API, or persist selected file bytes. Hashing currently uses the browser Web Crypto API and reads the selected file into memory; very large media files may exceed mobile-browser memory limits. Use smaller files on low-memory devices.

The browser workbench is a local intake/inspection surface, not the full semantic engine. It does not yet perform ASR, OCR, scene understanding, frame extraction, or evidence/claim generation. Its browser-generated Asset record uses `source.kind=browser_local_file`; it is a browser report and is not silently inserted into the Python catalog.

### GitHub Actions control

The manual operator workflow is `.github/workflows/ri-workbench.yml`.

- Open [RI Workbench Control](https://github.com/metsam-mastem/VINT/actions/workflows/ri-workbench.yml).
- Select **Run workflow** and choose `self_check` or `validate_project`.
- `self_check` runs tests, compilation, CLI checks, and verifies the web app files.
- `validate_project` performs the same checks and packages the static web app as a downloadable workflow artifact (retained for 14 days).

The workflow uses a temporary GitHub-hosted runner and read-only repository permissions. It does not accept or upload personal media. No GitHub token is embedded in the static app. The dashboard's Actions link intentionally hands control to GitHub's authenticated interface rather than storing credentials in the browser.

A dedicated publisher workflow is provided at `.github/workflows/ri-pages.yml`. After merging to the default branch, enable **Settings → Pages → Build and deployment → GitHub Actions**. The workflow publishes only `projects/reel-intelligence/web/` on relevant changes to `main`; it can also be started manually with `workflow_dispatch`. The static site itself requires no always-on server or database. The public Pages URL becomes available in the workflow deployment result.

## Not implemented yet

- ZIP/archive inspection and safe extraction.
- Full media decoding/transcoding pipelines beyond RI-005 sampled frame and normalized-audio extraction.
- Speech recognition, OCR, scene detection, or multimodal inference.
- Search/indexing, UI, API, cloud sync, or platform adapters.
- Android/Windows packaging and device-specific benchmarks.

These are future increments and must not be inferred from RI-001 through RI-004.

## Local-first and privacy

The intake layer reads only paths supplied by the operator. It does not transmit data over the network. Generated Asset records include the basename, not the absolute local path. FFprobe output is normalized and omits arbitrary metadata tags. Do not commit source media, transcripts, personal data, credentials, or local caches to this public repository.

## Current status

- RI-001 canonical validator: implemented; verified in CI.
- RI-002 local file and directory intake: implemented; supported formats and path-safety checks pass.
- RI-003 FFprobe metadata probe: implemented; fake-executable integration tests pass.
- RI-004 SQLite asset catalog: implemented; persistence, deduplication, filtering, and retrieval tests pass.
- CI matrix: PASS on Python 3.10, 3.12, and 3.13; 57 tests pass per version (171 test executions).
- Device-level and native FFprobe integration benchmarks: NOT RUN.
- Semantic media analysis pipeline: not implemented.
- Main branch: unchanged by this feature work.
