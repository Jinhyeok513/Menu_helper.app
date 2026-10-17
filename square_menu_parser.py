import json
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from html_menu_parser import UnsupportedMenuPageError


SQUARE_BOOTSTRAP_PREFIX = "window.__BOOTSTRAP_STATE__ = "
SQUARE_CATALOG_ORIGIN = "https://cdn5.editmysite.com"


def extract_square_storefront_info(html: str) -> dict | None:
    """Square Online HTML의 공개 bootstrap 메타데이터를 읽는다."""
    marker_position = html.find(SQUARE_BOOTSTRAP_PREFIX)
    if marker_position == -1:
        return None

    json_start = marker_position + len(SQUARE_BOOTSTRAP_PREFIX)
    script_end = html.find("</script>", json_start)
    if script_end == -1:
        raise UnsupportedMenuPageError(
            "Square Online bootstrap script의 끝을 찾지 못했습니다."
        )

    raw_json = html[json_start:script_end].strip().removesuffix(";")
    try:
        bootstrap = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise UnsupportedMenuPageError(
            "Square Online bootstrap 데이터를 JSON으로 읽지 못했습니다."
        ) from error

    site_data = bootstrap.get("siteData") or {}
    site = site_data.get("site") or {}
    site_properties = site.get("properties") or {}
    user = site_data.get("user") or {}
    snapshot = site_data.get("snapshot") or {}
    snapshot_properties = snapshot.get("properties") or {}
    store_info = bootstrap.get("storeInfo") or {}
    feature_flags = bootstrap.get("featureFlags") or {}

    location_ids = store_info.get("shipping_location_ids") or []
    location_id = next(
        (value for value in location_ids if isinstance(value, str) and value),
        None,
    )
    user_id = user.get("id")
    site_id = site_properties.get("classicSiteID")

    if user_id is None or not site_id or not location_id:
        raise UnsupportedMenuPageError(
            "Square Online 상품 API에 필요한 사이트·위치 정보를 찾지 못했습니다."
        )

    return {
        "user_id": str(user_id),
        "site_id": str(site_id),
        "location_id": location_id,
        "restaurant_name": snapshot_properties.get("title") or "Square restaurant",
        "currency": store_info.get("currency") or "AUD",
        "cache_version": feature_flags.get(
            "ecom.square-online-published-catalog-cache-version"
        ),
    }


def _square_api_root(storefront_info: dict) -> str:
    user_id = quote(storefront_info["user_id"], safe="")
    site_id = quote(storefront_info["site_id"], safe="")
    location_id = quote(storefront_info["location_id"], safe="")
    return (
        f"{SQUARE_CATALOG_ORIGIN}/app/store/api/v28/editor/users/{user_id}"
        f"/sites/{site_id}/store-locations/{location_id}"
    )


def build_square_catalog_urls(storefront_info: dict) -> tuple[str, str]:
    """Square 브라우저 화면이 사용하는 공개 카테고리·상품 URL을 만든다."""
    api_root = _square_api_root(storefront_info)

    shared_cache_parameter = {}
    cache_version = storefront_info.get("cache_version")
    if isinstance(cache_version, str) and cache_version:
        shared_cache_parameter["cache-version"] = cache_version

    product_query = urlencode(
        {
            "page": 1,
            "per_page": 200,
            "include": "images,options,modifiers,discounts,media_files",
            "has_categories": 1,
            "fulfillments[]": "dine_in",
            **shared_cache_parameter,
        }
    )
    category_query = urlencode(
        {
            "max_depth": 2,
            "nested": 1,
            "product_counts_fulfillments[]": "dine_in",
            **shared_cache_parameter,
        }
    )
    return (
        f"{api_root}/products?{product_query}",
        f"{api_root}/categories?{category_query}",
    )


