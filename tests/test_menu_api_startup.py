import os
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

from fastapi.testclient import TestClient

from connect_api_llm import app
from html_menu_parser import UnsupportedMenuPageError
from menu_url_fetcher import MenuPageFetchError
from performance_metrics import read_performance_events, record_performance_event
from v1_1_menu_store import MenuDatabaseNotConfiguredError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MenuAPIStartupTest(unittest.TestCase):
    def _extraction(self, menu_data: dict) -> SimpleNamespace:
        return SimpleNamespace(
            menu_data=menu_data,
            artifacts=[],
            extraction_status="success",
            validation_status="passed",
            started_at=datetime.now(UTC),
        )

    def _stored(self, menu_data: dict) -> SimpleNamespace:
        return SimpleNamespace(menu_data=menu_data)

    def _assert_server_imports(self, menu_json_path: str, expected_status: str) -> None:
        environment = os.environ.copy()
        environment["MENU_JSON_PATH"] = menu_json_path
        check_code = (
            "from fastapi.testclient import TestClient; "
            "from connect_api_llm import app; "
            "response = TestClient(app).get('/menus'); "
            "body = response.json(); "
            "assert response.status_code == 200, response.text; "
            "assert body['total_items'] == 0, body; "
            f"assert body['source']['dataset_status'] == {expected_status!r}, body"
        )
        completed = subprocess.run(
            [sys.executable, "-c", check_code],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_server_imports_without_stored_json_configuration(self) -> None:
        self._assert_server_imports("", "not_configured")

    def test_server_imports_when_configured_json_is_missing(self) -> None:
        self._assert_server_imports(
            "/tmp/menu-helper-missing-menu.json",
            "configured_file_missing",
        )

    def test_request_id_is_returned_on_success(self) -> None:
        response = TestClient(app).get(
            "/health",
            headers={"X-Request-ID": "mobile-diagnostic-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "mobile-diagnostic-1")

    def test_mobile_metric_accepts_database_storage_failure_stage(self) -> None:
        response = TestClient(app).post(
            "/performance/mobile-events",
            json={
                "request_id": "mobile-storage-failure-1",
                "event": "operation_failed",
                "operation": "url_menu_import",
                "duration_ms": 12.5,
                "outcome": "failure",
                "cache_status": "not_applicable",
                "attempt": 1,
                "retry_count": 0,
                "retry_limit": 0,
                "timeout": False,
                "rate_limited": False,
                "failure_stage": "storage",
                "measurement_method": "promise_rejected",
            },
        )

        self.assertEqual(response.status_code, 202)

    @patch("menu_api.menu_store")
    def test_readiness_is_separate_from_process_health(self, store) -> None:
        store.readiness.return_value = {
            "ready": False,
            "database": "not_configured",
            "schema_version": None,
        }
        client = TestClient(app)

        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/ready").status_code, 503)

    @patch("menu_api.menu_store")
    def test_url_import_reports_missing_database_before_fetch(self, store) -> None:
        store.require_ready.side_effect = MenuDatabaseNotConfiguredError("missing")

        response = TestClient(app).post(
            "/menu-sources/url",
            json={"url": "https://example.com/menu"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.headers["X-Menu-Error-Code"],
            "MENU_DATABASE_NOT_CONFIGURED",
        )
        self.assertEqual(response.headers["X-Menu-Failure-Stage"], "storage")

    @patch("menu_api.menu_store")
    def test_snapshot_detail_uses_stored_item_identifiers(self, store) -> None:
        store.get_snapshot_item.return_value = {
            "item_id": "listing-1",
            "product_id": "product-1",
            "source_product_id": "source-1",
            "restaurant_id": "restaurant-1",
            "name_original": "Stored Soup",
            "price_amount": 12,
            "price_aud": 12,
            "currency": "AUD",
            "options": [],
            "option_status": "not_checked",
            "snapshot_id": "snapshot-1",
            "snapshot_version": 1,
        }

        response = TestClient(app).get(
            "/menu-snapshots/snapshot-1/items/product-1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product_id"], "product-1")
        self.assertEqual(response.json()["snapshot_id"], "snapshot-1")

    @patch("menu_api.import_menu_item_detail_from_url")
    @patch("menu_api.menu_store")
    def test_square_snapshot_detail_is_fetched_and_saved_once(
        self,
        store,
        import_detail,
    ) -> None:
        stored_list_item = {
            "item_id": "listing-1",
            "product_id": "product-1",
            "source_product_id": "source-1",
            "restaurant_id": "restaurant-1",
            "source_id": "square_storefront_api",
            "name_original": "Rare Beef Noodle Soup",
            "price_amount": 18,
            "currency": "AUD",
            "options": [],
            "option_status": "not_checked",
            "variants": [],
            "variant_status": "not_checked",
            "snapshot_id": "snapshot-1",
            "snapshot_version": 1,
        }
        store.get_snapshot_item.return_value = stored_list_item
        store.get_snapshot_source_context.return_value = {
            "menu_source_id": "source-row-1",
            "snapshot_id": "snapshot-1",
            "snapshot_version": 1,
            "canonical_url": "https://fixture.square.site/",
            "platform": "square",
        }
        import_detail.return_value = {
            **stored_list_item,
            "variants": [
                {
                    "variant_id": "variant-1",
                    "name_original": "Regular",
                    "price_amount": 18,
                    "currency": "AUD",
                }
            ],
            "variant_status": "available",
        }

        response = TestClient(app).get(
            "/menu-snapshots/snapshot-1/items/product-1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["variant_status"], "available")
        import_detail.assert_called_once_with(
            "https://fixture.square.site/",
            "source-1",
            operation="snapshot_item_detail",
        )
        store.save_snapshot_item_detail.assert_called_once()

    @patch("menu_api.import_menu_item_detail_from_url")
    @patch("menu_api.menu_store")
    def test_stored_square_detail_does_not_refetch(
        self,
        store,
        import_detail,
    ) -> None:
        store.get_snapshot_item.return_value = {
            "item_id": "listing-1",
            "product_id": "product-1",
            "source_product_id": "source-1",
            "restaurant_id": "restaurant-1",
            "source_id": "square_storefront_api",
            "name_original": "Rare Beef Noodle Soup",
            "price_amount": 18,
            "currency": "AUD",
            "options": [],
            "option_status": "checked_none",
            "variants": [],
            "variant_status": "checked_none",
            "snapshot_id": "snapshot-1",
            "snapshot_version": 1,
        }

        response = TestClient(app).get(
            "/menu-snapshots/snapshot-1/items/product-1"
        )

        self.assertEqual(response.status_code, 200)
        import_detail.assert_not_called()
        store.get_snapshot_source_context.assert_not_called()

    @patch("menu_api.menu_store")
    @patch("menu_api.extract_menu_snapshot")
    def test_supported_url_returns_common_menu_response(self, extract_menu, store) -> None:
        menu_data = {
            "restaurant": {"restaurant_id": "fixture-1", "name": "Fixture Cafe"},
            "items": [],
            "dataset_status": "fixture",
            "provenance": {
                "source_url": "https://example.com/menu",
                "extraction_method": "json_ld",
            },
        }
        extract_menu.return_value = self._extraction(menu_data)
        store.save_menu_snapshot.return_value = self._stored(menu_data)

        response = TestClient(app).post(
            "/menu-sources/url",
            headers={"X-Request-ID": "mobile-success-1"},
            json={"url": "https://example.com/menu"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["menu"]["total_items"], 0)
        self.assertEqual(response.headers["X-Request-ID"], "mobile-success-1")

    @patch("menu_api.menu_store")
    @patch("menu_api.extract_menu_snapshot")
    def test_unsupported_structure_keeps_detail_and_adds_diagnostics(
        self,
        extract_menu,
        store,
    ) -> None:
        detail = "지원하는 메뉴 구조를 찾지 못했습니다."
        extract_menu.side_effect = UnsupportedMenuPageError(detail)
        store.record_failed_attempt.return_value = None

        response = TestClient(app).post(
            "/menu-sources/url",
            headers={"X-Request-ID": "mobile-unsupported-1"},
            json={"url": "https://example.com/dynamic-menu"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], detail)
        self.assertEqual(
            response.headers["X-Menu-Error-Code"],
            "UNSUPPORTED_MENU_STRUCTURE",
        )
        self.assertEqual(response.headers["X-Menu-Failure-Stage"], "extraction")
        self.assertEqual(response.headers["X-Request-ID"], "mobile-unsupported-1")

    @patch("menu_api.menu_store")
    @patch("menu_api.extract_menu_snapshot")
    def test_source_timeout_and_http_error_are_distinct(self, extract_menu, store) -> None:
        cases = (
            ("SOURCE_TIMEOUT", None),
            ("SOURCE_HTTP_ERROR", 503),
        )
        client = TestClient(app)
        for error_code, source_status in cases:
            with self.subTest(error_code=error_code):
                extract_menu.side_effect = MenuPageFetchError(
                    "원본 메뉴 요청 실패",
                    error_code=error_code,
                    http_status=source_status,
                    is_timeout=error_code == "SOURCE_TIMEOUT",
                )
                store.record_failed_attempt.return_value = None
                response = client.post(
                    "/menu-sources/url",
                    json={"url": "https://example.com/menu"},
                )
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.headers["X-Menu-Error-Code"], error_code)
                self.assertEqual(
                    response.headers["X-Menu-Failure-Stage"],
                    "source_request",
                )

    @patch("menu_api.menu_store")
    @patch("menu_api.extract_menu_snapshot")
    def test_common_data_conversion_failure_is_distinct(self, extract_menu, store) -> None:
        menu_data = {
            "restaurant": {"name": "Broken fixture"},
            "items": [{"item_type": "merchandise"}],
            "provenance": {},
        }
        extract_menu.return_value = self._extraction(menu_data)
        store.save_menu_snapshot.return_value = self._stored(menu_data)

        response = TestClient(app).post(
            "/menu-sources/url",
            json={"url": "https://example.com/menu"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.headers["X-Menu-Error-Code"],
            "MENU_TRANSFORM_FAILED",
        )
        self.assertEqual(
            response.headers["X-Menu-Failure-Stage"],
            "transformation",
        )

    @patch("menu_api.menu_store")
    @patch("menu_api.extract_menu_snapshot")
    def test_request_id_connects_safe_failure_logs(self, extract_menu, store) -> None:
        extract_menu.side_effect = UnsupportedMenuPageError("unsupported")
        store.record_failed_attempt.return_value = None
        with TemporaryDirectory() as directory:
            log_path = Path(directory) / "diagnostics.jsonl"

            def write_event(**event):
                return record_performance_event(
                    **event,
                    enabled=True,
                    log_path=log_path,
                )

            with patch("menu_api.record_performance_event", side_effect=write_event):
                response = TestClient(app).post(
                    "/menu-sources/url",
                    headers={"X-Request-ID": "mobile-log-link-1"},
                    json={"url": "https://example.com/menu?session=private"},
                )

            events, errors = read_performance_events([log_path])
            self.assertEqual(response.status_code, 422)
            self.assertFalse(errors)
            self.assertTrue(events)
            self.assertTrue(
                all(event["request_id"] == "mobile-log-link-1" for event in events)
            )
            raw_log = log_path.read_text(encoding="utf-8")
            self.assertNotIn("session=private", raw_log)
            self.assertNotIn("example.com/menu", raw_log)


if __name__ == "__main__":
    unittest.main()
