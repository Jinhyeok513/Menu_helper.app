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


if __name__ == "__main__":
    unittest.main()