def build_square_product_detail_urls(
    storefront_info: dict,
    source_product_id: str,
) -> tuple[str, str]:
    """실제 상품 상세 화면이 요청하는 상품·SKU URL을 만든다."""
    api_root = _square_api_root(storefront_info)
    product_id = quote(source_product_id, safe="")
    cache_parameters = {}
    cache_version = storefront_info.get("cache_version")
    if isinstance(cache_version, str) and cache_version:
        cache_parameters["cache-version"] = cache_version

    detail_query = urlencode(
        {
            "include": (
                "images,options,modifiers,category,categories,discounts,"
                "media_files,subscriptions"
            ),
            **cache_parameters,
        }
    )
    sku_query = urlencode(
        {
            "page": 1,
            "per_page": 100,
            "include": "image,media_files,product,subscriptions",
            **cache_parameters,
        }
    )
    return (
        f"{api_root}/products/{product_id}?{detail_query}",
        f"{api_root}/products/{product_id}/skus?{sku_query}",
    )


def _flatten_categories(categories: list[dict]):
    for category in categories:
        if not isinstance(category, dict):
            continue
        yield category
        children = category.get("children") or []
        if isinstance(children, list):
            yield from _flatten_categories(children)


def _number(value: object) -> int | float | None:
    if not isinstance(value, int | float):
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _display_order(value: object, fallback: int) -> int | float:
    parsed = _number(value)
    return fallback if parsed is None else parsed


def _infer_item_type(category_name: str) -> str:
    beverage_words = (
        "beverage",
        "coffee",
        "drink",
        "juice",
        "shake",
        "smoothie",
        "soda",
        "tea",
    )
    category_lower = category_name.lower()
    if any(word in category_lower for word in beverage_words):
        return "beverage"
    return "food"


def _image_variant_url(image: dict, preferred_width: int) -> str | None:
    urls = image.get("urls") or {}
    exact = urls.get(str(preferred_width))
    if isinstance(exact, str) and exact:
        return exact

    available = []
    if isinstance(urls, dict):
        for width, url in urls.items():
            try:
                numeric_width = int(width)
            except (TypeError, ValueError):
                continue
            if isinstance(url, str) and url:
                available.append((numeric_width, url))
    if not available:
        return None
    return min(available, key=lambda pair: abs(pair[0] - preferred_width))[1]


def _read_product_images(
    product: dict,
    source_product_id: str,
    retrieved_at: str,
) -> tuple[list[dict], str]:
    images_were_requested = "images" in product
    images = product.get("images") or {}
    image_data = images.get("data") or []
    if not isinstance(image_data, list):
        return [], "unsupported"

    normalized_images = []
    invalid_count = 0
    for raw_image in image_data:
        if not isinstance(raw_image, dict):
            invalid_count += 1
            continue
        original_url = raw_image.get("absolute_url")
        if not isinstance(original_url, str) or not original_url:
            invalid_count += 1
            continue

        normalized_images.append(
            {
                "image_id": raw_image.get("id"),
                "source_product_id": source_product_id,
                "display_order": len(normalized_images) + 1,
                "role": "primary" if not normalized_images else "additional",
                "url_original": original_url,
                "thumbnail_url": _image_variant_url(raw_image, 320) or original_url,
                "large_url": _image_variant_url(raw_image, 1280) or original_url,
                "width": raw_image.get("width"),
                "height": raw_image.get("height"),
                "format": raw_image.get("format"),
                "source_id": "square_storefront_api",
                "retrieved_at": retrieved_at,
            }
        )

    thumbnail = product.get("thumbnail") or {}
    thumbnail_data = thumbnail.get("data") or {}
    thumbnail_url = thumbnail_data.get("absolute_url")
    if (
        not normalized_images
        and isinstance(thumbnail_url, str)
        and thumbnail_url
    ):
        normalized_images.append(
            {
                "image_id": thumbnail_data.get("id"),
                "source_product_id": source_product_id,
                "display_order": 1,
                "role": "primary",
                "url_original": thumbnail_url,
                "thumbnail_url": thumbnail_url,
                "large_url": None,
                "width": thumbnail_data.get("width"),
                "height": thumbnail_data.get("height"),
                "format": thumbnail_data.get("format"),
                "source_id": "square_storefront_api",
                "retrieved_at": retrieved_at,
            }
        )

    if normalized_images:
        return normalized_images, "partial" if invalid_count else "available"
    if invalid_count:
        return [], "unsupported"
    return [], "none" if images_were_requested else "not_checked"


