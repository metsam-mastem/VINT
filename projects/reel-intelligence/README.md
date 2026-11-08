# REEL INTELLIGENCE

Platform-independent, local-first multimodal intelligence workbench.

This repository path contains the first executable engineering slice: **RI-001, the canonical contract validator**. It is deliberately dependency-light and does not yet decode or analyze media.

## Current scope

- Strict validation for Asset, Analysis Manifest, Timeline Event, Evidence, and Claim records.
- Timezone-aware ISO-8601 timestamps.
- SHA-256 format validation.
- Non-negative media offsets and valid time intervals.
- Required evidence references for supported/contradicted claims.
- Cross-record reference checks for assets and evidence.
- JSON CLI for one record or a linked JSON bundle.
- Persian/Unicode text is preserved as ordinary UTF-8 JSON content.

## Not implemented in RI-001

- File ingestion, copying, hashing of source media, or malware scanning.
- FFmpeg/ffprobe integration or full media decoding.
- Speech recognition, OCR, scene detection, or multimodal inference.
- Database persistence, vector search, UI, API, cloud sync, or platform adapters.

These are separate increments and must not be inferred from the presence of this validator.

## Install

From this directory:

```bash
python -m pip install -e ".[dev]"
```

## Validate one record

```bash
ri-validate path/to/asset.json
```

## Validate a linked bundle

Pass a JSON array containing assets and their dependent records:

```bash
ri-validate path/to/bundle.json
```

Read JSON from standard input:

```bash
cat bundle.json | ri-validate -
```

Exit codes:
- `0`: valid input
- `2`: invalid input or unreadable/invalid JSON

## Run tests

```bash
python -m pytest
```

Tests are committed before the implementation as the intended TDD acceptance contract. **Execution status in this delivery: NOT RUN**; run the command above in a Python environment before marking RI-001 as PASS.

## Record envelope

Every record includes:

- `schema_version`: currently `1.0`
- `record_type`: one of `asset`, `analysis_manifest`, `timeline_event`, `evidence`, `claim`

Unknown fields are rejected intentionally so spelling mistakes and accidental schema drift do not silently pass.

## Local-first and privacy

The validator performs no network calls. It reads only the JSON input path supplied by the operator (or stdin). It does not open media files. Do not commit source media, transcripts, personal data, credentials, or local caches to this public repository.

## Project status

- RI-001 implementation source: committed to feature branch.
- Acceptance tests: committed to feature branch.
- Local test execution: NOT RUN in this delivery environment.
- CI execution: NOT RUN.
- Media import and analysis pipeline: NOT IMPLEMENTED.
