import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin


class UnsupportedMenuPageError(ValueError):
    """지원하는 HTML 구조에서 메뉴 항목을 찾지 못했을 때 발생한다."""


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _schema_types(value: object) -> set[str]:
    return {
        str(item).lower()
        for item in _as_list(value)
        if isinstance(item, str)
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "menu"


def _parse_price(value: object) -> int | float | None:
    if isinstance(value, int | float):
        return value
    if not isinstance(value, str):
        return None

    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    if match is None:
        return None

    number = float(match.group())
    return int(number) if number.is_integer() else number


def _infer_item_type(category_name: str, explicit_type: str | None) -> str:
    if explicit_type in {"food", "beverage"}:
        return explicit_type

    beverage_words = ("beverage", "drink", "coffee", "tea", "juice")
    if any(word in category_name.lower() for word in beverage_words):
        return "beverage"
    return "food"


def _read_offer(menu_item: dict) -> tuple[int | float | None, str | None]:
    offers = _as_list(menu_item.get("offers"))
    first_offer = next((offer for offer in offers if isinstance(offer, dict)), {})
    price = _parse_price(
        first_offer.get("price")
        or first_offer.get("lowPrice")
        or menu_item.get("price")
    )
    currency = first_offer.get("priceCurrency") or menu_item.get("priceCurrency")
    return price, currency


def _image_url(value: object, source_url: str) -> str | None:
    if isinstance(value, str):
        return urljoin(source_url, value)
    if isinstance(value, dict):
        url = value.get("url") or value.get("contentUrl")
        if isinstance(url, str):
            return urljoin(source_url, url)
    if isinstance(value, list) and value:
        return _image_url(value[0], source_url)
    return None


class _MenuHTMLParser(HTMLParser):
    """JSON-LD와 menu-helper 데모용 data 속성을 읽는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.restaurant: dict = {}
        self.custom_items: list[dict] = []
        self.json_ld_documents: list[object] = []
        self.page_title = ""

        self._tag_stack: list[str] = []
        self._category: dict | None = None
        self._category_depth: int | None = None
        self._item: dict | None = None
        self._item_depth: int | None = None
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_text: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        void_tags = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
        if tag not in void_tags:
            self._tag_stack.append(tag)
        depth = len(self._tag_stack)
        attributes = dict(attrs)

        if tag == "title":
            self._in_title = True

        if (
            tag == "script"
            and attributes.get("type", "").lower() == "application/ld+json"
        ):
            self._in_json_ld = True
            self._json_ld_parts = []

        if "data-menu-root" in attributes:
            self.restaurant = {
                "name": attributes.get("data-restaurant-name"),
                "restaurant_id": attributes.get("data-restaurant-id"),
                "currency": attributes.get("data-currency"),
            }

        if "data-menu-category" in attributes:
            self._category = {
                "category_original": attributes.get("data-category"),
                "category_ko": attributes.get("data-category-ko"),
                "item_type": attributes.get("data-item-type"),
            }
            self._category_depth = depth

        if "data-menu-item" in attributes:
            self._item = {
                "item_id": attributes.get("data-item-id"),
                "item_type": attributes.get("data-item-type"),
                "name_original": attributes.get("data-name"),
                "name_ko": attributes.get("data-name-ko"),
                "price": attributes.get("data-price"),
                "currency": attributes.get("data-currency"),
                "description_original": attributes.get("data-description"),
                "image_url": attributes.get("data-image-url"),
                "category": dict(self._category or {}),
            }
            self._item_depth = depth

        field_attributes = {
            "data-menu-name": "name_original",
            "data-menu-name-ko": "name_ko",
            "data-menu-description": "description_original",
            "data-menu-price": "price",
        }
        if self._item is not None:
            for attribute_name, field_name in field_attributes.items():
                if attribute_name in attributes:
                    self._capture_field = field_name
                    self._capture_tag = tag
                    self._capture_text = []
                    break

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_parts.append(data)
        if self._in_title:
            self._title_parts.append(data)
        if self._capture_field is not None:
            self._capture_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        depth = len(self._tag_stack)

        if self._capture_field is not None and tag == self._capture_tag:
            value = " ".join("".join(self._capture_text).split())
            if value and self._item is not None:
                self._item[self._capture_field] = value
            self._capture_field = None
            self._capture_tag = None
            self._capture_text = []

        if tag == "script" and self._in_json_ld:
            raw_json = "".join(self._json_ld_parts).strip()
            if raw_json:
                try:
                    self.json_ld_documents.append(json.loads(raw_json))
                except json.JSONDecodeError:
                    # 다른 JSON-LD 문서가 유효할 수 있으므로 한 블록의 실패만 건너뛴다.
                    pass
            self._in_json_ld = False
            self._json_ld_parts = []

        if tag == "title":
            self._in_title = False
            self.page_title = " ".join("".join(self._title_parts).split())

        if self._item is not None and depth == self._item_depth:
            self.custom_items.append(self._item)
            self._item = None
            self._item_depth = None

        if self._category is not None and depth == self._category_depth:
            self._category = None
            self._category_depth = None

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()


def _iter_json_nodes(value: object):
    if isinstance(value, dict):
        yield value
        for nested_value in value.values():
            yield from _iter_json_nodes(nested_value)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_nodes(item)


def _extract_json_ld_items(
    documents: list[object],
    source_url: str,
) -> tuple[str | None, list[dict]]:
    restaurant_name = None
    menu_items: list[dict] = []
    seen_items: set[tuple] = set()

    for node in _iter_json_nodes(documents):
        node_types = _schema_types(node.get("@type"))
        if restaurant_name is None and node_types.intersection(
            {"restaurant", "foodestablishment", "cafeorcoffeeshop"}
        ):
            name = node.get("name")
            if isinstance(name, str):
                restaurant_name = name

        if "menusection" not in node_types:
            continue

        category_name = str(node.get("name") or "Menu")
        for raw_item in _as_list(
            node.get("hasMenuItem") or node.get("menuItem")
        ):
            if not isinstance(raw_item, dict):
                continue
            if "menuitem" not in _schema_types(raw_item.get("@type")):
                continue

            name = raw_item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            price, currency = _read_offer(raw_item)
            deduplication_key = (category_name, name, price, currency)
            if deduplication_key in seen_items:
                continue
            seen_items.add(deduplication_key)

            menu_items.append(
                {
                    "name_original": name.strip(),
                    "name_ko": None,
                    "category_original": category_name,
                    "category_ko": None,
                    "item_type": _infer_item_type(category_name, None),
                    "price": price,
                    "currency": currency,
                    "description_original": raw_item.get("description"),
                    "image_url": _image_url(raw_item.get("image"), source_url),
                }
            )

    return restaurant_name, menu_items


def _normalise_custom_items(raw_items: list[dict]) -> list[dict]:
    normalised_items = []
    for raw_item in raw_items:
        category = raw_item.get("category") or {}
        category_original = category.get("category_original") or "Menu"
        name = raw_item.get("name_original")
        if not isinstance(name, str) or not name.strip():
            continue

        normalised_items.append(
            {
                **raw_item,
                "name_original": name.strip(),
                "category_original": category_original,
                "category_ko": category.get("category_ko"),
                "item_type": _infer_item_type(
                    category_original,
                    raw_item.get("item_type") or category.get("item_type"),
                ),
                "price": _parse_price(raw_item.get("price")),
                "currency": raw_item.get("currency"),
            }
        )
    return normalised_items


def _build_menu_item(
    raw_item: dict,
    index: int,
    restaurant_id: str,
    default_currency: str,
    source_url: str,
) -> dict:
    item_id = raw_item.get("item_id") or f"html_{index:03d}"
    return {
        "item_id": item_id,
        "item_id_source": "source" if raw_item.get("item_id") else "generated",
        "restaurant_id": restaurant_id,
        "item_type": raw_item["item_type"],
        "category_original": raw_item["category_original"],
        "category_ko": raw_item.get("category_ko"),
        "name_original": raw_item["name_original"],
        "name_ko": raw_item.get("name_ko"),
        "description_original": raw_item.get("description_original"),
        "price_aud": raw_item.get("price"),
        "currency": raw_item.get("currency") or default_currency,
        "ingredients_listed": [],
        "ingredients_listed_ko": [],
        "ingredients_from_name": [],
        "ingredient_coverage": "unknown",
        "options": [],
        "option_note": None,
        "review_note": None,
        "source_id": "menu_url_html",
        "source_url": source_url,
        "source_menu_type": "public_html",
        "source_menu_updated_at": None,
        "retrieved_at": datetime.now(UTC).date().isoformat(),
        "google_menu_match_verified": False,
        "taste_explanation_ko": None,
        "allergen_safety": None,
        "image_url": raw_item.get("image_url"),
    }


def parse_menu_html(html: str, source_url: str) -> dict:
    """지원하는 HTML을 기존 JSON과 같은 메뉴 딕셔너리로 변환한다."""
    parser = _MenuHTMLParser()
    parser.feed(html)

    raw_items = _normalise_custom_items(parser.custom_items)
    extraction_method = "data_attributes"
    restaurant_name = parser.restaurant.get("name")

    if not raw_items:
        restaurant_name, raw_items = _extract_json_ld_items(
            parser.json_ld_documents,
            source_url,
        )
        extraction_method = "json_ld_menu"

    if not raw_items:
        raise UnsupportedMenuPageError(
            "지원하는 data-menu 속성 또는 JSON-LD MenuItem을 찾지 못했습니다."
        )

    restaurant_name = restaurant_name or parser.page_title or "Unknown restaurant"
    restaurant_id = (
        parser.restaurant.get("restaurant_id")
        or f"html_{_slugify(restaurant_name)}"
    )
    default_currency = parser.restaurant.get("currency") or "AUD"
    items = [
        _build_menu_item(
            raw_item,
            index,
            restaurant_id,
            default_currency,
            source_url,
        )
        for index, raw_item in enumerate(raw_items, start=1)
    ]

    return {
        "schema_version": "1.0",
        "dataset_status": "extracted_unverified",
        "restaurant": {
            "restaurant_id": restaurant_id,
            "name": restaurant_name,
        },
        "provenance": {
            "source_url": source_url,
            "extraction_method": extraction_method,
            "retrieved_at": datetime.now(UTC).date().isoformat(),
            "limitations_ko": [
                "지원하는 HTML 구조에서 읽은 결과이며 원본과 대조가 필요합니다.",
                "동적 자바스크립트·로그인·접근 제한 페이지는 지원하지 않습니다.",
            ],
        },
        "counts": {
            "food": sum(item["item_type"] == "food" for item in items),
            "beverage": sum(
                item["item_type"] == "beverage" for item in items
            ),
            "total": len(items),
        },
        "items": items,
    }