def _choice_price(raw_choice: dict) -> tuple[int | float | None, str]:
    if "price" not in raw_choice or raw_choice.get("price") is None:
        return None, "unknown"
    price = _number(raw_choice.get("price"))
    if price is None:
        return None, "unknown"
    return price, "confirmed"


def _read_modifier_groups(product: dict, currency: str) -> tuple[list[dict], str]:
    raw_modifiers = product.get("modifiers")
    if raw_modifiers is None:
        return [], "not_checked"
    if not isinstance(raw_modifiers, dict):
        return [], "unsupported"
    raw_groups = raw_modifiers.get("data")
    if not isinstance(raw_groups, list):
        return [], "unsupported"

    groups = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            continue
        raw_choices = raw_group.get("choices") or []
        if not isinstance(raw_choices, list):
            continue
        raw_max_selected = _number(raw_group.get("max_selected"))
        max_selected = None if raw_max_selected == 0 else raw_max_selected
        min_selected = _number(raw_group.get("min_selected"))
        min_selected = 0 if min_selected is None else min_selected
        if raw_max_selected is None:
            selection_type = "unknown"
            selection_limit_status = "unknown"
        elif max_selected == 1:
            selection_type = "single"
            selection_limit_status = "specified"
        elif max_selected is None or (
            isinstance(max_selected, int | float) and max_selected > 1
        ):
            selection_type = "multiple"
            selection_limit_status = (
                "unlimited" if raw_max_selected == 0 else "specified"
            )
        else:
            selection_type = "unknown"
            selection_limit_status = "unknown"

        choices = []
        for choice_index, raw_choice in enumerate(raw_choices, start=1):
            if not isinstance(raw_choice, dict):
                continue
            price_delta, price_status = _choice_price(raw_choice)
            choices.append(
                {
                    "choice_id": (
                        raw_choice.get("id") or raw_choice.get("square_id")
                    ),
                    "name_original": (
                        raw_choice.get("display_name")
                        or raw_choice.get("name")
                        or raw_choice.get("label")
                    ),
                    "display_order": _display_order(
                        raw_choice.get("display_order"),
                        choice_index,
                    ),
                    "selected_by_default": bool(
                        raw_choice.get("selected_by_default")
                    ),
                    "sold_out": bool(raw_choice.get("sold_out")),
                    "hidden": bool(raw_choice.get("hidden")),
                    "price_delta_aud": price_delta,
                    "price_kind": "additional",
                    "price_status": price_status,
                    "currency": currency,
                }
            )
        choices.sort(key=lambda choice: choice["display_order"])
        groups.append(
            {
                "group_id": raw_group.get("id") or raw_group.get("square_id"),
                "group_type": "modifier",
                "source_type": raw_group.get("type"),
                "name_original": raw_group.get("name"),
                "display_order": _display_order(
                    raw_group.get("display_order"),
                    len(groups) + 1,
                ),
                "required": min_selected > 0,
                "min_selected": min_selected,
                "max_selected": max_selected,
                "raw_max_selected": raw_max_selected,
                "selection_limit_status": selection_limit_status,
                "selection_type": selection_type,
                "allow_quantities": raw_group.get("allow_quantities"),
                "max_quantity": _number(raw_group.get("max_quantity")),
                "choices": choices,
            }
        )
    groups.sort(key=lambda group: group["display_order"])
    return groups, "available" if groups else "none"


def _read_variants(
    sku_document: object | None,
    currency: str,
    fetch_failed: bool = False,
) -> tuple[list[dict], str]:
    if fetch_failed:
        return [], "fetch_failed"
    if sku_document is None:
        return [], "not_checked"
    if not isinstance(sku_document, dict) or not isinstance(sku_document.get("data"), list):
        return [], "unsupported"

    variants = []
    for index, raw_sku in enumerate(sku_document["data"], start=1):
        if not isinstance(raw_sku, dict):
            continue
        price = raw_sku.get("price") or {}
        current_price = _number(price.get("current")) if isinstance(price, dict) else None
        variants.append(
            {
                "variant_id": raw_sku.get("id") or raw_sku.get("square_id"),
                "name_original": raw_sku.get("name"),
                "display_order": _display_order(raw_sku.get("display_order"), index),
                "selected_by_default": (
                    bool(raw_sku.get("selected_by_default"))
                    if "selected_by_default" in raw_sku
                    else None
                ),
                "sold_out": bool(raw_sku.get("sold_out")),
                "price_aud": current_price,
                "price_kind": "full_product_price",
                "price_status": "confirmed" if current_price is not None else "unknown",
                "currency": currency,
            }
        )
    variants.sort(key=lambda variant: variant["display_order"])
    return variants, "available" if len(variants) > 1 else "none"


