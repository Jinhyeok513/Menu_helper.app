import base64
import unittest
from unittest.mock import patch

from menu_image_parser import build_menu_data_from_ocr, validate_image_data_url


class MenuImageParserTest(unittest.TestCase):
    def test_validates_image_data_url(self) -> None:
        encoded = base64.b64encode(b"small-image").decode("ascii")

        media_type, image_bytes = validate_image_data_url(
            f"data:image/jpeg;base64,{encoded}"
        )

        self.assertEqual(media_type, "image/jpeg")
        self.assertEqual(image_bytes, b"small-image")

    def test_rejects_unsupported_media_type(self) -> None:
        with self.assertRaises(ValueError):
            validate_image_data_url("data:image/svg+xml;base64,PHN2Zz4=")

    def test_rejects_image_over_configured_byte_limit(self) -> None:
        encoded = base64.b64encode(b"12345").decode("ascii")

        with patch("menu_image_parser.MAX_IMAGE_BYTES", 4), self.assertRaises(ValueError):
            validate_image_data_url(f"data:image/jpeg;base64,{encoded}")

    def test_rejects_photo_result_without_menu_items(self) -> None:
        with self.assertRaises(ValueError):
            build_menu_data_from_ocr(
                {"restaurant_name": None, "currency": None, "items": []},
                "abcdef1234567890",
            )

    def test_builds_unverified_common_menu_data(self) -> None:
        result = build_menu_data_from_ocr(
            {
                "restaurant_name": "Photo Cafe",
                "currency": "AUD",
                "items": [
                    {
                        "category_original": "Coffee",
                        "item_type": "beverage",
                        "name_original": "Flat White",
                        "description_original": None,
                        "price": 5.5,
                    }
                ],
            },
            "abcdef1234567890",
        )

        self.assertEqual(result["dataset_status"], "ocr_extracted_unverified")
        self.assertEqual(result["counts"], {"food": 0, "beverage": 1, "total": 1})
        self.assertEqual(result["items"][0]["option_status"], "not_checked")
        self.assertEqual(result["items"][0]["name_original"], "Flat White")


if __name__ == "__main__":
    unittest.main()
