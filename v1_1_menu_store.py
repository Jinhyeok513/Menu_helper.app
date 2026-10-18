"""V1.1 PostgreSQL menu snapshot storage.

Added so URL extraction results survive backend restarts and list/detail requests
can use the same immutable snapshot. ``menu_api.py`` calls this module with a
common menu dictionary and bounded source artifacts; it returns stored snapshot
metadata and the menu dictionary that should be served.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from app_config import AppSettings, settings
from performance_metrics import record_performance_event


SCHEMA_VERSION = "v1_1_002_snapshot_item_details"
EXTRACTION_VERSION = "v1.1"
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "auth",
    "authorization",
    "customer_seat_id",
    "key",
    "ms",
    "password",
    "refresh_token",
    "session",
    "session_id",
    "signature",
    "tableid",
    "table_id",
    "token",
}
VOLATILE_MENU_KEYS = {
    "data_origin",
    "is_stale",
    "last_checked_at",
    "menu_source_id",
    "request_id",
    "retrieved_at",
    "snapshot_id",
    "snapshot_version",
    "source_url",
}


class MenuDatabaseError(RuntimeError):
    """Base class for database failures that are safe to map to API errors."""


class MenuDatabaseNotConfiguredError(MenuDatabaseError):
    """DATABASE_URL is absent or empty."""


class MenuDatabaseUnavailableError(MenuDatabaseError):
    """PostgreSQL could not be reached or a query failed."""


class MenuDatabaseSchemaError(MenuDatabaseError):
    """The database is reachable but the V1.1 schema is not applied."""


@dataclass(frozen=True)
class StoredMenuSnapshot:
    menu_source_id: str
    snapshot_id: str
    snapshot_version: int
    menu_data: dict
    data_origin: str
    is_stale: bool
    refresh_status: str
    reused_snapshot: bool
    last_checked_at: str


def canonicalise_source_url(url: str) -> str:
    """Remove credentials, fragments and known session/table query values."""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname
    if port is not None:
        netloc = f"{hostname}:{port}"
    safe_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in SENSITIVE_QUERY_KEYS
    ]
    safe_query.sort()
    return urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            urlencode(safe_query, doseq=True),
            "",
        )
    )


def _stable_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_value(value: object) -> object:
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _semantic_value(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_MENU_KEYS
        }
    return value


def menu_content_hash(menu_data: dict) -> str:
    """Hash menu meaning while excluding request/time/storage metadata."""
    semantic_menu = {
        "restaurant": _semantic_value(menu_data.get("restaurant") or {}),
        "items": _semantic_value(menu_data.get("items") or []),
    }
    return _stable_hash(semantic_menu)


_SENSITIVE_KEY = (
    r"access[_-]?token|refresh[_-]?token|authorization|cookie|password|secret|"
    r"session(?:_?id)?|customer_seat_id|table_?id|ms|token"
)
_SENSITIVE_JSON_PATTERN = re.compile(
    rf"(?i)([\"'](?:{_SENSITIVE_KEY})[\"']\s*:\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^,}\s]+)"
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    rf"(?i)((?:^|[?&;\s])(?:{_SENSITIVE_KEY})\s*=\s*)"
    r"([^&;\s\"']+)"
)


def _redact_sensitive_text(text: str) -> str:
    redacted = _SENSITIVE_JSON_PATTERN.sub(r'\1"[REDACTED]"', text)
    return _SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)


def _serialise_artifact_body(body: object) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _prepare_artifact(raw_artifact: dict, app_settings: AppSettings) -> dict:
    role = str(raw_artifact.get("role") or "source")[:100]
    content_type = str(raw_artifact.get("content_type") or "application/octet-stream")[
        :200
    ]
    body = _serialise_artifact_body(raw_artifact.get("body"))
    raw_hash = hashlib.sha256(body).hexdigest()
    original_bytes = len(body)
    if original_bytes > app_settings.source_artifact_max_bytes:
        return {
            "role": role,
            "content_type": content_type,
            "sha256": raw_hash,
            "storage_kind": "omitted",
            "content_encoding": None,
            "original_bytes": original_bytes,
            "stored_bytes": 0,
            "payload": None,
            "safe_to_store": False,
            "omission_reason": "source_artifact_too_large",
        }

    decoded = body.decode("utf-8", errors="replace")
    redacted = _redact_sensitive_text(decoded).encode("utf-8")
    compressed = gzip.compress(redacted, compresslevel=6)
    if len(compressed) > app_settings.source_artifact_max_compressed_bytes:
        return {
            "role": role,
            "content_type": content_type,
            "sha256": raw_hash,
            "storage_kind": "omitted",
            "content_encoding": None,
            "original_bytes": original_bytes,
            "stored_bytes": 0,
            "payload": None,
            "safe_to_store": False,
            "omission_reason": "compressed_artifact_too_large",
        }
    return {
        "role": role,
        "content_type": content_type,
        "sha256": raw_hash,
        "storage_kind": "postgres_gzip",
        "content_encoding": "gzip",
        "original_bytes": original_bytes,
        "stored_bytes": len(compressed),
        "payload": compressed,
        "safe_to_store": True,
        "omission_reason": None,
    }


def _platform_for_menu(menu_data: dict) -> str:
    method = str((menu_data.get("provenance") or {}).get("extraction_method") or "")
    if method.startswith("square"):
        return "square"
    if method:
        return "web"
    return "unknown"


def _annotate_stored_menu(
    menu_data: dict,
    *,
    source_id: UUID,
    snapshot_id: UUID,
    version: int,
    data_origin: str,
    is_stale: bool,
    refresh_status: str,
    last_checked_at: datetime,
) -> dict:
    result = copy.deepcopy(menu_data)
    provenance = result.setdefault("provenance", {})
    provenance.update(
        {
            "menu_source_id": str(source_id),
            "snapshot_id": str(snapshot_id),
            "snapshot_version": version,
            "data_origin": data_origin,
            "is_stale": is_stale,
            "refresh_status": refresh_status,
            "last_checked_at": last_checked_at.isoformat(),
        }
    )
    for item in result.get("items") or []:
        if isinstance(item, dict):
            item["menu_source_id"] = str(source_id)
            item["snapshot_id"] = str(snapshot_id)
            item["snapshot_version"] = version
    return result


class MenuStore:
    """Small psycopg repository for versioned menu snapshots."""

    def __init__(self, app_settings: AppSettings = settings) -> None:
        self.settings = app_settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.database_url)

    def require_configured(self) -> None:
        if not self.configured:
            raise MenuDatabaseNotConfiguredError(
                "DATABASE_URL이 설정되지 않았습니다."
            )

    def require_ready(self) -> None:
        """Distinguish missing config, unreachable DB and unapplied schema."""
        self.require_configured()
        readiness = self.readiness()
        if readiness["database"] in {"schema_missing", "schema_outdated"}:
            raise MenuDatabaseSchemaError(
                "V1.1 데이터베이스 스키마가 적용되지 않았습니다."
            )
        if not readiness["ready"]:
            raise MenuDatabaseUnavailableError(
                "PostgreSQL readiness 확인에 실패했습니다."
            )

    @contextmanager
    def _connection(self) -> Iterator[object]:
        self.require_configured()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise MenuDatabaseUnavailableError(
                "PostgreSQL 드라이버가 설치되지 않았습니다."
            ) from error

        try:
            with psycopg.connect(
                self.settings.database_url,
                connect_timeout=max(
                    1, math.ceil(self.settings.database_connect_timeout_seconds)
                ),
                options=(
                    "-c statement_timeout="
                    f"{max(1, self.settings.database_statement_timeout_ms)}"
                ),
                row_factory=dict_row,
            ) as connection:
                yield connection
        except MenuDatabaseError:
            raise
        except psycopg.Error as error:
            raise MenuDatabaseUnavailableError(
                "PostgreSQL 연결 또는 쿼리에 실패했습니다."
            ) from error

    def apply_schema(self) -> list[str]:
        schema_path = Path(__file__).with_name("v1_1_schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self._connection() as connection:
            connection.execute(schema_sql, prepare=False)
        return self.schema_versions()

    def schema_versions(self) -> list[str]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT version FROM menu_schema_migrations ORDER BY applied_at"
                ).fetchall()
        except MenuDatabaseUnavailableError as error:
            cause_text = str(error.__cause__ or "").lower()
            if "menu_schema_migrations" in cause_text or "does not exist" in cause_text:
                raise MenuDatabaseSchemaError(
                    "V1.1 데이터베이스 스키마가 적용되지 않았습니다."
                ) from error
            raise
        return [str(row["version"]) for row in rows]

    def readiness(self) -> dict:
        if not self.configured:
            return {
                "ready": False,
                "database": "not_configured",
                "schema_version": None,
            }
        try:
            versions = self.schema_versions()
        except MenuDatabaseSchemaError:
            return {
                "ready": False,
                "database": "schema_missing",
                "schema_version": None,
            }
        except MenuDatabaseUnavailableError:
            return {
                "ready": False,
                "database": "unavailable",
                "schema_version": None,
            }
        ready = SCHEMA_VERSION in versions
        return {
            "ready": ready,
            "database": "ready" if ready else "schema_outdated",
            "schema_version": versions[-1] if versions else None,
        }

    def _row_to_snapshot(
        self,
        row: dict,
        *,
        data_origin: str,
        is_stale: bool,
        refresh_status: str,
        reused_snapshot: bool,
    ) -> StoredMenuSnapshot:
        menu_data = _annotate_stored_menu(
            row["common_menu"],
            source_id=row["source_id"],
            snapshot_id=row["snapshot_id"],
            version=row["version"],
            data_origin=data_origin,
            is_stale=is_stale,
            refresh_status=refresh_status,
            last_checked_at=row["last_checked_at"] or row["created_at"],
        )
        return StoredMenuSnapshot(
            menu_source_id=str(row["source_id"]),
            snapshot_id=str(row["snapshot_id"]),
            snapshot_version=row["version"],
            menu_data=menu_data,
            data_origin=data_origin,
            is_stale=is_stale,
            refresh_status=refresh_status,
            reused_snapshot=reused_snapshot,
            last_checked_at=(row["last_checked_at"] or row["created_at"]).isoformat(),
        )

    def save_menu_snapshot(
        self,
        *,
        menu_data: dict,
        source_url: str,
        artifacts: list[dict],
        request_id: str,
        extraction_status: str,
        validation_status: str,
        started_at: datetime | None = None,
    ) -> StoredMenuSnapshot:
        """Atomically deduplicate, version and promote a menu snapshot."""
        from psycopg.types.json import Jsonb

        if extraction_status not in {"success", "partial"}:
            raise ValueError("저장 가능한 추출 상태가 아닙니다.")
        now = datetime.now(UTC)
        started_at = started_at or now
        canonical_url = canonicalise_source_url(source_url)
        parsed = urlsplit(canonical_url)
        host = parsed.hostname or "unknown"
        restaurant = menu_data.get("restaurant") or {}
        restaurant_id = str(restaurant.get("restaurant_id") or "unknown")
        restaurant_name = restaurant.get("name")
        platform = _platform_for_menu(menu_data)
        store_identity = f"{platform}|{host}|{restaurant_id}"
        locator_key = _stable_hash({"url": canonical_url})
        source_key = _stable_hash(
            {"store": store_identity, "channel": "online_menu", "url": canonical_url}
        )
        content_hash = menu_content_hash(menu_data)
        extraction_method = str(
            (menu_data.get("provenance") or {}).get("extraction_method")
            or "unknown"
        )
        prepared_artifacts = [
            _prepare_artifact(artifact, self.settings) for artifact in artifacts
        ]
        db_started_at = datetime.now(UTC)

        try:
            with self._connection() as connection:
                store_id = uuid4()
                store_row = connection.execute(
                    """
                    INSERT INTO menu_stores(
                        store_id, identity_key, restaurant_name, platform,
                        platform_store_id, source_host
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (identity_key) DO UPDATE SET
                        restaurant_name = EXCLUDED.restaurant_name,
                        updated_at = NOW()
                    RETURNING store_id
                    """,
                    (
                        store_id,
                        store_identity,
                        restaurant_name,
                        platform,
                        restaurant_id if restaurant_id != "unknown" else None,
                        host,
                    ),
                ).fetchone()
                store_id = store_row["store_id"]

                proposed_source_id = uuid4()
                source_row = connection.execute(
                    """
                    INSERT INTO menu_sources(
                        source_id, store_id, locator_key, source_key, platform,
                        sales_channel, canonical_url, source_host, source_path,
                        source_identity, last_checked_at
                    ) VALUES (%s, %s, %s, %s, %s, 'online_menu', %s, %s, %s, %s, %s)
                    ON CONFLICT (locator_key) DO UPDATE SET
                        store_id = EXCLUDED.store_id,
                        canonical_url = EXCLUDED.canonical_url,
                        source_identity = EXCLUDED.source_identity,
                        last_checked_at = EXCLUDED.last_checked_at,
                        updated_at = NOW()
                    RETURNING source_id
                    """,
                    (
                        proposed_source_id,
                        store_id,
                        locator_key,
                        source_key,
                        platform,
                        canonical_url,
                        host,
                        parsed.path or "/",
                        Jsonb(
                            {
                                "restaurant_id": restaurant_id,
                                "identity_status": (
                                    "verified_source"
                                    if restaurant_id != "unknown"
                                    else "provisional_url"
                                ),
                            }
                        ),
                        now,
                    ),
                ).fetchone()
                source_id = source_row["source_id"]
                locked_source = connection.execute(
                    """
                    SELECT source_id, current_snapshot_id, last_checked_at
                    FROM menu_sources WHERE source_id = %s FOR UPDATE
                    """,
                    (source_id,),
                ).fetchone()
                current_row = None
                if locked_source["current_snapshot_id"] is not None:
                    current_row = connection.execute(
                        """
                        SELECT s.*, src.last_checked_at
                        FROM menu_snapshots s
                        JOIN menu_sources src ON src.source_id = s.source_id
                        WHERE s.snapshot_id = %s
                        """,
                        (locked_source["current_snapshot_id"],),
                    ).fetchone()

                if current_row is not None and current_row["content_hash"] == content_hash:
                    attempt_id = uuid4()
                    connection.execute(
                        """
                        INSERT INTO extraction_attempts(
                            attempt_id, request_id, source_id, snapshot_id, outcome,
                            reused_snapshot, diagnostics, started_at, finished_at
                        ) VALUES (%s, %s, %s, %s, 'reused', TRUE, %s, %s, %s)
                        """,
                        (
                            attempt_id,
                            request_id,
                            source_id,
                            current_row["snapshot_id"],
                            Jsonb({"content_hash": content_hash}),
                            started_at,
                            now,
                        ),
                    )
                    current_row["last_checked_at"] = now
                    result = self._row_to_snapshot(
                        current_row,
                        data_origin="stored_reuse",
                        is_stale=False,
                        refresh_status="unchanged",
                        reused_snapshot=True,
                    )
                else:
                    version_row = connection.execute(
                        """
                        SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                        FROM menu_snapshots WHERE source_id = %s
                        """,
                        (source_id,),
                    ).fetchone()
                    snapshot_id = uuid4()
                    previous_snapshot_id = (
                        current_row["snapshot_id"] if current_row is not None else None
                    )
                    version = int(version_row["next_version"])
                    connection.execute(
                        """
                        INSERT INTO menu_snapshots(
                            snapshot_id, source_id, version, previous_snapshot_id,
                            content_hash, extraction_status, validation_status,
                            extraction_method, extraction_version,
                            menu_schema_version, common_menu, fetched_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            snapshot_id,
                            source_id,
                            version,
                            previous_snapshot_id,
                            content_hash,
                            extraction_status,
                            validation_status,
                            extraction_method,
                            EXTRACTION_VERSION,
                            str(menu_data.get("schema_version") or "1.0"),
                            Jsonb(menu_data),
                            now,
                        ),
                    )
                    promote_snapshot = not (
                        extraction_status == "partial"
                        and current_row is not None
                        and current_row["extraction_status"] == "success"
                    )
                    if promote_snapshot:
                        connection.execute(
                            """
                            UPDATE menu_sources
                            SET current_snapshot_id = %s, last_checked_at = %s,
                                updated_at = NOW()
                            WHERE source_id = %s
                            """,
                            (snapshot_id, now, source_id),
                        )

                    attempt_id = uuid4()
                    connection.execute(
                        """
                        INSERT INTO extraction_attempts(
                            attempt_id, request_id, source_id, snapshot_id, outcome,
                            reused_snapshot, diagnostics, started_at, finished_at
                        ) VALUES (%s, %s, %s, %s, %s, FALSE, %s, %s, %s)
                        """,
                        (
                            attempt_id,
                            request_id,
                            source_id,
                            snapshot_id,
                            extraction_status,
                            Jsonb({"content_hash": content_hash, "promoted": promote_snapshot}),
                            started_at,
                            now,
                        ),
                    )
                    for artifact in prepared_artifacts:
                        connection.execute(
                            """
                            INSERT INTO source_artifacts(
                                artifact_id, source_id, snapshot_id, attempt_id,
                                artifact_role, content_type, content_sha256,
                                storage_kind, content_encoding, original_bytes,
                                stored_bytes, payload, safe_to_store, omission_reason
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s
                            )
                            ON CONFLICT (source_id, artifact_role, content_sha256)
                            DO NOTHING
                            """,
                            (
                                uuid4(),
                                source_id,
                                snapshot_id,
                                attempt_id,
                                artifact["role"],
                                artifact["content_type"],
                                artifact["sha256"],
                                artifact["storage_kind"],
                                artifact["content_encoding"],
                                artifact["original_bytes"],
                                artifact["stored_bytes"],
                                artifact["payload"],
                                artifact["safe_to_store"],
                                artifact["omission_reason"],
                            ),
                        )

                    if promote_snapshot:
                        served_row = connection.execute(
                            """
                            SELECT s.*, src.last_checked_at
                            FROM menu_snapshots s
                            JOIN menu_sources src ON src.source_id = s.source_id
                            WHERE s.snapshot_id = %s
                            """,
                            (snapshot_id,),
                        ).fetchone()
                        result = self._row_to_snapshot(
                            served_row,
                            data_origin="fresh_extraction",
                            is_stale=False,
                            refresh_status=extraction_status,
                            reused_snapshot=False,
                        )
                    else:
                        current_row["last_checked_at"] = now
                        result = self._row_to_snapshot(
                            current_row,
                            data_origin="stored_fallback",
                            is_stale=True,
                            refresh_status="partial_not_promoted",
                            reused_snapshot=False,
                        )
        finally:
            record_performance_event(
                component="backend",
                event="database_write",
                operation="url_menu_import",
                outcome="success" if "result" in locals() else "failure",
                duration_ms=(datetime.now(UTC) - db_started_at).total_seconds() * 1000,
                stage="storage",
                cache_status=(
                    "hit" if "result" in locals() and result.reused_snapshot else "miss"
                ),
                data_origin=(result.data_origin if "result" in locals() else None),
                measurement_method="postgres_transaction",
            )
        return result

    def _select_snapshot(self, where_sql: str, parameter: object) -> dict | None:
        started_at = datetime.now(UTC)
        try:
            with self._connection() as connection:
                row = connection.execute(
                    f"""
                    SELECT s.*, src.last_checked_at
                    FROM menu_snapshots s
                    JOIN menu_sources src ON src.source_id = s.source_id
                    WHERE {where_sql}
                    """,
                    (parameter,),
                ).fetchone()
        finally:
            record_performance_event(
                component="backend",
                event="database_read",
                operation="menu_snapshot_read",
                outcome="success" if "row" in locals() else "failure",
                duration_ms=(datetime.now(UTC) - started_at).total_seconds() * 1000,
                stage="storage",
                measurement_method="postgres_query",
            )
        return row

    def get_snapshot(self, snapshot_id: str) -> StoredMenuSnapshot | None:
        try:
            parsed_id = UUID(snapshot_id)
        except ValueError:
            return None
        row = self._select_snapshot("s.snapshot_id = %s", parsed_id)
        if row is None:
            return None
        return self._row_to_snapshot(
            row,
            data_origin="stored_snapshot",
            is_stale=False,
            refresh_status="stored",
            reused_snapshot=True,
        )

    def get_current_for_url(self, source_url: str) -> StoredMenuSnapshot | None:
        locator_key = _stable_hash({"url": canonicalise_source_url(source_url)})
        row = self._select_snapshot(
            "s.snapshot_id = (SELECT current_snapshot_id FROM menu_sources WHERE locator_key = %s)",
            locator_key,
        )
        if row is None:
            return None
        return self._row_to_snapshot(
            row,
            data_origin="stored_fallback",
            is_stale=True,
            refresh_status="refresh_failed",
            reused_snapshot=True,
        )

    def get_snapshot_item(self, snapshot_id: str, item_identifier: str) -> dict | None:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            return None
        for item in snapshot.menu_data.get("items") or []:
            identifiers = {
                str(item.get(key))
                for key in ("item_id", "product_id", "source_product_id")
                if item.get(key) is not None
            }
            if item_identifier in identifiers:
                source_product_id = item.get("source_product_id")
                if source_product_id:
                    with self._connection() as connection:
                        detail_row = connection.execute(
                            """
                            SELECT item_detail
                            FROM menu_item_details
                            WHERE snapshot_id = %s AND source_product_id = %s
                            """,
                            (UUID(snapshot_id), str(source_product_id)),
                        ).fetchone()
                    if detail_row is not None:
                        return _annotate_stored_menu(
                            {"items": [detail_row["item_detail"]]},
                            source_id=UUID(snapshot.menu_source_id),
                            snapshot_id=UUID(snapshot.snapshot_id),
                            version=snapshot.snapshot_version,
                            data_origin="stored_snapshot",
                            is_stale=False,
                            refresh_status="stored_detail",
                            last_checked_at=datetime.fromisoformat(snapshot.last_checked_at),
                        )["items"][0]
                return item
        return None

    def get_snapshot_source_context(self, snapshot_id: str) -> dict | None:
        try:
            parsed_id = UUID(snapshot_id)
        except ValueError:
            return None
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT src.source_id, src.canonical_url, src.platform,
                       s.snapshot_id, s.version
                FROM menu_snapshots s
                JOIN menu_sources src ON src.source_id = s.source_id
                WHERE s.snapshot_id = %s
                """,
                (parsed_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "menu_source_id": str(row["source_id"]),
            "snapshot_id": str(row["snapshot_id"]),
            "snapshot_version": row["version"],
            "canonical_url": row["canonical_url"],
            "platform": row["platform"],
        }

    def save_snapshot_item_detail(
        self,
        *,
        snapshot_id: str,
        item_detail: dict,
        extraction_method: str,
    ) -> dict:
        """Cache fetched detail under one immutable list snapshot."""
        from psycopg.types.json import Jsonb

        parsed_snapshot_id = UUID(snapshot_id)
        source_product_id = item_detail.get("source_product_id")
        product_id = item_detail.get("product_id") or item_detail.get("item_id")
        if not source_product_id or not product_id:
            raise ValueError("상세 저장에 필요한 상품 식별자가 없습니다.")
        retrieved_at = datetime.now(UTC)
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO menu_item_details(
                    detail_id, snapshot_id, source_product_id, product_id,
                    item_detail, extraction_method, retrieved_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_id, source_product_id) DO UPDATE SET
                    item_detail = EXCLUDED.item_detail,
                    extraction_method = EXCLUDED.extraction_method,
                    retrieved_at = EXCLUDED.retrieved_at
                RETURNING item_detail
                """,
                (
                    uuid4(),
                    parsed_snapshot_id,
                    str(source_product_id),
                    str(product_id),
                    Jsonb(item_detail),
                    extraction_method,
                    retrieved_at,
                ),
            ).fetchone()
        return row["item_detail"]

    def record_failed_attempt(
        self,
        *,
        source_url: str,
        request_id: str,
        failure_stage: str,
        error_code: str,
        started_at: datetime,
    ) -> StoredMenuSnapshot | None:
        """Record failure without replacing a current successful snapshot."""
        from psycopg.types.json import Jsonb

        locator_key = _stable_hash({"url": canonicalise_source_url(source_url)})
        finished_at = datetime.now(UTC)
        with self._connection() as connection:
            source = connection.execute(
                "SELECT source_id, current_snapshot_id FROM menu_sources WHERE locator_key = %s",
                (locator_key,),
            ).fetchone()
            source_id = source["source_id"] if source else None
            snapshot_id = source["current_snapshot_id"] if source else None
            connection.execute(
                """
                INSERT INTO extraction_attempts(
                    attempt_id, request_id, source_id, snapshot_id, outcome,
                    failure_stage, error_code, reused_snapshot, diagnostics,
                    started_at, finished_at
                ) VALUES (%s, %s, %s, %s, 'failure', %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    request_id,
                    source_id,
                    snapshot_id,
                    failure_stage,
                    error_code,
                    snapshot_id is not None,
                    Jsonb({}),
                    started_at,
                    finished_at,
                ),
            )
        return self.get_current_for_url(source_url) if snapshot_id is not None else None


def _main() -> None:
    parser = argparse.ArgumentParser(description="Menu Helper V1.1 database utility")
    parser.add_argument("command", choices=("check", "apply-schema", "versions"))
    arguments = parser.parse_args()
    store = MenuStore()
    if arguments.command == "apply-schema":
        versions = store.apply_schema()
        print({"database": "ready", "schema_versions": versions})
    elif arguments.command == "versions":
        print({"schema_versions": store.schema_versions()})
    else:
        print(store.readiness())


if __name__ == "__main__":
    _main()
