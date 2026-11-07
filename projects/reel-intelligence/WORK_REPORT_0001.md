# REEL INTELLIGENCE
## Platform-Independent Multimodal Intelligence Workbench

**Document:** Work Report & Research-Driven Architecture Proposal  
**Document ID:** RI-WR-0001  
**Version:** 0.2.0  
**Date:** 2026-11-07  
**Repository:** https://github.com/metsam-mastem/VINT  
**Project path:** projects/reel-intelligence/  
**Publication status:** Initial research and architecture report

---

## 1. Executive decision

Reel Intelligence is **not an Instagram analyzer**. It is a platform-independent workbench for importing, inspecting, understanding, verifying, indexing, and reverse-engineering multimedia and companion materials.

In the initial case, the Instagram URL did not provide a reliable acquisition path. The user-uploaded MP4 was the usable primary input and the source of the initial analysis. The product therefore treats user-supplied files and folders as first-class inputs; platform URLs and connectors are optional adapters.

**Recommended direction:** local-first modular monolith, reproducible pipeline, provider adapters, evidence-linked multimodal timeline. SaaS, multi-agent orchestration, distributed infrastructure, and enterprise deployment are deferred until validated by actual usage and benchmarks.

VINT remains **Public**. Public source code does not imply public storage of user media, private transcripts, credentials, model caches, or sensitive artifacts.

## 2. Problem, scope, and non-goals

The system should connect what was said, shown, written, and changed in a media item, preserve timestamps and provenance, and support evidence-backed analysis and technical reverse engineering.

### In scope
- Video, audio, images, subtitles, text, and selected document formats.
- Single and batch file import, folders, drag-and-drop, and later direct-file URLs, APIs, and connectors.
- Metadata extraction, speech transcription, scene detection, selective frame extraction, OCR, document parsing, and optional visual interpretation.
- Timestamp-aligned evidence, claim tracking, source references, human review, search, and export.
- Educational, technical, research, and general media analysis across platforms.

### Non-goals for the first release
- Dependence on Instagram, TikTok, YouTube, or any single platform.
- Unrestricted scraping or bypassing platform access controls.
- Replacing a professional video editor or full digital asset management suite.
- Training a foundation model.
- Free-running multi-agent systems.
- Facial identity recognition, emotion diagnosis, personality inference, or biometric profiling.
- SaaS billing, multi-tenancy, Kubernetes, and distributed microservices before a demonstrated need.

## 3. Universal import strategy

An import adapter should normalize its input into the same asset record regardless of where the content came from.

| Priority | Import method | Decision |
|---|---|---|
| P0 | Single file upload / drag-and-drop | First milestone |
| P0 | Multiple-file selection and folder batch | First milestone; bounded by size and concurrency |
| P1 | Local watched folder | After the core pipeline |
| P1 | Direct HTTP(S) file URL | Add with strict size, timeout, MIME, redirect, and host-safety checks |
| P2 | CLI import | Low-cost repeatable batch interface; can be introduced early |
| P2 | API / webhook and cloud-drive connectors | Optional adapters when a real use case exists |
| P3 | Platform page URLs | Permission-aware optional adapters; never a core dependency |

### Format support policy

| Family | Initial candidates | Later candidates |
|---|---|---|
| Video | MP4, MOV, MKV, WebM | AVI, M4V, additional containers/codecs after tests |
| Audio | MP3, WAV, M4A | AAC, FLAC, OGG, OPUS |
| Images | JPG/JPEG, PNG | WEBP, TIFF, HEIC |
| Captions/text | SRT, VTT, TXT, MD, JSON | XML and other structured formats |
| Documents | PDF | DOCX, PPTX, HTML, EPUB |
| Batch packages | ZIP with safe extraction limits | Other archives only if justified |

These are candidate formats, not a claim that every codec/parser is already supported. File extension alone does not prove decodability; use content sniffing and media probing. Add a format to the supported list only after repeatable tests.

### Parser strategy
- FFmpeg/ffprobe for media probing, decoding, audio extraction, frame extraction, and transcoding.
- Lightweight image handling for normalization and thumbnails.
- A lightweight PDF/text parser for the first document support.
- Evaluate Apache Tika and Unstructured as alternative document adapters, not simultaneous mandatory dependencies. Compare extraction quality, memory, cold start, and target-device performance.
- Reject or safely isolate malformed and potentially hostile files. Never execute embedded content or macros.

## 4. Proposed architecture

Use a **modular monolith** for the first working product.

