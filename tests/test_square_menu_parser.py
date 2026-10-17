import json
import unittest

from square_menu_parser import (
    build_square_catalog_urls,
    build_square_product_detail_urls,
    extract_square_storefront_info,
    parse_square_catalog,
    parse_square_product_detail,
)


class SquareMenuParserTest(unittest.TestCase):
    def setUp(self) -> None:
        bootstrap = {
            "siteData": {
                "site": {"properties": {"classicSiteID": "site-1"}},
                "user": {"id": 123},
                "snapshot": {"properties": {"title": "Square Test Cafe"}},
            },
            "storeInfo": {
                "currency": "AUD",
                "shipping_location_ids": ["location-1"],
            },
            "featureFlags": {
                "ecom.square-online-published-catalog-cache-version": "2026-03-25"
            },
        }
        self.html = (
            "<html><script type='application/javascript'>"
            "window.__BOOTSTRAP_STATE__ = "
            f"{json.dumps(bootstrap)};"
            "</script></html>"
        )

    def test_extracts_square_bootstrap_and_builds_public_api_urls(self) -> None:
        info = extract_square_storefront_info(self.html)

        self.assertEqual(info["restaurant_name"], "Square Test Cafe")
        self.assertEqual(info["currency"], "AUD")
        product_url, category_url = build_square_catalog_urls(info)
        self.assertIn("cdn5.editmysite.com", product_url)
        self.assertIn("site-1/store-locations/location-1/products", product_url)
        self.assertIn("site-1/store-locations/location-1/categories", category_url)
        self.assertIn("modifiers", product_url)

        detail_url, sku_url = build_square_product_detail_urls(info, "food/1")
        self.assertIn("products/food%2F1?", detail_url)
        self.assertIn("products/food%2F1/skus?", sku_url)

    def test_preserves_category_and_product_order_and_price_range(self) -> None:
        info = extract_square_storefront_info(self.html)
        product_document = {
            "data": [
                {
                    "id": "drink-2",
                    "name": "Iced Tea",
                    "categoryIds": ["drinks"],
                    "price": {"low": 6, "high": 6},
                    "thumbnail": {
                        "data": {
                            "id": "tea-thumbnail",
                            "absolute_url": "https://images.example/tea.jpg",
                        }
                    },
                },
                {
                    "id": "food-1",
                    "name": "Noodle Soup",
                    "categoryIds": ["mains"],
                    "price": {"low": 17.8, "high": 19.8},
                    "modifiers": {
                        "data": [
                            {
                                "id": "choice-group",
                                "name": "Noodle Choices",
                                "type": "choice",
                                "display_order": 1,
                                "min_selected": 1,
                                "max_selected": 1,
                                "allow_quantities": False,
                                "choices": [
                                    {
                                        "id": "with-soup",
                                        "display_name": "With Soup",
                                        "display_order": 2,
                                        "price": 0,
                                    },
                                    {
                                        "id": "dry",
                                        "display_name": "Dry",
                                        "display_order": 1,
                                        "price": 0,
                                    },
                                ],
                            }
                        ]
                    },
                    "images": {
                        "data": [
                            {
                                "id": "image-1",
                                "absolute_url": "https://images.example/noodle.jpg",
                                "urls": {
                                    "320": "https://images.example/noodle-320.jpg",
                                    "1280": "https://images.example/noodle-1280.jpg",
                                },
                            },
                            {"id": "broken-image-without-url"},
                        ]
                    },
                },
                {
                    "id": "drink-1",
                    "name": "Coffee",
                    "categoryIds": ["drinks"],
                    "price": {"low": 5, "high": 5},
                },
            ]
        }
        category_document = {
            "data": [
                {
                    "id": "root",
                    "name": "Menu",
                    "children": [
                        {
                            "id": "mains",
                            "name": "Mains",
                            "preferred_order_product_ids": ["food-1"],
                            "children": [],
                        },
                        {
                            "id": "drinks",
                            "name": "Drinks",
                            "preferred_order_product_ids": [
                                "drink-1",
                                "drink-2",
                            ],
                            "children": [],
                        },
                    ],
                }
            ]
        }

        result = parse_square_catalog(
            product_document,
            category_document,
            "https://test.square.site/menu",
            info,
        )

        self.assertEqual(result["restaurant"]["name"], "Square Test Cafe")
        self.assertEqual(result["counts"], {
            "food": 1,
            "beverage": 2,
            "total": 3,
            "unique_products": 3,
        })
        self.assertEqual(
            [item["name_original"] for item in result["items"]],
            ["Noodle Soup", "Coffee", "Iced Tea"],
        )
        self.assertEqual(result["items"][0]["price_aud"], 17.8)
        self.assertEqual(result["items"][0]["price_max_aud"], 19.8)
        first_item = result["items"][0]
        self.assertEqual(first_item["source_product_id"], "food-1")
        self.assertEqual(first_item["option_status"], "available")
        self.assertEqual(
            [choice["name_original"] for choice in first_item["options"][0]["choices"]],
            ["Dry", "With Soup"],
        )
        self.assertTrue(first_item["options"][0]["required"])
        self.assertEqual(first_item["options"][0]["selection_type"], "single")
        self.assertEqual(first_item["image_status"], "partial")
        self.assertEqual(
            first_item["images"][0]["thumbnail_url"],
            "https://images.example/noodle-320.jpg",
        )
        self.assertEqual(result["items"][1]["option_status"], "not_checked")
        self.assertEqual(result["items"][2]["image_status"], "available")
        self.assertEqual(
            result["items"][2]["image_url"],
            "https://images.example/tea.jpg",
        )

    def test_product_detail_keeps_variants_as_full_prices(self) -> None:
        info = extract_square_storefront_info(self.html)
        product_document = {
            "data": {
                "id": "pho-1",
                "name": "Rare Beef Noodle Soup",
                "price": {"low": 16.8, "high": 18.8},
                "category": {"data": {"id": "pho", "name": "Pho"}},
                "modifiers": {"data": []},
                "images": {"data": []},
            }
        }
        sku_document = {
            "data": [
                {"id": "regular", "name": "Regular", "display_order": 1, "price": {"current": 16.8}},
                {"id": "large", "name": "Large", "display_order": 2, "price": {"current": 18.8}},
            ]
        }

        item = parse_square_product_detail(
            product_document,
            sku_document,
            "https://test.square.site/",
            info,
        )

        self.assertEqual(item["variant_status"], "available")
        self.assertEqual([variant["name_original"] for variant in item["variants"]], ["Regular", "Large"])
        self.assertTrue(all(variant["price_kind"] == "full_product_price" for variant in item["variants"]))
        self.assertTrue(all(variant["selected_by_default"] is None for variant in item["variants"]))
        self.assertEqual(item["variant_selection"]["selection_type"], "single")
        self.assertIsNone(item["variant_selection"]["required"])
        self.assertEqual(item["variant_selection"]["constraint_status"], "not_provided")

    def test_same_product_in_two_categories_keeps_shared_detail_data(self) -> None:
        info = extract_square_storefront_info(self.html)
        product_document = {
            "data": [
                {
                    "id": "shared-1",
                    "name": "Shared Dish",
                    "categoryIds": ["featured", "mains"],
                    "modifiers": {"data": []},
                    "images": {
                        "data": [
                            {"id": "image-1", "absolute_url": "https://images.example/shared.jpg"}
                        ]
                    },
                }
            ]
        }
        category_document = {
            "data": [
                {"id": "featured", "name": "Featured", "preferred_order_product_ids": ["shared-1"]},
                {"id": "mains", "name": "Mains", "preferred_order_product_ids": ["shared-1"]},
            ]
        }

        result = parse_square_catalog(
            product_document,
            category_document,
            "https://test.square.site/",
            info,
        )

        first, second = result["items"]
        self.assertNotEqual(first["item_id"], second["item_id"])
        self.assertEqual(first["product_id"], second["product_id"])
        self.assertEqual(first["images"], second["images"])
        self.assertEqual(first["options"], second["options"])


if __name__ == "__main__":
    unittest.main()
