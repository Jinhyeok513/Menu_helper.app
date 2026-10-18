"""V1.1 provider-neutral embedded/semantic HTML extraction helpers.

Added to reuse the same relationship rules for static HTML and a future
rendered DOM. ``html_menu_parser.py`` calls these functions with JSON-LD
documents or HTML and receives raw menu item dictionaries; final common-menu
normalisation remains in the existing parser.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


PRICE_PATTERN = re.compile(
    r"(?P<currency>A\$|AU\$|US\$|NZ\$|\$|€|£)?\s*"
    r"(?P<amount>\d{1,4}(?:[.,]\d{1,2})?)"
)
ITEM_HINTS = {"item", "product", "dish", "meal", "menuitem", "menu-item"}
NAME_HINTS = {"name", "title", "product-name", "item-name", "dish-name"}
PRICE_HINTS = {"price", "amount", "cost"}
EXCLUDED_HINTS = {
    "cart",
    "checkout",
    "delivery",
    "fee",
    "minimum-order",
    "order-total",
    "shipping",
    "subtotal",
}


def _tokens(attributes: dict[str, str]) -> set[str]:
    raw = " ".join(
        value
        for key, value in attributes.items()
        if key in {"class", "id", "data-testid", "itemprop"}
    ).lower()
    return {
        token
        for token in re.split(r"[^a-z0-9_-]+", raw)
        if token
    }


def _normalise_text(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


@dataclass
class _Node:
    tag: str
    attributes: dict[str, str]
    parent: "_Node | None" = None
    children: list["_Node"] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)
    order: int = 0

    def text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text())
        return _normalise_text(parts)

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()


class _DOMTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self.stack = [self.root]
        self._order = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._order += 1
        node = _Node(
            tag=tag.lower(),
            attributes={key.lower(): value or "" for key, value in attrs},
            parent=self.stack[-1],
            order=self._order,
        )
        self.stack[-1].children.append(node)
        if tag.lower() not in {
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
        }:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag.lower():
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_parts.append(data)


def resolve_json_ld_references(documents: list[object]) -> list[object]:
    """Resolve local ``@id`` references without following network URLs."""
    id_map: dict[str, dict] = {}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            identifier = value.get("@id")
            if isinstance(identifier, str) and len(value) > 1:
                id_map[identifier] = value
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(documents)

    def expand(value: object, active_ids: frozenset[str]) -> object:
        if isinstance(value, list):
            return [expand(item, active_ids) for item in value]
        if not isinstance(value, dict):
            return value
        identifier = value.get("@id")
        base = value
        if (
            isinstance(identifier, str)
            and identifier in id_map
            and identifier not in active_ids
        ):
            base = {**id_map[identifier], **value}
            active_ids = active_ids | {identifier}
        return {
            key: expand(item, active_ids)
            for key, item in base.items()
        }

    return [expand(copy.deepcopy(document), frozenset()) for document in documents]


def _has_hint(node: _Node, hints: set[str]) -> bool:
    tokens = _tokens(node.attributes)
    return bool(tokens.intersection(hints)) or any(
        any(hint in token for hint in hints) for token in tokens
    )


def _candidate_nodes(root: _Node) -> list[_Node]:
    candidates = []
    for node in root.descendants():
        if node.tag not in {"article", "div", "li"}:
            continue
        if _has_hint(node, EXCLUDED_HINTS):
            continue
        if node.attributes.get("itemtype", "").lower().endswith("/menuitem"):
            candidates.append(node)
            continue
        if _has_hint(node, ITEM_HINTS):
            candidates.append(node)

    # A parent menu list and each item can both match. Keep only the deepest
    # nodes so a name is never paired with a price from a sibling product.
    return [
        node
        for node in candidates
        if not any(descendant in candidates for descendant in node.descendants())
    ]


def _find_name(node: _Node) -> str | None:
    explicit_name = node.attributes.get("data-name")
    if explicit_name and explicit_name.strip():
        return _normalise_text([explicit_name])
    descendants = [node, *node.descendants()]
    for candidate in descendants:
        if candidate.attributes.get("itemprop", "").lower() == "name" or _has_hint(
            candidate, NAME_HINTS
        ):
            text = candidate.text()
            if text:
                return text
    for candidate in descendants:
        if candidate.tag in {"h2", "h3", "h4", "h5", "h6"}:
            text = candidate.text()
            if text:
                return text
    return None


def _find_price(node: _Node) -> tuple[int | float | None, str | None, str | None]:
    descendants = [node, *node.descendants()]
    price_text = None
    for candidate in descendants:
        data_price = candidate.attributes.get("data-price")
        if data_price:
            price_text = data_price
            break
        if candidate.attributes.get("itemprop", "").lower() == "price" or _has_hint(
            candidate, PRICE_HINTS
        ):
            price_text = candidate.attributes.get("content") or candidate.text()
            if price_text:
                break
    if not price_text:
        return None, None, None
    match = PRICE_PATTERN.search(price_text.replace(",", ""))
    if match is None:
        return None, None, price_text
    number = float(match.group("amount"))
    amount: int | float = int(number) if number.is_integer() else number
    symbol = match.group("currency")
    currency = {
        "A$": "AUD",
        "AU$": "AUD",
        "US$": "USD",
        "NZ$": "NZD",
        "€": "EUR",
        "£": "GBP",
    }.get(symbol)
    # A bare dollar symbol is ambiguous and remains unknown.
    return amount, currency, price_text


def _category_for(node: _Node) -> str | None:
    current = node.parent
    while current is not None:
        explicit = current.attributes.get("data-category") or current.attributes.get(
            "aria-label"
        )
        if explicit:
            return _normalise_text([explicit])
        for child in current.children:
            if child is node:
                break
            if child.tag in {"h1", "h2", "h3"} and child.text():
                return child.text()
        current = current.parent
    return None


def _item_type(category: str | None) -> str:
    category_lower = (category or "").lower()
    if any(word in category_lower for word in ("drink", "beverage", "coffee", "tea", "juice")):
        return "beverage"
    if any(word in category_lower for word in ("food", "breakfast", "lunch", "dinner", "main", "dessert")):
        return "food"
    return "unknown"


def extract_semantic_html_items(html: str) -> list[dict]:
    """Extract only name/price pairs proven to share one repeated container."""
    parser = _DOMTreeParser()
    parser.feed(html)
    items: list[dict] = []
    seen: set[str] = set()
    for display_order, node in enumerate(_candidate_nodes(parser.root), start=1):
        name = _find_name(node)
        price, currency, price_text = _find_price(node)
        if not name or price is None:
            continue
        category = _category_for(node)
        signature = f"{category}|{name}|{price}|{currency}"
        if signature in seen:
            continue
        seen.add(signature)
        identifier = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
        items.append(
            {
                "item_id": f"semantic_{identifier}",
                "source_product_id": None,
                "name_original": name,
                "name_ko": None,
                "category_original": category or "Uncategorised",
                "category_ko": None,
                "item_type": _item_type(category),
                "price": price,
                "price_max": None,
                "currency": currency,
                "description_original": None,
                "image_urls": [],
                "image_was_present": False,
                "display_order": display_order,
                "extraction_evidence": {
                    "relationship": "same_item_container",
                    "price_text": price_text,
                },
            }
        )
    return items
