import unittest
from pathlib import Path

from html_menu_parser import UnsupportedMenuPageError, parse_menu_html
from menu_ui import create_menu_ui_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "demo_cafe_menu.html"


class HTMLMenuParserTest(unittest.TestCase):
    def test_demo_html_becomes_common_menu_data(self) -> None:
        html = FIXTURE_PATH.read_text(encoding="utf-8")

        menu_data = parse_menu_html(
            html,
            "https://example.com/demo-cafe/menu",
        )
        ui_data = create_menu_ui_data(menu_data)

        self.assertEqual(menu_data["restaurant"]["name"], "Harbour Demo Cafe")
        self.assertEqual(
            menu_data["counts"],
            {"food": 12, "beverage": 6, "total": 18},
        )
        self.assertEqual([tab["item_count"] for tab in ui_data["tabs"]], [12, 6])
        self.assertEqual(
            [
                category["category_original"]
                for category in ui_data["tabs"][0]["categories"]
            ],
            ["Breakfast", "Lunch"],
        )
        first_item = ui_data["tabs"][0]["categories"][0]["items"][0]
        self.assertEqual(first_item["item_id"], "demo_001")
        self.assertEqual(first_item["name_original"], "Avocado Toast")
        self.assertEqual(first_item["price_aud"], 18)

    def test_unsupported_html_is_not_treated_as_empty_menu(self) -> None:
        with self.assertRaises(UnsupportedMenuPageError):
            parse_menu_html(
                "<html><h1>No menu structure</h1></html>",
                "https://example.com",
            )

    def test_json_ld_menu_section_is_supported(self) -> None:
        html = """
        <html><head><script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Restaurant",
          "name": "Schema Cafe",
          "hasMenu": {
            "@type": "Menu",
            "hasMenuSection": {
              "@type": "MenuSection",
              "name": "Cold Beverages",
              "hasMenuItem": {
                "@type": "MenuItem",
              "name": "Iced Tea",
              "@id": "iced-tea-1",
              "image": ["/images/tea-small.jpg", "/images/tea-large.jpg"],
                "offers": {
                  "@type": "Offer",
                  "price": "6.50",
                  "priceCurrency": "AUD"
                }
              }
            }
          }
        }
        </script></head></html>
        """

        result = parse_menu_html(html, "https://example.com/menu")

        self.assertEqual(result["restaurant"]["name"], "Schema Cafe")
        self.assertEqual(result["counts"], {"food": 0, "beverage": 1, "total": 1})
        self.assertEqual(result["items"][0]["name_original"], "Iced Tea")
        self.assertEqual(result["items"][0]["price_aud"], 6.5)
        item = result["items"][0]
        self.assertEqual(item["source_product_id"], "iced-tea-1")
        self.assertEqual(item["option_status"], "not_checked")
        self.assertEqual(item["image_status"], "available")
        self.assertEqual(
            [image["url_original"] for image in item["images"]],
            [
                "https://example.com/images/tea-small.jpg",
                "https://example.com/images/tea-large.jpg",
            ],
        )


if __name__ == "__main__":
    unittest.main()
