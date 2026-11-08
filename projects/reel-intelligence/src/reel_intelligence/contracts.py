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
_SOURCE_FIELDS = {"kind", "uri", "path", "platform", "external_id", "imported_at", "details"}
_LOCATOR_FIELDS = {
    "start_ms", "end_ms", "page", "frame", "byte_offset", "byte_length",
    "timestamp_ms", "unit", "path", "selector", "x", "y", "width", "height", "region",
}
_LOCATOR_ANCHORS = {
    "start_ms", "page", "frame", "byte_offset", "timestamp_ms", "path",
    "selector", "x", "region",
}


class ContractError(ValueError):
    """Raised when a canonical record violates the contract."""


def _fail(field: str, message: str) -> None:
    raise ContractError(f"{field}: {message}")


def _nonempty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(field, "must be a non-empty string")


def _enum(value: Any, allowed: set[str], field: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        _fail(field, f"must be one of: {', '.join(sorted(allowed))}")


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
        _fail(field, "must be a finite number between 0 and 1")


def _string_list(value: Any, field: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, list):
        _fail(field, "must be an array")
    if nonempty and not value:
        _fail(field, "must contain at least one evidence reference")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        _fail(field, "must contain only non-empty strings")
    if len(set(value)) != len(value):
        _fail(field, "must not contain duplicate values")


def _validate_source(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        _fail("source", "must be a non-empty object")
    unknown = set(value) - _SOURCE_FIELDS
    if unknown:
        _fail("source", f"unsupported fields: {', '.join(sorted(unknown))}")
    _nonempty_string(value.get("kind"), "source.kind")
    for field in ("uri", "path", "platform", "external_id"):
        if field in value:
            _nonempty_string(value[field], f"source.{field}")
    if "imported_at" in value:
        _timestamp(value["imported_at"], "source.imported_at")
    if "details" in value and not isinstance(value["details"], dict):
        _fail("source.details", "must be an object")


def _validate_locator(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        _fail("locator", "must be a non-empty object identifying source position")
    unknown = set(value) - _LOCATOR_FIELDS
    if unknown:
        _fail("locator", f"unsupported fields: {', '.join(sorted(unknown))}")
    if not (_LOCATOR_ANCHORS & set(value)):
        _fail("locator", "must include at least one positional field")
    for field in ("start_ms", "end_ms", "page", "frame", "byte_offset", "byte_length", "timestamp_ms", "x", "y", "width", "height"):
        if field in value:
            _integer(value[field], f"locator.{field}")
    if ("start_ms" in value) != ("end_ms" in value):
        _fail("locator", "start_ms and end_ms must be provided together")
    if "start_ms" in value and value["end_ms"] < value["start_ms"]:
        _fail("locator.end_ms", "must be >= locator.start_ms")
    if ("byte_offset" in value) != ("byte_length" in value):
        _fail("locator", "byte_offset and byte_length must be provided together")
    for field in ("unit", "path", "selector"):
        if field in value:
            _nonempty_string(value[field], f"locator.{field}")
    if "region" in value and not isinstance(value["region"], (dict, list, str)):
        _fail("locator.region", "must be an object, array, or string")


def validate_record(record: Any) -> dict[str, Any]:
    """Validate one record and return the original mapping unchanged."""
    if not isinstance(record, dict):
        _fail("record", "must be a JSON object")
    kind = record.get("record_type")
    if not isinstance(kind, str) or kind not in _FIELDS:
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
        _enum(record["media_type"], _ALLOWED_MEDIA, "media_type")
        _nonempty_string(record["filename"], "filename")
        _integer(record["byte_size"], "byte_size")
        _validate_source(record["source"])
        for field in ("duration_ms", "width", "height"):
            if field in record:
                _integer(record[field], field)
        if "metadata" in record and not isinstance(record["metadata"], dict):
            _fail("metadata", "must be an object")

    elif kind == "analysis_manifest":
        _nonempty_string(record["asset_id"], "asset_id")
        _nonempty_string(record["pipeline_version"], "pipeline_version")
        _enum(record["status"], _ALLOWED_MANIFEST_STATUS, "status")
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
        _enum(record["modality"], _ALLOWED_MODALITIES, "modality")
        _validate_locator(record["locator"])
        _nonempty_string(record["observation"], "observation")
        if "extractor" in record:
            _nonempty_string(record["extractor"], "extractor")
        if "confidence" in record:
            _confidence(record["confidence"], "confidence")
        if "content_hash" in record:
            if not isinstance(record["content_hash"], str) or not _HEX_256.fullmatch(record["content_hash"]):
                _fail("content_hash", "must be a SHA-256 hex digest")

    elif kind == "claim":
        _nonempty_string(record["statement"], "statement")
        _enum(record["status"], _ALLOWED_CLAIM_STATUS, "status")
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
    if isinstance(records, (str, bytes, dict)):
        _fail("bundle", "must be an iterable of record objects, not a string or object")
    try:
        validated = [validate_record(item) for item in records]
    except TypeError as exc:
        _fail("bundle", f"must be an iterable of record objects ({exc})")
    by_type: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in _FIELDS}
    for item in validated:
        kind = item["record_type"]
        identifier = item[_ID_FIELDS[kind]]
        if identifier in by_type[kind]:
            _fail(_ID_FIELDS[kind], f"duplicate identifier: {identifier}")
        by_type[kind][identifier] = item

    assets = by_type["asset"]
    evidence = by_type["evidence"]
    claims = by_type["claim"]
    for kind in ("analysis_manifest", "timeline_event", "evidence"):
        for item in by_type[kind].values():
            asset_id = item["asset_id"]
            if asset_id not in assets:
                _fail("asset_id", f"reference to missing asset: {asset_id}")
    for item in claims.values():
        for evidence_id in item["evidence_ids"]:
            if evidence_id not in evidence:
                _fail("evidence_ids", f"reference to missing evidence: {evidence_id}")
        for claim_id in item.get("related_claim_ids", []):
            if claim_id == item["claim_id"]:
                _fail("related_claim_ids", "a claim cannot reference itself")
            if claim_id not in claims:
                _fail("related_claim_ids", f"reference to missing claim: {claim_id}")
    for item in by_type["timeline_event"].values():
        for evidence_id in item.get("evidence_ids", []):
            linked = evidence.get(evidence_id)
            if linked is None:
                _fail("evidence_ids", f"reference to missing evidence: {evidence_id}")
            if linked["asset_id"] != item["asset_id"]:
                _fail("evidence_ids", "timeline evidence must belong to the same asset")
    return validated
