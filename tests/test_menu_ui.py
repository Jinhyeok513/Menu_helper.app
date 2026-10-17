import copy
import unittest

from menu_ui import create_menu_ui_data


class MenuUIDataTest(unittest.TestCase):
    def test_empty_menu_keeps_food_and_beverage_tabs(self) -> None:
        menu_data = {"restaurant": {"name": "Empty Cafe"}, "items": []}

        result = create_menu_ui_data(menu_data)

        self.assertEqual(result["total_items"], 0)
        self.assertEqual([tab["tab_id"] for tab in result["tabs"]], ["food", "beverage"])
        self.assertEqual([tab["item_count"] for tab in result["tabs"]], [0, 0])

    def test_conversion_does_not_change_original_data(self) -> None:
        menu_data = {
            "restaurant": {"name": "Test Cafe"},
            "items": [
                {
                    "item_id": "food_1",
                    "item_type": "food",
                    "category_original": "Breakfast",
                    "category_ko": "아침 메뉴",
                    "name_original": "Toast",
                    "name_ko": "토스트",
                    "options": [],
                }
            ],
        }
        original = copy.deepcopy(menu_data)

        create_menu_ui_data(menu_data)

        self.assertEqual(menu_data, original)

    def test_unknown_item_type_is_not_silently_removed(self) -> None:
        menu_data = {
            "items": [
                {
                    "item_id": "unknown_1",
                    "item_type": "merchandise",
                    "category_original": "Goods",
                    "name_original": "Mug",
                }
            ]
        }

        with self.assertRaises(ValueError):
            create_menu_ui_data(menu_data)

    def test_source_counts_and_price_range_are_preserved(self) -> None:
        menu_data = {
            "provenance": {
                "unique_product_count": 1,
                "category_listing_count": 2,
            },
            "items": [
                {
                    "item_id": "food_1",
                    "item_type": "food",
                    "category_original": "Mains",
                    "name_original": "Noodle Soup",
                    "price_aud": 17.8,
                    "price_max_aud": 19.8,
                }
            ],
        }

        result = create_menu_ui_data(menu_data)

        self.assertEqual(result["source"]["unique_product_count"], 1)
        self.assertEqual(result["source"]["category_listing_count"], 2)
        item = result["tabs"][0]["categories"][0]["items"][0]
        self.assertEqual(item["price_aud"], 17.8)
        self.assertEqual(item["price_max_aud"], 19.8)
        self.assertEqual(item["option_status"], "not_checked")
        self.assertFalse(item["has_options"])
        self.assertEqual(item["restaurant_id"], "restaurant_unknown")
        self.assertIn("description_original", item)

    def test_option_summary_keeps_detail_link_identifiers(self) -> None:
        menu_data = {
            "items": [
                {
                    "item_id": "square_category_product",
                    "product_id": "square_site_product",
                    "source_product_id": "product",
                    "item_type": "food",
                    "category_original": "Mains",
                    "name_original": "Noodle Soup",
                    "option_status": "available",
                    "options": [
                        {
                            "group_id": "add-ons",
                            "choices": [{"choice_id": "chilli"}, {"choice_id": "onion"}],
                        }
                    ],
                    "image_url": "https://images.example/noodle.jpg",
                    "images": [{"url_original": "https://images.example/noodle.jpg"}],
                    "image_status": "available",
                }
            ]
        }

        result = create_menu_ui_data(menu_data)
        item = result["tabs"][0]["categories"][0]["items"][0]

        self.assertEqual(item["product_id"], "square_site_product")
        self.assertEqual(item["source_product_id"], "product")
        self.assertTrue(item["has_options"])
        self.assertEqual(item["option_group_count"], 1)
        self.assertEqual(item["option_choice_count"], 2)
        self.assertEqual(item["image_count"], 1)


if __name__ == "__main__":
    unittest.main()
