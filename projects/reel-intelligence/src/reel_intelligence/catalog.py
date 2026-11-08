"""Local SQLite catalog for canonical Asset records and probe metadata."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .contracts import ContractError, validate_record


class CatalogError(ValueError):
    """Raised when a catalog operation cannot be completed safely."""


class AssetCatalog:
    """Small, local-only SQLite catalog with no external service dependency."""

    SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except (OSError, sqlite3.Error) as exc:
            raise CatalogError(f"cannot initialize asset catalog: {exc}") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > self.SCHEMA_VERSION:
                raise CatalogError(
                    f"catalog schema {version} is newer than supported schema {self.SCHEMA_VERSION}"
                )
            if version == 0:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS assets (
                        asset_id TEXT PRIMARY KEY,
                        sha256 TEXT NOT NULL UNIQUE,
                        asset_json TEXT NOT NULL,
                        probe_json TEXT,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets(sha256);
                    CREATE INDEX IF NOT EXISTS idx_assets_last_seen ON assets(last_seen_at);
                    """
                )
                connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _serialize(value: Any, field: str) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise CatalogError(f"{field} must be JSON-serializable") from exc

    def add_asset(self, asset: dict[str, Any], *, probe: dict[str, Any] | None = None) -> bool:
        """Insert or refresh an Asset. Returns True only for a new asset ID."""
        try:
            validated = validate_record(asset)
            if validated["record_type"] != "asset":
                raise CatalogError("only Asset records can be added to the asset catalog")
            if probe is not None and not isinstance(probe, dict):
                raise CatalogError("probe metadata must be an object")
            asset_json = self._serialize(validated, "asset")
            probe_json = self._serialize(probe, "probe") if probe is not None else None
            now = self._now()
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT sha256 FROM assets WHERE asset_id = ?", (validated["asset_id"],)
                ).fetchone()
                if existing is not None and existing["sha256"] != validated["sha256"]:
                    raise CatalogError("asset ID is already associated with a different content hash")
                if existing is None:
                    connection.execute(
                        """INSERT INTO assets
                           (asset_id, sha256, asset_json, probe_json, first_seen_at, last_seen_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (validated["asset_id"], validated["sha256"], asset_json, probe_json, now, now),
                    )
                    return True
                connection.execute(
                    """UPDATE assets
                       SET asset_json = ?, probe_json = COALESCE(?, probe_json), last_seen_at = ?
                       WHERE asset_id = ?""",
                    (asset_json, probe_json, now, validated["asset_id"]),
                )
                return False
        except (ContractError, sqlite3.Error) as exc:
            if isinstance(exc, CatalogError):
                raise
            raise CatalogError(f"cannot add asset: {exc}") from exc

    def attach_probe(self, asset_id: str, probe: dict[str, Any]) -> None:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise CatalogError("asset_id must be a non-empty string")
        if not isinstance(probe, dict):
            raise CatalogError("probe metadata must be an object")
        probe_json = self._serialize(probe, "probe")
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE assets SET probe_json = ?, last_seen_at = ? WHERE asset_id = ?",
                    (probe_json, self._now(), asset_id),
                )
                if cursor.rowcount == 0:
                    raise CatalogError(f"asset not found: {asset_id}")
        except sqlite3.Error as exc:
            raise CatalogError(f"cannot attach probe metadata: {exc}") from exc

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """SELECT asset_json, probe_json, first_seen_at, last_seen_at
                       FROM assets WHERE asset_id = ?""",
                    (asset_id,),
                ).fetchone()
            if row is None:
                return None
            return {
                "asset": json.loads(row["asset_json"]),
                "probe": json.loads(row["probe_json"]) if row["probe_json"] is not None else None,
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise CatalogError(f"cannot read asset: {exc}") from exc

    def list_assets(self, *, media_type: str | None = None, limit: int = 100,
                    offset: int = 0) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise CatalogError("limit must be an integer between 1 and 1000")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise CatalogError("offset must be a non-negative integer")
        if media_type is not None and media_type not in {
            "video", "audio", "image", "document", "text", "archive", "other"
        }:
            raise CatalogError("unsupported media_type filter")
        try:
            with self._connect() as connection:
                if media_type is None:
                    rows = connection.execute(
                        """SELECT asset_json, probe_json, first_seen_at, last_seen_at
                           FROM assets ORDER BY last_seen_at DESC, asset_id ASC LIMIT ? OFFSET ?""",
                        (limit, offset),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """SELECT asset_json, probe_json, first_seen_at, last_seen_at
                           FROM assets WHERE json_extract(asset_json, '$.media_type') = ?
                           ORDER BY last_seen_at DESC, asset_id ASC LIMIT ? OFFSET ?""",
                        (media_type, limit, offset),
                    ).fetchall()
            return [
                {
                    "asset": json.loads(row["asset_json"]),
                    "probe": json.loads(row["probe_json"]) if row["probe_json"] is not None else None,
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                }
                for row in rows
            ]
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise CatalogError(f"cannot list assets: {exc}") from exc
