"""Insert and re-read non-destructive V1.1 PostgreSQL verification snapshots.

The script is called manually after ``v1_1_schema.sql`` is applied. It uses a
reserved example.invalid source, stores an initial menu, verifies deduplication,
then stores a price change as a new version. It never deletes existing rows and
prints IDs/status only, never DATABASE_URL or menu payloads.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from performance_metrics import bind_request_id, reset_request_id
from v1_1_menu_store import MenuStore


def _menu(price: int) -> dict:
    return {
        "schema_version": "1.1",
        "dataset_status": "verification_fixture",
        "restaurant": {
            "restaurant_id": "v1_1_db_verification_store",
            "name": "V1.1 Database Verification",
        },
        "provenance": {
            "source_url": "https://example.invalid/menu-helper-v1-1-verification",
            "extraction_method": "verification_fixture",
        },
        "items": [
            {
                "item_id": "verification_tea",
                "product_id": "verification_tea",
                "source_product_id": "verification_tea",
                "restaurant_id": "v1_1_db_verification_store",
                "source_id": "verification_fixture",
                "item_type": "beverage",
                "category_original": "Verification",
                "name_original": "Verification Tea",
                "price_amount": price,
                "price_aud": price,
                "currency": "AUD",
                "options": [],
                "option_status": "not_checked",
                "variants": [],
                "variant_status": "not_checked",
            }
        ],
    }


def main() -> None:
    store = MenuStore()
    request_id = "v1-1-database-verification"
    token = bind_request_id(request_id)
    try:
        first = store.save_menu_snapshot(
            menu_data=_menu(5),
            source_url="https://example.invalid/menu-helper-v1-1-verification",
            artifacts=[
                {
                    "role": "verification_json_redaction_v2",
                    "content_type": "application/json",
                    "body": {"verification": True, "token": "must-not-be-stored"},
                }
            ],
            request_id=request_id,
            extraction_status="success",
            validation_status="passed",
        )
        duplicate = store.save_menu_snapshot(
            menu_data=_menu(5),
            source_url="https://example.invalid/menu-helper-v1-1-verification",
            artifacts=[],
            request_id=request_id,
            extraction_status="success",
            validation_status="passed",
        )
        changed = store.save_menu_snapshot(
            menu_data=_menu(6),
            source_url="https://example.invalid/menu-helper-v1-1-verification",
            artifacts=[],
            request_id=request_id,
            extraction_status="success",
            validation_status="passed",
        )
        def save_concurrent() -> object:
            return store.save_menu_snapshot(
                menu_data=_menu(7),
                source_url="https://example.invalid/menu-helper-v1-1-verification",
                artifacts=[],
                request_id=request_id,
                extraction_status="success",
                validation_status="passed",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_results = list(executor.map(lambda _: save_concurrent(), range(2)))
        partial_menu = _menu(8)
        partial_menu["items"][0]["currency"] = None
        partial = store.save_menu_snapshot(
            menu_data=partial_menu,
            source_url="https://example.invalid/menu-helper-v1-1-verification",
            artifacts=[],
            request_id=request_id,
            extraction_status="partial",
            validation_status="needs_review",
        )
        fallback = store.record_failed_attempt(
            source_url="https://example.invalid/menu-helper-v1-1-verification",
            request_id=request_id,
            failure_stage="source_request",
            error_code="VERIFICATION_SOURCE_FAILURE",
            started_at=datetime.now(UTC),
        )
        item = store.get_snapshot_item(changed.snapshot_id, "verification_tea")
        if item is None:
            raise RuntimeError("저장한 검증 메뉴를 다시 읽지 못했습니다.")
        print(
            {
                "first_version": first.snapshot_version,
                "duplicate_reused": duplicate.reused_snapshot,
                "changed_version": changed.snapshot_version,
                "detail_snapshot_matches": item.get("snapshot_id") == changed.snapshot_id,
                "concurrent_snapshot_matches": (
                    concurrent_results[0].snapshot_id == concurrent_results[1].snapshot_id
                ),
                "partial_did_not_replace_success": (
                    partial.snapshot_id == concurrent_results[0].snapshot_id
                    and partial.refresh_status == "partial_not_promoted"
                ),
                "failure_preserved_current": (
                    fallback is not None
                    and fallback.snapshot_id == concurrent_results[0].snapshot_id
                ),
            }
        )
    finally:
        reset_request_id(token)


if __name__ == "__main__":
    main()
