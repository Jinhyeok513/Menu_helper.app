import unittest

from menu_ui import create_menu_detail


class MenuDetailTest(unittest.TestCase):
    def test_normalises_legacy_option_without_guessing_price(self) -> None:
        detail = create_menu_detail(
            {
                "item_id": "roll-1",
                "restaurant_id": "cafe-1",
                "name_original": "Bacon Egg Roll",
                "currency": "AUD",
                "options": [
                    {
                        "group": "sauce",
                        "choices": ["BBQ sauce", "tomato sauce"],
                        "selection_count": 1,
                        "additional_price_aud": None,
                    }
                ],
                "image_url": None,
            }
        )

        group = detail["options"][0]
        self.assertEqual(detail["option_status"], "available")
        self.assertTrue(group["required"])
        self.assertEqual(group["max_selected"], 1)
        self.assertEqual(group["choices"][0]["price_status"], "unknown")
        self.assertIsNone(group["choices"][0]["price_delta_aud"])

    def test_empty_legacy_options_remain_not_checked(self) -> None:
        detail = create_menu_detail(
            {
                "item_id": "coffee-1",
                "restaurant_id": "cafe-1",
                "name_original": "Coffee",
                "options": [],
            }
        )

        self.assertEqual(detail["option_status"], "not_checked")
        self.assertEqual(detail["options"], [])


if __name__ == "__main__":
    unittest.main()