```text
Input adapters
  ├─ local file / folder
  ├─ direct file URL (later)
  ├─ API / cloud connector (later)
  └─ platform adapters (optional)
        ↓
Intake + validation
        ↓
Asset registry + immutable source reference
        ↓
Low-cost inspection and normalization
        ↓
Modality processors
  ├─ audio / speech
  ├─ scene / frame
  ├─ OCR / document layout
  └─ image / visual analysis
        ↓
Unified timestamped evidence timeline
        ↓
Claim ledger + verification + human review
        ↓
Search / analysis / report / export
```

### Canonical asset record
Each import should create a manifest with:
- `asset_id`, original filename, detected MIME/container/codec, and source kind.
- Source reference where available and permitted.
- File size, duration, dimensions, sample rate, and stream metadata where applicable.
- SHA-256 content hash and import timestamp.
- Processing profile, tool/model versions, status, and structured errors.

Original media remains immutable. Derived artifacts are separate and reproducible.

### Canonical evidence event
Each timeline event should support:
- `event_id`, `asset_id`, `start_ms`, `end_ms` (or page/region for documents and still images).
- Modality: speech, OCR, scene, image, audio event, document block, or model interpretation.
- Extracted content and artifact pointer.
- Producer tool/model and version; confidence/uncertainty where meaningful.
- Evidence state: observed, inferred, human-reviewed, verified, disputed, or unresolved.
- Optional bounding box, page number, speaker/track, or entity reference.

Raw observations must never be conflated with model interpretations.

### Initial output format

Prefer a versioned folder of JSON/Markdown artifacts over a database-heavy stack:

```text
workspace/<project>/<asset_id>/
  manifest.json
  metadata.json
  transcript.json
  scenes.json
  frames/          # selected frames only
  ocr.json
  timeline.json
  claims.json
  analysis.json
  report.md
```

Original media stays in local/private storage and is not committed to Git. Use SQLite/FTS only when local multi-asset search is needed. Add vector or graph databases only if retrieval benchmarks show ordinary indexed text and metadata are insufficient.

## 5. Efficient analysis profiles

Expose three understandable profiles rather than a large collection of switches:

1. **Quick Scan:** metadata, hash, audio extraction, speech transcript, inexpensive scene-change detection, representative frames, concise index.
2. **Deep Review:** denser scene/frame inspection, OCR on selected frames, timestamp alignment, optional visual interpretation, claim/evidence review, and source research.
3. **Question-Targeted:** use the user's question plus low-cost transcript/scene signals to select only relevant windows for deeper analysis.

A Quick Scan should be promotable to Deep Review without re-importing or repeating unchanged extraction work.

## 6. Cost-aware keyframe selection

Do not send every frame to an expensive vision model.

1. Probe metadata and detect exact duplicates by content hash.
2. Run low-cost temporal sampling and scene-boundary detection.
3. Find candidate changes using scene transitions, motion, speech turns/audio activity, and OCR-text changes.
4. Score candidates for novelty, query relevance, and uncertainty.
5. Select under a visible compute/token budget.
6. Send only selected frames to expensive visual models.
7. Record why each frame was selected and which regions remain unsampled.

**Research lead — FOCUS (ICLR 2026):** query-relevant keyframe selection can be framed as budgeted exploration/exploitation. The paper reports strong results with fewer than 2% of frames in its evaluated settings. Its full environment and dependencies are not appropriate for the constrained first milestone. Implement a lightweight CPU baseline behind a replaceable `FrameSelector` interface, then benchmark FOCUS as an optional advanced strategy. Do not assume the paper's speedup transfers to our videos or hardware.

## 7. Differentiating product ideas

These are proposals for experiments, not implemented features.

1. **Evidence-linked timeline:** one synchronized view of speech, OCR, scenes, audio events, visual observations, and document references.
2. **Cross-modal discrepancy detector:** flag possible inconsistencies between narration, visible text, and imagery for human review; do not issue an unsupported factual verdict.
3. **Evidence ledger:** every important claim points to a timestamp, frame, transcript segment, document page, or external source.
4. **Analysis receipt:** input hash, tool/model versions, settings, duration, resource use, errors, and output hashes for reproducibility.
5. **Companion-material analysis:** ingest video alongside PDFs, slides, source files, screenshots, and captions into one case folder.
6. **Technical reverse-engineering mode:** group screen/UI/code changes into steps, identify visible commands and named tools, align speech with on-screen actions, and export a procedure draft.
7. **Human review at uncertainty boundaries:** ask for review when evidence is weak, modalities disagree, or a claim affects a downstream decision.
8. **Process once, reuse many times:** separate extraction from interpretation so a new question/report does not rerun the expensive media pipeline.
9. **Evidence coverage metric:** measure supported-claim coverage separately from unsupported-claim rate.
10. **Uncertainty-aware abstention:** allow “insufficient evidence” rather than forcing a confident answer.

