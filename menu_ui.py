import json
import sys
from pathlib import Path

from data_load import load_menu_data


TAB_LABELS = {
    "food": "음식",
    "beverage": "음료",
    "unknown": "미분류",
}


def _normalise_legacy_options(menu_item: dict) -> list[dict]:
    """초기 JSON 옵션을 URL 메뉴와 같은 선택 그룹 구조로 바꾼다."""
    item_id = str(menu_item.get("item_id") or "menu")
    raw_options = menu_item.get("options") or []
    if not isinstance(raw_options, list):
        return []

    normalised = []
    for group_index, raw_group in enumerate(raw_options, start=1):
        if not isinstance(raw_group, dict):
            continue
        if isinstance(raw_group.get("choices"), list) and raw_group.get("group_id"):
            normalised.append(raw_group)
            continue

        selection_count = raw_group.get("selection_count")
        selection_count = selection_count if isinstance(selection_count, int) else None
        additional_price = raw_group.get("additional_price_aud")
        price_confirmed = isinstance(additional_price, int | float)
        choices = []
        for choice_index, raw_choice in enumerate(raw_group.get("choices") or [], start=1):
            if not isinstance(raw_choice, str):
                continue
            choices.append(
                {
                    "choice_id": f"{item_id}_option_{group_index}_{choice_index}",
                    "name_original": raw_choice,
                    "display_order": choice_index,
                    "selected_by_default": False,
                    "sold_out": False,
                    "hidden": False,
                    "price_delta_aud": additional_price if price_confirmed else None,
                    "price_delta_amount": additional_price if price_confirmed else None,
                    "price_kind": "additional",
                    "price_status": "confirmed" if price_confirmed else "unknown",
                    "currency": menu_item.get("currency"),
                }
            )
        normalised.append(
            {
                "group_id": f"{item_id}_option_{group_index}",
                "group_type": "modifier",
                "source_type": "legacy_sample",
                "name_original": raw_group.get("group"),
                "display_order": group_index,
                "required": bool(selection_count and selection_count > 0),
                "min_selected": selection_count or 0,
                "max_selected": selection_count,
                "raw_max_selected": selection_count,
                "selection_limit_status": (
                    "specified" if selection_count is not None else "unknown"
                ),
                "selection_type": (
                    "single"
                    if selection_count == 1
                    else "multiple"
                    if isinstance(selection_count, int) and selection_count > 1
                    else "unknown"
                ),
                "allow_quantities": False,
                "max_quantity": None,
                "choices": choices,
            }
        )
    return normalised


def create_menu_detail(menu_item: dict) -> dict:
    """저장 JSON과 URL 상품을 모바일 상세 화면의 공통 구조로 맞춘다."""
    options = _normalise_legacy_options(menu_item)
    variants = menu_item.get("variants")
    variants = variants if isinstance(variants, list) else []
    images = menu_item.get("images")
    images = images if isinstance(images, list) else []
    image_url = menu_item.get("image_url")
    if not images and isinstance(image_url, str) and image_url:
        images = [
            {
                "image_id": None,
                "source_product_id": menu_item.get("source_product_id"),
                "display_order": 1,
                "role": "primary",
                "url_original": image_url,
                "thumbnail_url": image_url,
                "large_url": image_url,
                "width": None,
                "height": None,
                "format": None,
                "source_id": menu_item.get("source_id") or "stored_menu_json",
                "retrieved_at": menu_item.get("retrieved_at"),
            }
        ]

    detail = dict(menu_item)
    detail.update(
        {
            "product_id": menu_item.get("product_id") or menu_item.get("item_id"),
            "source_product_id": menu_item.get("source_product_id"),
            # V1.1: 상세·설명이 목록과 동일한 불변 스냅샷을 조회하게 한다.
            "menu_source_id": menu_item.get("menu_source_id"),
            "snapshot_id": menu_item.get("snapshot_id"),
            "snapshot_version": menu_item.get("snapshot_version"),
            "price_amount": menu_item.get("price_amount", menu_item.get("price_aud")),
            "price_max_amount": menu_item.get(
                "price_max_amount", menu_item.get("price_max_aud")
            ),
            "price_max_aud": menu_item.get("price_max_aud"),
            "options": options,
            "option_status": menu_item.get("option_status") or (
                "available" if options else "not_checked"
            ),
            "variants": variants,
            "variant_status": menu_item.get("variant_status") or "not_checked",
            "variant_selection": menu_item.get("variant_selection") or {
                "selection_type": "unknown",
                "required": None,
                "min_selected": None,
                "max_selected": None,
                "constraint_status": "not_provided",
            },
            "images": images,
            "image_status": menu_item.get("image_status") or (
                "available" if images else "not_checked"
            ),
        }
    )
    return detail


