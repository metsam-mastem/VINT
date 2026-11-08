# REEL INTELLIGENCE

Platform-independent, local-first multimodal intelligence workbench.

This repository path currently contains two executable engineering increments:
- **RI-001 — Canonical Contract Validator**
- **RI-002 — Safe Local File Intake**

The implementation is deliberately dependency-light. Media decoding and AI analysis are not implied by file intake.

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
- Detects changes to the file during inspection.\n- Recursive or top-level directory intake with deterministic ordering, content deduplication, and fail-closed symlink handling.

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

## Intake a local file

```bash
ri-intake path/to/sample.mp4
```

Restrict the accepted path to a root directory:

```bash
ri-intake media/sample.mp4 --root /path/to/workspace
```

The command prints one canonical Asset JSON record to stdout. It does not copy, move, upload, decode, or modify the source file.

## Run tests

```bash
python -m pytest -q
```

GitHub Actions runs the suite on Python 3.10, 3.12, and 3.13 and checks both CLI entry points.

## Not implemented yet

- ZIP/archive inspection and safe extraction.
- Full media decoding, transcoding, and frame/audio extraction.
- Speech recognition, OCR, scene detection, or multimodal inference.
- Database persistence, search/indexing, UI, API, cloud sync, or platform adapters.
- Android/Windows packaging and device-specific benchmarks.

These are future increments and must not be inferred from RI-001/RI-002.

## Local-first and privacy

The intake layer reads only the path supplied by the operator. It does not transmit data over the network. The generated record includes the basename, not the absolute local path. Do not commit source media, transcripts, personal data, credentials, or local caches to this public repository.

## Current status

- RI-001 validator: implementation and CI verification in progress on the feature branch.
- RI-002 local file and directory intake: implemented; CI verification pending for latest commit.\n- RI-003 FFprobe metadata probe: implemented; CI verification pending for latest commit.
- Media analysis pipeline: not implemented.
- Main branch: unchanged by this feature work.