## 8. Nature Portfolio research and engineering implications

### 8.1 Visual cognition in multimodal LLMs
Schulze Buschoff et al., *Nature Machine Intelligence* (2025), evaluated visual models on intuitive physics, causal reasoning, and intuitive psychology, identifying capability gaps relative to humans.

**Implication:** distinguish observed pixels/text/audio from inferred interpretation. Do not infer intent, emotion, causality, or hidden physical events from a single frame without supporting evidence.

https://www.nature.com/articles/s42256-024-00963-y

### 8.2 RVTBench: semantic, spatial, and temporal video reasoning
Shen et al., *Scientific Data* (2026), describe a benchmark with 3,896 queries over 200 video sequences, covering segmentation, grounding, VQA, and summary; semantic, spatial, and temporal reasoning; and four difficulty levels. The work uses structured digital-twin representations as an intermediary.

**Implication:** test more than summarization: temporal order, object/location grounding, state changes, segment retrieval, and multi-step questions. The article, code, and dataset have separate licensing/provenance considerations.

https://www.nature.com/articles/s41597-026-07670-w  
Code: https://github.com/yiqings/rvt  
Dataset: https://zenodo.org/records/19697191

### 8.3 Data leakage and evaluation integrity
Bernett et al., *Nature Methods* (2024), discuss hidden relationships between training and test examples that can inflate reported performance. Joeres et al., *Nature Communications* (2025), introduce DataSAIL for leakage-reduced splitting in their domain.

**Implication:** keep source groups, creators/sessions, and near-duplicate families together during benchmark splitting. A cropped or lightly edited copy of a test video must not leak into training.

https://www.nature.com/articles/s41592-024-02362-y  
https://www.nature.com/articles/s41467-025-58606-8

### 8.4 OCR must preserve document structure
Li et al., *Scientific Reports* (2025), describe layout-aware document processing that distinguishes titles, paragraphs, tables, and images before recognition and structured output.

**Implication:** OCR should preserve page, bounding box, block type, reading order, and recognized text—not only a concatenated string.

https://www.nature.com/articles/s41598-025-07439-y

### 8.5 Reproducibility and reusable research artifacts
A *Nature Machine Intelligence* editorial (2026) calls for attention to reproducibility, transparency, and consistent descriptions of digital artifacts.

**Implication:** every analysis report should carry an analysis receipt and versioned schema. A result without source hash, configuration, and tool/model provenance is not fully reproducible.

https://www.nature.com/articles/s42256-026-01219-7

### 8.6 Perception caution
Marjieh et al., *Scientific Reports* (2024), compared model-derived judgments with human sensory datasets across six modalities and discuss both useful correlations and limitations.

**Implication:** distinguish direct signal evidence from language-mediated interpretation, especially for audio, music, and visual semantics.

https://www.nature.com/articles/s41598-024-72071-1

## 9. Open-source landscape

| Project | Potential role | Recommendation / caution |
|---|---|---|
| FFmpeg | Media probing, decoding, extraction, transcoding | Core media utility; audit LGPL/GPL build configuration |
| PyAV | Python access to FFmpeg streams/frames | Use only where CLI is insufficient |
| PySceneDetect | Shot/scene boundaries | Strong candidate; benchmark on our clips |
| Whisper / Faster-Whisper | Speech transcription | Adapter; reproduce performance on Persian CPU test set |
| PaddleOCR | OCR on frames and images | Optional due to runtime/dependency footprint |
| Apache Tika | Broad document metadata/text extraction | Optional adapter; Java runtime weight matters |
| Unstructured | Python document partitioning/extraction | Alternative adapter; inspect dependency footprint |
| FOCUS | Budget-aware keyframe selection | Study/adapt principle; do not import full stack into MVP |
| RVTBench | Video reasoning evaluation inspiration | Borrow task taxonomy; check dataset/code rights |
| TranscreveAI | Multimodal video dossier example | Study schema/UX; audit maintenance and security |
| VIndex | JSON-first video indexing example | Study simple output design; audit code/license |
| Vidat | Human temporal/spatial annotation | Study review UX, not a core runtime dependency |