def _ordered_category_products(
    category: dict,
    products: list[dict],
    products_by_id: dict[str, dict],
) -> list[dict]:
    category_id = category.get("id")
    if not isinstance(category_id, str):
        return []

    matching_products = [
        product
        for product in products
        if category_id in (product.get("categoryIds") or [])
    ]
    matching_ids = {
        product.get("id")
        for product in matching_products
        if isinstance(product.get("id"), str)
    }
    ordered_products = []
    added_ids = set()

    for product_id in category.get("preferred_order_product_ids") or []:
        product = products_by_id.get(product_id)
        if product_id in matching_ids and product is not None:
            ordered_products.append(product)
            added_ids.add(product_id)

    for product in matching_products:
        product_id = product.get("id")
        if product_id not in added_ids:
            ordered_products.append(product)
            added_ids.add(product_id)

    return ordered_products


def _build_square_item(
    product: dict,
    category: dict,
    storefront_info: dict,
    source_url: str,
    retrieved_at: str | None = None,
) -> dict:
    product_id = str(product.get("id"))
    category_id = str(category.get("id"))
    category_name = str(category.get("name") or "Menu")
    price_data = product.get("price") or {}
    price_low = _number(price_data.get("low"))
    price_high = _number(price_data.get("high"))

    retrieved_at = retrieved_at or datetime.now(UTC).isoformat()
    options, option_status = _read_modifier_groups(
        product,
        storefront_info["currency"],
    )
    images, image_status = _read_product_images(
        product,
        product_id,
        retrieved_at,
    )

    return {
        # 같은 상품이 여러 원문 카테고리에 표시될 수 있어 카드 ID에 카테고리도 넣는다.
        "item_id": f"square_{category_id.lower()}_{product_id.lower()}",
        "item_id_source": "square_category_and_product",
        "product_id": f"square_{storefront_info['site_id']}_{product_id}",
        "source_product_id": product_id,
        "restaurant_id": f"square_{storefront_info['site_id']}",
        "item_type": _infer_item_type(category_name),
        "category_original": category_name,
        "category_ko": None,
        "name_original": str(product.get("name") or "Unnamed item").strip(),
        "name_ko": None,
        "description_original": product.get("short_description") or None,
        "price_aud": price_low,
        "price_max_aud": price_high if price_high != price_low else None,
        "currency": storefront_info["currency"],
        "ingredients_listed": [],
        "ingredients_listed_ko": [],
        "ingredients_from_name": [],
        "ingredient_coverage": "unknown",
        "options": options,
        "option_status": option_status,
        "variants": [],
        "variant_status": "not_checked",
        "option_note": None,
        "review_note": None,
        "source_id": "square_storefront_api",
        "source_url": source_url,
        "source_menu_type": "square_storefront_api",
        "source_menu_updated_at": product.get("updated_date"),
        "retrieved_at": retrieved_at,
        "google_menu_match_verified": False,
        "taste_explanation_ko": None,
        "allergen_safety": None,
        "image_url": images[0]["url_original"] if images else None,
        "images": images,
        "image_status": image_status,
    }


