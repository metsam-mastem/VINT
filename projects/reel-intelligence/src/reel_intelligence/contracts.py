"""Strict, dependency-free validators for REEL INTELLIGENCE canonical records."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")

_COMMON = {"schema_version", "record_type"}
_FIELDS = {
    "asset": {
        "required": {"asset_id", "sha256", "media_type", "filename", "byte_size", "source", "created_at"},
        "optional": {"duration_ms", "width", "height", "metadata"},
    },
    "analysis_manifest": {
        "required": {"manifest_id", "asset_id", "pipeline_version", "status", "started_at", "created_at"},
        "optional": {"finished_at", "toolchain", "output_refs", "warnings", "profile"},
    },
    "timeline_event": {
        "required": {"event_id", "asset_id", "start_ms", "end_ms", "event_type", "created_at"},
        "optional": {"text", "evidence_ids", "confidence", "producer"},
    },
    "evidence": {
        "required": {"evidence_id", "asset_id", "modality", "locator", "observation", "created_at"},
        "optional": {"extractor", "confidence", "content_hash"},
    },
    "claim": {
        "required": {"claim_id", "statement", "status", "evidence_ids", "created_at"},
        "optional": {"confidence", "rationale", "related_claim_ids"},
    },
}
_ID_FIELDS = {
    "asset": "asset_id",
    "analysis_manifest": "manifest_id",
    "timeline_event": "event_id",
    "evidence": "evidence_id",
    "claim": "claim_id",
}
_ALLOWED_MEDIA = {"video", "audio", "image", "document", "text", "archive", "other"}
_ALLOWED_MODALITIES = {"video", "audio", "image", "document", "text", "metadata"}
_ALLOWED_CLAIM_STATUS = {"supported", "contradicted", "uncertain", "unverified"}
_ALLOWED_MANIFEST_STATUS = {"running", "completed", "failed", "partial"}


class ContractError(ValueError):
    """Raised when a canonical record violates the contract."""


def _fail(field: str, message: str) -> None:
    raise ContractError(f"{field}: {message}")


def _nonempty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(field, "must be a non-empty string")


def _timestamp(value: Any, field: str) -> datetime:
    _nonempty_string(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(field, "must be an ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(field, "must include an explicit timezone")
    return parsed


def _integer(value: Any, field: str, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(field, f"must be an integer >= {minimum}")


def _confidence(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        _fail(field, "must be a number between 0 and 1")


def _string_list(value: Any, field: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, list):
        _fail(field, "must be an array")
    if nonempty and not value:
        _fail(field, "must contain at least one evidence reference")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        _fail(field, "must contain only non-empty strings")
    if len(set(value)) != len(value):
        _fail(field, "must not contain duplicate values")


def validate_record(record: Any) -> dict[str, Any]:
    """Validate one record and return the original mapping unchanged."""
    if not isinstance(record, dict):
        _fail("record", "must be a JSON object")
    kind = record.get("record_type")
    if kind not in _FIELDS:
        _fail("record_type", f"unsupported record type: {kind!r}")
    spec = _FIELDS[kind]
    allowed = _COMMON | spec["required"] | spec["optional"]
    unknown = set(record) - allowed
    if unknown:
        _fail("unknown fields", ", ".join(sorted(unknown)))
    missing = spec["required"] - set(record)
    if missing:
        _fail("missing fields", ", ".join(sorted(missing)))
    if record.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version", f"expected {SCHEMA_VERSION}")
    _nonempty_string(record.get(_ID_FIELDS[kind]), _ID_FIELDS[kind])
    _timestamp(record.get("created_at"), "created_at")

    if kind == "asset":
        if not isinstance(record["sha256"], str) or not _HEX_256.fullmatch(record["sha256"]):
            _fail("sha256", "must be 64 lowercase hexadecimal characters")
        if record["media_type"] not in _ALLOWED_MEDIA:
            _fail("media_type", "unsupported media type")
        _nonempty_string(record["filename"], "filename")
        _integer(record["byte_size"], "byte_size")
        if not isinstance(record["source"], dict) or not record["source"]:
            _fail("source", "must be a non-empty object")
        _nonempty_string(record["source"].get("kind"), "source.kind")
        for field in ("duration_ms", "width", "height"):
            if field in record:
                _integer(record[field], field)
        if "metadata" in record and not isinstance(record["metadata"], dict):
            _fail("metadata", "must be an object")

    elif kind == "analysis_manifest":
        _nonempty_string(record["asset_id"], "asset_id")
        _nonempty_string(record["pipeline_version"], "pipeline_version")
        if record["status"] not in _ALLOWED_MANIFEST_STATUS:
            _fail("status", "unsupported manifest status")
        started = _timestamp(record["started_at"], "started_at")
        if "finished_at" in record:
            finished = _timestamp(record["finished_at"], "finished_at")
            if finished < started:
                _fail("finished_at", "must not precede started_at")
        for field in ("toolchain", "profile"):
            if field in record and not isinstance(record[field], dict):
                _fail(field, "must be an object")
        for field in ("output_refs", "warnings"):
            if field in record:
                _string_list(record[field], field)

    elif kind == "timeline_event":
        _nonempty_string(record["asset_id"], "asset_id")
        _integer(record["start_ms"], "start_ms")
        _integer(record["end_ms"], "end_ms")
        if record["end_ms"] < record["start_ms"]:
            _fail("end_ms", "must be >= start_ms")
        _nonempty_string(record["event_type"], "event_type")
        if "text" in record and not isinstance(record["text"], str):
            _fail("text", "must be a string")
        if "evidence_ids" in record:
            _string_list(record["evidence_ids"], "evidence_ids")
        if "confidence" in record:
            _confidence(record["confidence"], "confidence")
        if "producer" in record:
            _nonempty_string(record["producer"], "producer")

    elif kind == "evidence":
        _nonempty_string(record["asset_id"], "asset_id")
        if record["modality"] not in _ALLOWED_MODALITIES:
            _fail("modality", "unsupported modality")
        if not isinstance(record["locator"], dict) or not record["locator"]:
            _fail("locator", "must be a non-empty object identifying source position")
        for field in ("start_ms", "end_ms", "page", "frame"):
            if field in record["locator"]:
                _integer(record["locator"][field], f"locator.{field}")
        if "start_ms" in record["locator"] and "end_ms" in record["locator"]:
            if record["locator"]["end_ms"] < record["locator"]["start_ms"]:
                _fail("locator.end_ms", "must be >= locator.start_ms")
        _nonempty_string(record["observation"], "observation")
        if "extractor" in record:
            _nonempty_string(record["extractor"], "extractor")
        if "confidence" in record:
            _confidence(record["confidence"], "confidence")
        if "content_hash" in record and not _HEX_256.fullmatch(str(record["content_hash"])):
            _fail("content_hash", "must be a SHA-256 hex digest")

    elif kind == "claim":
        _nonempty_string(record["statement"], "statement")
        if record["status"] not in _ALLOWED_CLAIM_STATUS:
            _fail("status", "unsupported claim status")
        _string_list(record["evidence_ids"], "evidence_ids",
                     nonempty=record["status"] in {"supported", "contradicted"})
        if "confidence" in record:
            _confidence(record["confidence"], "confidence")
        if "rationale" in record:
            _nonempty_string(record["rationale"], "rationale")
        if "related_claim_ids" in record:
            _string_list(record["related_claim_ids"], "related_claim_ids")
    return record


def validate_bundle(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate records and all cross-record references in a bundle."""
    validated = [validate_record(item) for item in records]
    by_type: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in _FIELDS}
    for item in validated:
        kind = item["record_type"]
        identifier = item[_ID_FIELDS[kind]]
        if identifier in by_type[kind]:
            _fail(_ID_FIELDS[kind], f"duplicate identifier: {identifier}")
        by_type[kind][identifier] = item

    assets = by_type["asset"]
    evidence = by_type["evidence"]
    for kind in ("analysis_manifest", "timeline_event", "evidence"):
        for item in by_type[kind].values():
            asset_id = item["asset_id"]
            if asset_id not in assets:
                _fail("asset_id", f"reference to missing asset: {asset_id}")
    for item in by_type["claim"].values():
        for evidence_id in item["evidence_ids"]:
            if evidence_id not in evidence:
                _fail("evidence_ids", f"reference to missing evidence: {evidence_id}")
    for item in by_type["timeline_event"].values():
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id not in evidence:
                _fail("evidence_ids", f"reference to missing evidence: {evidence_id}")
    return validated