Repositories:
- https://github.com/FFmpeg/FFmpeg
- https://github.com/PyAV-Org/PyAV
- https://github.com/Breakthrough/PySceneDetect
- https://github.com/openai/whisper
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/PaddlePaddle/PaddleOCR
- https://github.com/apache/tika
- https://github.com/Unstructured-IO/unstructured
- https://github.com/NUS-HPC-AI-Lab/FOCUS
- https://github.com/yiqings/rvt
- https://github.com/DeHor-Labs/transcreve-ai
- https://github.com/vaibhav-space/vindex
- https://github.com/anucvml/vidat

### License and provenance notes
Repository-level license metadata is not sufficient to establish the rights for every dependency, model weight, sample, or dataset. FOCUS is identified as Apache-2.0; RVT code repository metadata identifies CC0-1.0; Unstructured and PaddleOCR identify Apache-2.0. The RVTBench article and Zenodo dataset have separate licensing terms that must be checked before reuse. FFmpeg is LGPL 2.1-or-later, while optional GPL components can change distribution obligations. Perform a per-component license, model-weight, and data-provenance audit before bundling or redistributing anything.

## 10. Simplification and pruning decisions

### Defer or remove from MVP

| Candidate | Decision | Reason |
|---|---|---|
| Instagram-specific downloader | Remove from core | Platform-independent file intake is primary |
| Multiple platform scrapers | Defer / optional adapters | Fragile, policy-sensitive, unnecessary for core |
| Free-running multi-agent system | Defer | Expensive, hard to debug and reproduce |
| LangGraph/agent framework | Defer | Deterministic pipeline stages are sufficient initially |
| Redis/Celery/Kafka | Defer | No distributed workload demonstrated |
| PostgreSQL from day one | Defer | JSON + SQLite suffice for initial single-user workflow |
| Qdrant/FAISS/vector DB | Defer | Add only after retrieval benchmark requires it |
| Neo4j/graph DB | Defer | Begin with evidence-linked JSON relations |
| SaaS billing/multi-tenancy | Defer | Demand and unit economics not validated |
| Kubernetes/microservices | Remove from initial architecture | Excessive operational complexity |
| Face recognition/emotion classification | Exclude from MVP | Privacy, reliability, and relevance concerns |
| Vision model on every frame | Remove | Wasteful; use adaptive sampling |
| Original media in Git | Prohibit | Privacy, rights, and repository hygiene risk |
| Overlapping parsers for same file family | Avoid | Duplicate dependencies and inconsistent outputs |
| Full mobile/desktop/web implementations at once | Defer | Validate pipeline before selecting UI surfaces |

### Keep
- File/folder import and safe validation.
- FFmpeg/ffprobe media inspection.
- Optional speech, scene, OCR, and document adapters.
- One versioned timeline/evidence schema.
- JSON-first outputs and Markdown export.
- Human review and explicit uncertainty.
- Tests, license inventory, and reproducibility manifest.

## 11. Code quality and engineering workflow

- Modular boundaries: `intake`, `media`, `documents`, `timeline`, `evidence`, `analysis`, `export`.
- Thin provider adapters with stable typed contracts.
- No business logic inside UI components.
- Centralize format detection and capability declarations.
- No hidden network calls during local analysis.
- Keep optional dependencies truly optional.
- Prefer deterministic transformations and persist run configuration.
- Add linting, formatting, type checks, unit/integration tests, dependency and license checks to CI.
- A feature needs a concrete user problem, measurable acceptance criteria, and a maintenance rationale.
- Status vocabulary: `PASS`, `FAIL`, `NOT RUN`, `BLOCKED`.

## 12. Benchmark plan

Build an initial human-reviewed set of approximately 20–30 lawfully usable media assets. Cover Persian and English; speech/noise/music; educational, tutorial, interview, promotional, and technical content; fast/slow editing; on-screen text; and companion documents.

Measure:
- Transcript WER and timestamp error.
- OCR CER, layout, and reading-order quality.
- Scene boundary precision/recall with boundary tolerance.
- Keyframe recall under a fixed frame/token budget.
- Temporal and spatial grounding accuracy.
- Evidence coverage and unsupported-claim rate.
- Citation/source-pointer correctness.
- Re-run consistency and provenance completeness.
- Wall-clock time, peak RAM, disk use, and estimated cost per media minute.

