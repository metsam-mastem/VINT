# REEL INTELLIGENCE

Platform-independent, local-first multimodal intelligence workbench.

This repository path currently contains three executable engineering increments:
- **RI-001 — Canonical Contract Validator**
- **RI-002 — Safe Local File Intake**
- **RI-003 — FFprobe Media Metadata Inspection**

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

## Run tests

```bash
python -m pytest -q
```

GitHub Actions runs the suite on Python 3.10, 3.12, and 3.13 and verifies all three CLI entry points.

## Not implemented yet

- ZIP/archive inspection and safe extraction.
- Full media decoding, transcoding, and frame/audio extraction.
- Speech recognition, OCR, scene detection, or multimodal inference.
- Database persistence, search/indexing, UI, API, cloud sync, or platform adapters.
- Android/Windows packaging and device-specific benchmarks.

These are future increments and must not be inferred from RI-001 through RI-003.

## Local-first and privacy

The intake layer reads only paths supplied by the operator. It does not transmit data over the network. Generated Asset records include the basename, not the absolute local path. FFprobe output is normalized and omits arbitrary metadata tags. Do not commit source media, transcripts, personal data, credentials, or local caches to this public repository.

## Current status

- RI-001 canonical validator: implemented; 50 tests pass in the current CI matrix.
- RI-002 local file and directory intake: implemented; supported formats and path-safety checks pass.
- RI-003 FFprobe metadata probe: implemented; fake-executable integration tests pass.
- CI matrix: PASS on Python 3.10, 3.12, and 3.13 for the current code commit.
- Device-level and native FFprobe integration benchmarks: NOT RUN.
- Semantic media analysis pipeline: not implemented.
- Main branch: unchanged by this feature work.
