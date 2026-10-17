import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm import (
    MenuSelectionError,
    explanation_generation_metadata,
    generate_menu_explanation,
    generate_menu_one_line_description,
    validate_menu_selection,
)


class MenuSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.menu_item = {
            "item_id": "menu-1",
            "source_id": "test-source",
            "product_id": "product-1",
            "variants": [
                {"variant_id": "regular", "name_original": "Regular", "sold_out": False, "price_aud": 16.8, "price_kind": "full_product_price"},
                {"variant_id": "large", "name_original": "Large", "sold_out": False, "price_aud": 18.8, "price_kind": "full_product_price"},
            ],
            "options": [
                {
                    "group_id": "noodle-choice",
                    "name_original": "Noodles Choice",
                    "min_selected": 1,
                    "max_selected": 1,
                    "choices": [
                        {"choice_id": "dry", "name_original": "Dry", "sold_out": False, "hidden": False, "price_delta_aud": 0, "price_status": "confirmed"},
                        {"choice_id": "soup", "name_original": "With Soup", "sold_out": False, "hidden": False, "price_delta_aud": 0, "price_status": "confirmed"},
                    ],
                }
            ],
        }

    def test_returns_only_confirmed_selection_facts(self) -> None:
        result = validate_menu_selection(
            self.menu_item,
            {"variant_id": "regular", "choice_ids": ["soup"]},
        )

        self.assertEqual(result["variant"]["name"], "Regular")
        self.assertEqual(result["choices"][0]["choice_name"], "With Soup")

    def test_rejects_missing_required_choice(self) -> None:
        with self.assertRaises(MenuSelectionError):
            validate_menu_selection(
                self.menu_item,
                {"variant_id": "regular", "choice_ids": []},
            )

    def test_rejects_choice_from_another_product(self) -> None:
        with self.assertRaises(MenuSelectionError):
            validate_menu_selection(
                self.menu_item,
                {"variant_id": "regular", "choice_ids": ["other-product"]},
            )

    @staticmethod
    def _fake_client(response_data: dict) -> SimpleNamespace:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(response_data))
                )
            ]
        )
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: response)
            )
        )

    def test_detail_description_does_not_require_options_before_selection(self) -> None:
        response_data = {
            "one_line_description_ko": "부드러운 맛을 기대할 수 있어요.",
            "detailed_description_ko": "메뉴 정보가 적어 일반적인 특징만 설명해요.",
            "restaurant_facts_ko": [],
            "general_food_knowledge_ko": [],
            "inferences_ko": ["부드러울 수 있어요."],
            "unverified_information_ko": ["구체적인 재료는 미확인입니다."],
            "option_descriptions_ko": [],
            "combination_description_ko": None,
        }
        with patch("llm._require_api_key", return_value="hidden"), patch(
            "llm._create_client", return_value=self._fake_client(response_data)
        ):
            result = generate_menu_explanation(self.menu_item)

        self.assertIsNone(result["combination_description_ko"])
        self.assertEqual(result["selected_choice_ids"], [])

    def test_one_line_description_keeps_source_identity(self) -> None:
        response_data = {
            "one_line_description_ko": "진한 향이 느껴질 수 있는 메뉴예요.",
            "restaurant_facts_ko": [],
            "general_food_knowledge_ko": [],
            "inferences_ko": ["진한 향이 날 수 있어요."],
            "unverified_information_ko": [],
        }
        with patch("llm._require_api_key", return_value="hidden"), patch(
            "llm._create_client", return_value=self._fake_client(response_data)
        ):
            result = generate_menu_one_line_description(self.menu_item)

        self.assertEqual(result["product_id"], "product-1")

    def test_combination_ids_come_from_validated_server_data(self) -> None:
        response_data = {
            "one_line_description_ko": "진한 국물 맛을 기대할 수 있어요.",
            "detailed_description_ko": "쌀국수와 국물을 함께 즐기는 메뉴예요.",
            "restaurant_facts_ko": [],
            "general_food_knowledge_ko": [],
            "inferences_ko": ["진한 맛일 수 있어요."],
            "unverified_information_ko": [],
            "option_descriptions_ko": [
                {
                    "description_ko": "국물과 함께 촉촉하게 즐길 수 있어요.",
                    "basis": "general_food_knowledge",
                }
            ],
            "combination_description_ko": "Regular 크기에 국물을 함께 고른 조합이에요.",
        }
        with patch("llm._require_api_key", return_value="hidden"), patch(
            "llm._create_client", return_value=self._fake_client(response_data)
        ):
            result = generate_menu_explanation(
                self.menu_item,
                {"variant_id": "regular", "choice_ids": ["soup"]},
                include_combination=True,
            )

        self.assertEqual(result["item_id"], "menu-1")
        self.assertEqual(result["selected_variant_id"], "regular")
        self.assertEqual(result["selected_choice_ids"], ["soup"])
        self.assertEqual(
            result["option_descriptions_ko"][0]["choice_id"],
            "soup",
        )

    def test_generation_metadata_separates_description_kinds(self) -> None:
        one_line = explanation_generation_metadata("one_line")
        detail = explanation_generation_metadata("detail")

        self.assertNotEqual(one_line["prompt_version"], detail["prompt_version"])
        self.assertEqual(one_line["language"], "ko")


if __name__ == "__main__":
    unittest.main()