def create_menu_card(menu_item: dict, restaurant_id: str | None = None) -> dict:
    """메뉴 원본 한 건에서 목록 카드에 필요한 필드만 골라 반환한다."""
    options = menu_item.get("options")
    options = options if isinstance(options, list) else []
    option_status = menu_item.get("option_status")
    if option_status is None:
        # 기존 JSON의 빈 options는 조사 완료를 뜻하지 않으므로 '없음'으로 바꾸지 않는다.
        option_status = "available" if options else "not_checked"
    option_choice_count = sum(
        len(group.get("choices") or [])
        for group in options
        if isinstance(group, dict)
    )
    images = menu_item.get("images")
    images = images if isinstance(images, list) else []
    return {
        "item_id": menu_item.get("item_id"),
        "product_id": menu_item.get("product_id") or menu_item.get("item_id"),
        "source_product_id": menu_item.get("source_product_id"),
        "menu_source_id": menu_item.get("menu_source_id"),
        "snapshot_id": menu_item.get("snapshot_id"),
        "snapshot_version": menu_item.get("snapshot_version"),
        "restaurant_id": (
            menu_item.get("restaurant_id")
            or restaurant_id
            or "restaurant_unknown"
        ),
        "source_id": menu_item.get("source_id") or "stored_menu_json",
        "category_original": menu_item.get("category_original"),
        "name_original": menu_item.get("name_original"),
        "name_ko": menu_item.get("name_ko"),
        "description_original": menu_item.get("description_original"),
        "ingredients_listed": menu_item.get("ingredients_listed") or [],
        "ingredients_from_name": menu_item.get("ingredients_from_name") or [],
        "price_aud": menu_item.get("price_aud"),
        "price_max_aud": menu_item.get("price_max_aud"),
        "price_amount": menu_item.get("price_amount", menu_item.get("price_aud")),
        "price_max_amount": menu_item.get(
            "price_max_amount", menu_item.get("price_max_aud")
        ),
        "currency": menu_item.get("currency"),
        "one_line_description_ko": menu_item.get("taste_explanation_ko"),
        "has_options": option_status == "available" and bool(options),
        "option_status": option_status,
        "option_group_count": len(options),
        "option_choice_count": option_choice_count,
        "variant_status": menu_item.get("variant_status") or "not_checked",
        "image_url": menu_item.get("image_url"),
        "image_status": menu_item.get("image_status") or (
            "available" if menu_item.get("image_url") else "not_checked"
        ),
        "image_count": len(images) if images else int(bool(menu_item.get("image_url"))),
    }


