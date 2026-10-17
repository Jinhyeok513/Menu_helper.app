import unittest
from dataclasses import replace
from unittest.mock import patch

from app_config import settings
from menu_url_fetcher import (
    MenuPageFetchError,
    MenuURLValidationError,
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