def parse_square_product_detail(
    product_document: object,
    sku_document: object | None,
    source_url: str,
    storefront_info: dict,
    *,
    sku_fetch_failed: bool = False,
) -> dict:
    """Square 상품 상세와 SKU 응답을 하나의 공통 상세 데이터로 합친다."""
    if not isinstance(product_document, dict):
        raise UnsupportedMenuPageError(
            "Square 상품 상세 응답이 딕셔너리가 아닙니다."
        )
    product = product_document.get("data", product_document)
    if not isinstance(product, dict) or not isinstance(product.get("id"), str):
        raise UnsupportedMenuPageError("Square 상품 상세에서 상품 ID를 찾지 못했습니다.")

    category = product.get("category") or {}
    category_data = category.get("data") if isinstance(category, dict) else None
    if not isinstance(category_data, dict):
        categories = product.get("categories") or {}
        category_list = (
            categories.get("data") if isinstance(categories, dict) else None
        )
        category_data = (
            category_list[0]
            if isinstance(category_list, list) and category_list
            else {}
        )
    category_data = dict(category_data) if isinstance(category_data, dict) else {}
    category_data.setdefault("id", "detail")
    category_data.setdefault("name", "Menu")

    item = _build_square_item(product, category_data, storefront_info, source_url)
    variants, variant_status = _read_variants(
        sku_document,
        storefront_info["currency"],
        fetch_failed=sku_fetch_failed,
    )
    item["variants"] = variants
    item["variant_status"] = variant_status
    item["variant_selection"] = {
        # SKU는 한 상품 변형을 고르는 구조지만, 실제 응답은 필수·기본값을 주지 않는다.
        "selection_type": "single" if variants else "unknown",
        "required": None,
        "min_selected": None,
        "max_selected": None,
        "constraint_status": (
            "fetch_failed" if sku_fetch_failed else "not_provided"
        ),
    }
    return item


def parse_square_catalog(
    product_document: object,
    category_document: object,
    source_url: str,
    storefront_info: dict,
) -> dict:
    """Square 공개 상품·카테고리 응답을 공통 메뉴 구조로 변환한다."""
    if not isinstance(product_document, dict):
        raise UnsupportedMenuPageError("Square 상품 응답이 딕셔너리가 아닙니다.")
    if not isinstance(category_document, dict):
        raise UnsupportedMenuPageError("Square 카테고리 응답이 딕셔너리가 아닙니다.")

    products = product_document.get("data")
    category_roots = category_document.get("data")
    if not isinstance(products, list) or not isinstance(category_roots, list):
        raise UnsupportedMenuPageError(
            "Square 상품 또는 카테고리 응답의 data가 리스트가 아닙니다."
        )

    valid_products = [
        product
        for product in products
        if isinstance(product, dict)
        and isinstance(product.get("id"), str)
        and isinstance(product.get("name"), str)
        and product.get("name").strip()
    ]
    products_by_id = {product["id"]: product for product in valid_products}
    items = []
    retrieved_at = datetime.now(UTC).isoformat()

    for category in _flatten_categories(category_roots):
        for product in _ordered_category_products(
            category,
            valid_products,
            products_by_id,
        ):
            items.append(
                _build_square_item(
                    product,
                    category,
                    storefront_info,
                    source_url,
                    retrieved_at,
                )
            )

    if not items:
        raise UnsupportedMenuPageError(
            "Square 공개 상품 응답에서 카테고리에 연결된 메뉴를 찾지 못했습니다."
        )

    return {
        "schema_version": "1.0",
        "dataset_status": "extracted_unverified",
        "restaurant": {
            "restaurant_id": f"square_{storefront_info['site_id']}",
            "name": storefront_info["restaurant_name"],
        },
        "provenance": {
            "source_url": source_url,
            "extraction_method": "square_bootstrap_storefront_api",
            "retrieved_at": datetime.now(UTC).date().isoformat(),
            "unique_product_count": len(products_by_id),
            "category_listing_count": len(items),
            "limitations_ko": [
                "Square Online 공개 상품·카테고리 API에서 읽은 결과입니다.",
                "여러 카테고리에 속한 상품은 원문처럼 각 카테고리에 표시됩니다.",
                "판매 가능 시간과 재고 상태는 메뉴 목록에서 판단하지 않습니다.",
            ],
        },
        "counts": {
            "food": sum(item["item_type"] == "food" for item in items),
            "beverage": sum(item["item_type"] == "beverage" for item in items),
            "total": len(items),
            "unique_products": len(products_by_id),
        },
        "items": items,
    }