def create_menu_ui_data(menu_data: dict) -> dict:
    """전체 메뉴를 음식·음료 탭과 원본 카테고리별로 구성한다."""
    menu_items = menu_data["items"]
    restaurant = menu_data.get("restaurant") or {}
    restaurant_id = restaurant.get("restaurant_id")
    tabs_by_type = {}
    categories_by_type = {}

    # V1.1: 기존 빈 화면은 음식·음료 두 탭을 유지하고, 실제 미분류 항목이
    # 있을 때만 세 번째 탭을 노출한다.
    visible_types = ["food", "beverage"]
    if any(item.get("item_type") == "unknown" for item in menu_items):
        visible_types.append("unknown")
    for item_type in visible_types:
        label_ko = TAB_LABELS[item_type]
        tabs_by_type[item_type] = {
            "tab_id": item_type,
            "label_ko": label_ko,
            "item_count": 0,
            "categories": [],
        }
        categories_by_type[item_type] = {}

    for menu_item in menu_items:
        item_type = menu_item.get("item_type")

        # 알 수 없는 분류를 조용히 제외하면 원본 메뉴가 사라질 수 있다.
        if item_type not in tabs_by_type:
            raise ValueError(f"지원하지 않는 item_type입니다: {item_type!r}")

        category_key = (
            menu_item.get("category_original"),
            menu_item.get("category_ko"),
        )
        type_categories = categories_by_type[item_type]

        if category_key not in type_categories:
            category_data = {
                "category_original": category_key[0],
                "category_ko": category_key[1],
                "items": [],
            }
            type_categories[category_key] = category_data
            tabs_by_type[item_type]["categories"].append(category_data)

        menu_card = create_menu_card(menu_item, restaurant_id)
        type_categories[category_key]["items"].append(menu_card)
        tabs_by_type[item_type]["item_count"] += 1

    provenance = menu_data.get("provenance") or {}

    return {
        "restaurant": menu_data.get("restaurant"),
        "source": {
            "url": provenance.get("source_url"),
            "extraction_method": provenance.get("extraction_method"),
            "dataset_status": menu_data.get("dataset_status"),
            "unique_product_count": provenance.get("unique_product_count"),
            "category_listing_count": provenance.get("category_listing_count"),
            "menu_source_id": provenance.get("menu_source_id"),
            "snapshot_id": provenance.get("snapshot_id"),
            "snapshot_version": provenance.get("snapshot_version"),
            "last_checked_at": provenance.get("last_checked_at"),
            "data_origin": provenance.get("data_origin"),
            "is_stale": bool(provenance.get("is_stale", False)),
            "refresh_status": provenance.get("refresh_status"),
            "validation_status": provenance.get("validation_status"),
        },
        "total_items": len(menu_items),
        "tabs": list(tabs_by_type.values()),
    }


def main() -> None:
    if len(sys.argv) != 2:
        script_name = Path(sys.argv[0]).name
        raise SystemExit(f"사용법: python3 {script_name} <메뉴 JSON 경로>")

    json_path = sys.argv[1]
    menu_data = load_menu_data(json_path)
    menu_ui_data = create_menu_ui_data(menu_data)
    restaurant = menu_ui_data["restaurant"] or {}

    print(f"식당: {restaurant.get('name')}")
    print(f"전체 메뉴 개수: {menu_ui_data['total_items']}")

    for tab in menu_ui_data["tabs"]:
        print(
            f"{tab['label_ko']} 탭: {tab['item_count']}개 메뉴, "
            f"{len(tab['categories'])}개 카테고리"
        )

    food_tab = menu_ui_data["tabs"][0]
    if food_tab["categories"] and food_tab["categories"][0]["items"]:
        first_category = food_tab["categories"][0]
        print(
            "첫 번째 카테고리: "
            f"{first_category['category_original']} / "
            f"{first_category['category_ko']}"
        )
        print("목록의 첫 번째 메뉴:")
        print(
            json.dumps(
                first_category["items"][0],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("음식 탭의 첫 번째 메뉴: 메뉴 목록이 비어 있습니다.")


if __name__ == "__main__":
    main()


# 학습 확인(실행되지 않는 주석):
# 1. TAB_LABELS["food"]의 값은 무엇일까?
# 2. bool([])과 bool([{"group": "sauce"}])의 결과는 각각 무엇일까?
# 3. append(menu_card) 대신 = menu_card를 쓰면 같은 카테고리의 메뉴가
#    하나씩 쌓이지 않는 이유는 무엇일까?
# 4. if __name__ = "__main__": 는 왜 올바른 조건문이 아닐까?
