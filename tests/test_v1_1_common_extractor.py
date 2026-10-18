import unittest

from html_menu_parser import parse_menu_html
from v1_1_common_extractor import extract_semantic_html_items
from v1_1_extraction_pipeline import validate_common_menu


class V11CommonExtractorTest(unittest.TestCase):
    def test_two_different_container_shapes_use_same_relationship_rule(self) -> None:
        structures = (
            """
            <section data-category="Mains">
              <article class="menu-item"><h3 class="item-name">Dumplings</h3>
                <span class="price">A$12.50</span></article>
            </section>
            """,
            """
            <div aria-label="Cold Drinks">
              <div class="product-card"><p itemprop="name">Lemon Tea</p>
                <meta itemprop="price" content="6.00"></div>
            </div>
            """,
        )

        first, second = (extract_semantic_html_items(html) for html in structures)

        self.assertEqual(first[0]["name_original"], "Dumplings")
        self.assertEqual(first[0]["price"], 12.5)
        self.assertEqual(first[0]["currency"], "AUD")
        self.assertEqual(second[0]["name_original"], "Lemon Tea")
        self.assertEqual(second[0]["price"], 6)
        self.assertIsNone(second[0]["currency"])
        self.assertEqual(second[0]["item_type"], "beverage")

    def test_names_and_prices_in_separate_sibling_containers_are_not_zipped(self) -> None:
        html = """
        <div class="menu-names"><h3>Noodles</h3><h3>Tea</h3></div>
        <div class="menu-prices"><span>A$12</span><span>A$5</span></div>
        """

        self.assertEqual(extract_semantic_html_items(html), [])

    def test_json_ld_id_reference_and_unknown_values_are_preserved(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@id":"#restaurant","@type":"Restaurant","name":"Graph Cafe",
           "hasMenu":{"@id":"#menu"}},
          {"@id":"#menu","@type":"Menu","hasMenuSection":{"@id":"#section"}},
          {"@id":"#section","@type":"MenuSection","name":"Specials",
           "hasMenuItem":{"@id":"#dish"}},
          {"@id":"#dish","@type":"MenuItem","name":"Chef Plate",
           "offers":{"@type":"Offer","price":"19"}}
        ]}
        </script>
        """

        result = parse_menu_html(html, "https://example.com/menu")
        item = result["items"][0]

        self.assertEqual(item["name_original"], "Chef Plate")
        self.assertEqual(item["price_amount"], 19)
        self.assertIsNone(item["price_aud"])
        self.assertIsNone(item["currency"])
        self.assertEqual(item["item_type"], "unknown")
        status, validation, warnings = validate_common_menu(result)
        self.assertEqual(status, "partial")
        self.assertEqual(validation, "needs_review")
        self.assertIn("currency_unknown", warnings)


if __name__ == "__main__":
    unittest.main()
