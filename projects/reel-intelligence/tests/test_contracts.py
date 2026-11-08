import pytest

from reel_intelligence.contracts import ContractError, validate_bundle, validate_record


def asset():
    return {
        "schema_version": "1.0", "record_type": "asset",
        "asset_id": "asset-001", "sha256": "a" * 64,
        "media_type": "video", "filename": "sample.mp4",
        "byte_size": 1200, "source": {"kind": "local_file"},
        "created_at": "2026-11-08T07:00:00Z",
    }


def test_accepts_valid_asset():
    assert validate_record(asset())["asset_id"] == "asset-001"


@pytest.mark.parametrize("field,value,match", [
    ("record_type", "mystery", "record_type"),
    ("sha256", "not-a-hash", "sha256"),
    ("byte_size", -1, "byte_size"),
    ("created_at", "2026-11-08T07:00:00", "timezone"),
    ("byt_size", 1200, "unknown"),
])
def test_rejects_invalid_asset_fields(field, value, match):
    item = asset()
    item[field] = value
    with pytest.raises(ContractError, match=match):
        validate_record(item)


def test_preserves_persian_unicode():
    item = asset()
    item["filename"] = "آزمایش-صوت.mp4"
    assert validate_record(item)["filename"] == "آزمایش-صوت.mp4"


def test_supported_claim_requires_evidence():
    claim = {
        "schema_version": "1.0", "record_type": "claim",
        "claim_id": "claim-1", "statement": "The device uses ANC",
        "status": "supported", "evidence_ids": [],
        "created_at": "2026-11-08T07:00:00Z",
    }
    with pytest.raises(ContractError, match="evidence_ids"):
        validate_record(claim)


def test_rejects_reversed_timeline_interval():
    event = {
        "schema_version": "1.0", "record_type": "timeline_event",
        "event_id": "event-1", "asset_id": "asset-1",
        "start_ms": 900, "end_ms": 800, "event_type": "observation",
        "created_at": "2026-11-08T07:00:00Z",
    }
    with pytest.raises(ContractError, match="end_ms"):
        validate_record(event)


def test_evidence_requires_locator():
    evidence = {
        "schema_version": "1.0", "record_type": "evidence",
        "evidence_id": "e-1", "asset_id": "asset-1",
        "modality": "video", "locator": {},
        "observation": "A person appears",
        "created_at": "2026-11-08T07:00:00Z",
    }
    with pytest.raises(ContractError, match="locator"):
        validate_record(evidence)


def test_bundle_rejects_broken_asset_references():
    event = {
        "schema_version": "1.0", "record_type": "timeline_event",
        "event_id": "event-1", "asset_id": "missing-asset",
        "start_ms": 0, "end_ms": 100, "event_type": "observation",
        "created_at": "2026-11-08T07:00:00Z",
    }
    with pytest.raises(ContractError, match="missing-asset"):
        validate_bundle([event])


def test_bundle_accepts_linked_supported_claim():
    a = asset()
    e = {
        "schema_version": "1.0", "record_type": "evidence",
        "evidence_id": "e-1", "asset_id": "asset-001",
        "modality": "video", "locator": {"start_ms": 10, "end_ms": 20},
        "observation": "Visible object", "created_at": "2026-11-08T07:00:00Z",
    }
    c = {
        "schema_version": "1.0", "record_type": "claim",
        "claim_id": "claim-1", "statement": "An object is visible",
        "status": "supported", "evidence_ids": ["e-1"],
        "created_at": "2026-11-08T07:00:00Z",
    }
    assert len(validate_bundle([a, e, c])) == 3
