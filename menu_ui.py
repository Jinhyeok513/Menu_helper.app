import json
import sys
from pathlib import Path

from data_load import load_menu_data


TAB_LABELS = {
    "food": "음식",
    "beverage": "음료",
}


def create_menu_card(menu_item: dict) -> dict:
    """메뉴 원본 한 건에서 목록 카드에 필요한 필드만 골라 반환한다."""
    return {
        "item_id": menu_item.get("item_id"),
        "name_original": menu_item.get("name_original"),
        "name_ko": menu_item.get("name_ko"),
        "price_aud": menu_item.get("price_aud"),
        "currency": menu_item.get("currency"),
        "one_line_description_ko": menu_item.get("taste_explanation_ko"),
        "has_options": bool(menu_item.get("options")),
        "image_url": menu_item.get("image_url"),
    }


def create_menu_ui_data(menu_data: dict) -> dict:
    """전체 메뉴를 음식·음료 탭과 원본 카테고리별로 구성한다."""
    menu_items = menu_data["items"]
    tabs_by_type = {}
    categories_by_type = {}

    for item_type, label_ko in TAB_LABELS.items():
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

        menu_card = create_menu_card(menu_item)
        type_categories[category_key]["items"].append(menu_card)
        tabs_by_type[item_type]["item_count"] += 1

    provenance = menu_data.get("provenance") or {}

    return {
        "restaurant": menu_data.get("restaurant"),
        "source": {
            "url": provenance.get("source_url"),
            "extraction_method": provenance.get("extraction_method"),
            "dataset_status": menu_data.get("dataset_status"),
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