Keep near-duplicate/source groups together during dataset splitting. Report confidence intervals when sample size permits. Never mark a benchmark PASS before execution.

## 13. Phased roadmap

| Phase | Deliverable | Exit condition |
|---|---|---|
| 0 | Charter, schemas, repository hygiene, benchmark definition | Scope and data boundaries approved |
| 1 | MP4 + audio/image/text sidecar import, metadata, JSON manifest | Repeatable import/validation tests pass |
| 2 | Transcript, scene detection, selected frames, OCR | Timestamped outputs inspectable and linked |
| 3 | Unified timeline, evidence ledger, JSON/Markdown export | Claims link to source evidence |
| 4 | Quick Scan / Deep Review / Question-Targeted | Budget/quality comparison completed |
| 5 | Human review UX and technical reverse-engineering mode | User can correct/approve uncertain evidence |
| 6 | More document formats and optional import adapters | Support matrix backed by tests |
| 7 | Multi-user/cloud/API only if demand is validated | Cost, privacy, and operations review approved |

## 14. Public repository hygiene

VINT remains Public. Do not commit:
- Uploaded user media or extracted private frames/audio.
- Personal transcripts, private research files, or sensitive metadata.
- API keys, cookies, tokens, passwords, `.env` files, or account exports.
- Model caches, downloaded model weights, large intermediate artifacts, or local databases.

Use `.gitignore`, synthetic or explicitly licensed fixtures, secret scanning, and a clear media-data policy. Public source and documentation are appropriate; private media workspaces are not Git content by default.

## 15. Initial case study and execution status

### ANC sample
A user-uploaded MP4 was the primary input. Speech extraction was performed using Descript and an initial scientific review was made of the explanation of Active Noise Cancellation.

Initial scientific qualification: destructive interference is a valid ANC principle, but ANC does not make all surrounding air motionless. Performance depends on frequency, phase, amplitude, latency, and acoustic geometry; low-frequency continuous noise is generally easier to cancel than abrupt high-frequency sounds.

### Status table

| Work item | Status | Evidence / note |
|---|---|---|
| User-uploaded MP4 used as primary case input | PASS | Speech extraction performed in earlier analysis |
| Instagram page used successfully as source | BLOCKED | URL did not provide reliable source media |
| Initial ANC scientific review | PASS (limited) | Not a complete technical validation |
| Full frame-by-frame review and OCR for sample | NOT RUN | Outstanding |
| VINT repository metadata inspected | PASS | Repository ID 1449560266; default branch main; public |
| VINT contents before publication | PASS — empty | No existing project files found |
| Product implementation and benchmark | NOT RUN | Proposal only |

## 16. Publication record

This report is the first documentation artifact for Reel Intelligence within VINT.

**Path:** `projects/reel-intelligence/WORK_REPORT_0001.md`  
**Commit message:** `docs(reel-intelligence): add research and architecture work report`  
**Target branch:** `main`

Expected change: add this one documentation file and its parent directories. No application code, dependencies, workflows, repository settings, or source media are changed.

No implementation or benchmark completion is claimed by this report.

---

## References

### Nature Portfolio
1. Schulze Buschoff, L. M. et al. (2025). Visual cognition in multimodal large language models. *Nature Machine Intelligence*. https://doi.org/10.1038/s42256-024-00963-y
2. Shen, Y. et al. (2026). RVTBench. *Scientific Data*. https://doi.org/10.1038/s41597-026-07670-w
3. Bernett, J. et al. (2024). Guiding questions to avoid data leakage in biological machine learning applications. *Nature Methods*. https://doi.org/10.1038/s41592-024-02362-y
4. Joeres, R. et al. (2025). Data splitting to avoid information leakage with DataSAIL. *Nature Communications*. https://doi.org/10.1038/s41467-025-58606-8
5. Li, D.-L. et al. (2025). Printed document layout analysis and optical character recognition system based on deep learning. *Scientific Reports*. https://doi.org/10.1038/s41598-025-07439-y
6. (2026). Recognizing reproducibility and reusability in times of fast science. *Nature Machine Intelligence*. https://doi.org/10.1038/s42256-026-01219-7
7. Marjieh, R. et al. (2024). Large language models predict human sensory judgments across six modalities. *Scientific Reports*. https://doi.org/10.1038/s41598-024-72071-1

### Open-source repositories
See Section 9 for direct repository links. Repository metadata, branch names, licenses, dependencies, model weights, and data provenance must be rechecked before adopting or redistributing code or artifacts.
