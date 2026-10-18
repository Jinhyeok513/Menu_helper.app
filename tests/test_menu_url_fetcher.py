import socket
import unittest
from dataclasses import replace
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app_config import settings
from html_menu_parser import UnsupportedMenuPageError
from menu_url_fetcher import (
    MenuPageFetchError,
    MenuURLValidationError,
    fetch_menu_html,
    import_menu_from_url,
    import_menu_item_detail_from_url,
    validate_menu_url,
)


class MenuURLValidationTest(unittest.TestCase):
    def test_rejects_non_http_scheme(self) -> None:
        with self.assertRaises(MenuURLValidationError):
            validate_menu_url("file:///etc/passwd")

    def test_rejects_credentials_in_url(self) -> None:
        with self.assertRaises(MenuURLValidationError):
            validate_menu_url("https://user:password@example.com/menu")

    def test_rejects_localhost_by_default(self) -> None:
        with self.assertRaises(MenuURLValidationError):
            validate_menu_url("http://127.0.0.1:9000/menu.html")

    def test_development_setting_can_allow_local_fixture(self) -> None:
        development_settings = replace(settings, allow_private_menu_urls=True)

        result = validate_menu_url(
            "http://127.0.0.1:9000/menu.html",
            development_settings,
        )

        self.assertEqual(result, "http://127.0.0.1:9000/menu.html")

    @patch("menu_url_fetcher.record_performance_event")
    @patch("menu_url_fetcher.build_opener")
    @patch("menu_url_fetcher.validate_menu_url")
    def test_source_timeout_has_stable_code_and_safe_log(
        self,
        validate_url,
        build_opener,
        record_event,
    ) -> None:
        validate_url.return_value = "https://example.com/private?table=secret"
        build_opener.return_value.open.side_effect = URLError(socket.timeout())

        with self.assertRaises(MenuPageFetchError) as raised:
            fetch_menu_html("https://example.com/private?table=secret")

        self.assertEqual(raised.exception.error_code, "SOURCE_TIMEOUT")
        self.assertTrue(raised.exception.is_timeout)
        event = record_event.call_args.kwargs
        self.assertEqual(event["stage"], "source_request")
        self.assertEqual(event["source_host"], "example.com")
        self.assertEqual(event["error_code"], "SOURCE_TIMEOUT")
        self.assertNotIn("url", event)

    @patch("menu_url_fetcher.record_performance_event")
    @patch("menu_url_fetcher.build_opener")
    @patch("menu_url_fetcher.validate_menu_url")
    def test_source_http_error_keeps_status_without_response_body(
        self,
        validate_url,
        build_opener,
        record_event,
    ) -> None:
        validate_url.return_value = "https://example.com/menu"
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"
        source_error = HTTPError(
            "https://example.com/menu",
            503,
            "unavailable",
            headers,
            BytesIO(b""),
        )
        build_opener.return_value.open.side_effect = source_error

        with self.assertRaises(MenuPageFetchError) as raised:
            fetch_menu_html("https://example.com/menu")

        self.assertEqual(raised.exception.error_code, "SOURCE_HTTP_ERROR")
        self.assertEqual(raised.exception.http_status, 503)
        event = record_event.call_args.kwargs
        self.assertEqual(event["http_status"], 503)
        self.assertEqual(event["content_type"], "text/html")
        self.assertEqual(event["error_code"], "SOURCE_HTTP_ERROR")
        source_error.close()

    @patch("menu_url_fetcher.record_performance_event")
    @patch("menu_url_fetcher.fetch_menu_html")
    def test_unsupported_structure_is_logged_as_extraction_failure(
        self,
        fetch_html,
        record_event,
    ) -> None:
        fetch_html.return_value = (
            "<html><script src='dynamic-app.js'></script></html>",
            "https://example.com/menu",
        )

        with self.assertRaises(UnsupportedMenuPageError) as raised:
            import_menu_from_url("https://example.com/menu")

        self.assertIn("JSON-LD MenuItem", str(raised.exception))
        extraction_event = next(
            call.kwargs
            for call in record_event.call_args_list
            if call.kwargs.get("event") == "menu_parse_transform"
        )
        self.assertEqual(extraction_event["stage"], "extraction")
        self.assertEqual(
            extraction_event["error_code"],
            "UNSUPPORTED_MENU_STRUCTURE",
        )

    @patch("menu_url_fetcher.fetch_menu_json")
    @patch("menu_url_fetcher.fetch_menu_html")
    def test_square_url_uses_public_catalog_responses(
        self,
        fetch_html,
        fetch_json,
    ) -> None:
        bootstrap = {
            "siteData": {
                "site": {"properties": {"classicSiteID": "site-1"}},
                "user": {"id": 123},
                "snapshot": {"properties": {"title": "New Cafe"}},
            },
            "storeInfo": {
                "currency": "AUD",
                "shipping_location_ids": ["location-1"],
            },
            "featureFlags": {},
        }
        import json

        html = (
            "<script>window.__BOOTSTRAP_STATE__ = "
            f"{json.dumps(bootstrap)};</script>"
        )
        fetch_html.return_value = (html, "https://new-cafe.square.site/")
        fetch_json.side_effect = [
            {
                "data": [
                    {
                        "id": "new-1",
                        "name": "New Dish",
                        "categoryIds": ["mains"],
                        "price": {"low": 12, "high": 12},
                    }
                ]
            },
            {
                "data": [
                    {
                        "id": "mains",
                        "name": "Mains",
                        "preferred_order_product_ids": ["new-1"],
                        "children": [],
                    }
                ]
            },
        ]

        result = import_menu_from_url("https://new-cafe.square.site/")

        self.assertEqual(result["restaurant"]["name"], "New Cafe")
        self.assertEqual(result["items"][0]["name_original"], "New Dish")
        self.assertEqual(
            result["provenance"]["extraction_method"],
            "square_bootstrap_storefront_api",
        )
        self.assertEqual(fetch_json.call_count, 2)

    @patch("menu_url_fetcher.fetch_menu_json")
    @patch("menu_url_fetcher.fetch_menu_html")
    def test_square_detail_uses_same_url_and_product_id(
        self,
        fetch_html,
        fetch_json,
    ) -> None:
        bootstrap = {
            "siteData": {
                "site": {"properties": {"classicSiteID": "site-1"}},
                "user": {"id": 123},
                "snapshot": {"properties": {"title": "New Cafe"}},
            },
            "storeInfo": {
                "currency": "AUD",
                "shipping_location_ids": ["location-1"],
            },
            "featureFlags": {},
        }
        import json

        fetch_html.return_value = (
            "<script>window.__BOOTSTRAP_STATE__ = "
            f"{json.dumps(bootstrap)};</script>",
            "https://new-cafe.square.site/",
        )
        fetch_json.side_effect = [
            {
                "data": {
                    "id": "new-1",
                    "name": "New Dish",
                    "price": {"low": 12, "high": 14},
                    "modifiers": {"data": []},
                    "images": {"data": []},
                }
            },
            {
                "data": [
                    {"id": "small", "name": "Small", "price": {"current": 12}},
                    {"id": "large", "name": "Large", "price": {"current": 14}},
                ]
            },
        ]

        item = import_menu_item_detail_from_url(
            "https://new-cafe.square.site/",
            "new-1",
        )

        self.assertEqual(item["source_product_id"], "new-1")
        self.assertEqual(item["variant_status"], "available")
        self.assertEqual(fetch_json.call_count, 2)

    @patch("menu_url_fetcher.fetch_menu_json")
    @patch("menu_url_fetcher.fetch_menu_html")
    def test_sku_failure_preserves_product_options(
        self,
        fetch_html,
        fetch_json,
    ) -> None:
        bootstrap = {
            "siteData": {
                "site": {"properties": {"classicSiteID": "site-1"}},
                "user": {"id": 123},
                "snapshot": {"properties": {"title": "New Cafe"}},
            },
            "storeInfo": {
                "currency": "AUD",
                "shipping_location_ids": ["location-1"],
            },
            "featureFlags": {},
        }
        import json

        fetch_html.return_value = (
            "<script>window.__BOOTSTRAP_STATE__ = "
            f"{json.dumps(bootstrap)};</script>",
            "https://new-cafe.square.site/",
        )
        fetch_json.side_effect = [
            {
                "data": {
                    "id": "new-1",
                    "name": "New Dish",
                    "modifiers": {
                        "data": [
                            {
                                "id": "extras",
                                "name": "Extras",
                                "min_selected": 0,
                                "max_selected": 0,
                                "choices": [{"id": "chilli", "name": "Chilli", "price": 0}],
                            }
                        ]
                    },
                    "images": {"data": []},
                }
            },
            MenuPageFetchError("SKU request failed"),
        ]

        item = import_menu_item_detail_from_url(
            "https://new-cafe.square.site/",
            "new-1",
        )

        self.assertEqual(item["option_status"], "available")
        self.assertEqual(item["variant_status"], "fetch_failed")


if __name__ == "__main__":
    unittest.main()
