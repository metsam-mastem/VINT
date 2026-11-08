import pytest

from reel_intelligence.catalog import AssetCatalog, CatalogError
from reel_intelligence.intake import inspect_file


def make_asset(tmp_path, name="audio.mp3"):
    source = tmp_path / name
    source.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00catalog-test")
    return inspect_file(source, root=tmp_path)


def test_catalog_persists_and_retrieves_unicode_asset(tmp_path):
    db = tmp_path / "catalog.sqlite3"
    asset = make_asset(tmp_path)
    asset["filename"] = "نمونه-صوت.mp3"

    catalog = AssetCatalog(db)
    assert catalog.add_asset(asset) is True

    record = catalog.get_asset(asset["asset_id"])
    assert record["asset"] == asset
    assert record["probe"] is None
    assert record["asset"]["filename"] == "نمونه-صوت.mp3"


def test_catalog_add_is_idempotent_for_same_asset(tmp_path):
    asset = make_asset(tmp_path)
    catalog = AssetCatalog(tmp_path / "catalog.sqlite3")

    assert catalog.add_asset(asset) is True
    assert catalog.add_asset(asset) is False
    assert len(catalog.list_assets()) == 1


def test_catalog_stores_probe_metadata_separately(tmp_path):
    asset = make_asset(tmp_path)
    catalog = AssetCatalog(tmp_path / "catalog.sqlite3")
    catalog.add_asset(asset)
    probe = {"tool": "ffprobe", "format": {"duration_seconds": 4.5}, "streams": []}

    catalog.attach_probe(asset["asset_id"], probe)

    assert catalog.get_asset(asset["asset_id"])["probe"] == probe


def test_catalog_filters_and_paginates_assets(tmp_path):
    video = make_asset(tmp_path, "one.mp3")
    second = tmp_path / "two.png"
    second.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    image = inspect_file(second, root=tmp_path)
    catalog = AssetCatalog(tmp_path / "catalog.sqlite3")
    catalog.add_asset(video)
    catalog.add_asset(image)

    assert len(catalog.list_assets(media_type="audio")) == 1
    assert len(catalog.list_assets(media_type="image")) == 1
    assert len(catalog.list_assets(limit=1)) == 1
    assert len(catalog.list_assets(offset=1)) == 1


def test_catalog_rejects_invalid_asset_record(tmp_path):
    asset = make_asset(tmp_path)
    asset["sha256"] = "invalid"
    catalog = AssetCatalog(tmp_path / "catalog.sqlite3")

    with pytest.raises(CatalogError):
        catalog.add_asset(asset)


def test_catalog_rejects_unknown_asset_id_for_probe(tmp_path):
    catalog = AssetCatalog(tmp_path / "catalog.sqlite3")
    with pytest.raises(CatalogError, match="not found"):
        catalog.attach_probe("missing", {"tool": "ffprobe"})


def test_catalog_rejects_hash_collision_with_different_asset_id(tmp_path):
    asset = make_asset(tmp_path)
    duplicate = dict(asset)
    duplicate["asset_id"] = "asset-different-id"
    catalog = AssetCatalog(tmp_path / "catalog.sqlite3")
    catalog.add_asset(asset)

    with pytest.raises(CatalogError):
        catalog.add_asset(duplicate)
