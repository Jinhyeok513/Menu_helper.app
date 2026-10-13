import json
import sys
from pathlib import Path

from data_load import load_menu_data


def get_menu_items(menu_data: dict) -> list[dict]:
    """전체 메뉴 딕셔너리에서 메뉴 항목 리스트를 반환한다."""
    return menu_data["items"]


def find_menu_by_id(menu_data: dict, item_id: str) -> dict | None:
    """item_id가 일치하는 메뉴를 반환하고, 없으면 None을 반환한다."""
    menu_items = get_menu_items(menu_data)

    for menu_item in menu_items:
        if menu_item.get("item_id") == item_id:
            # 원하는 메뉴를 찾았으므로 나머지 항목은 확인하지 않아도 된다.
            return menu_item

    # 찾지 못한 상태와 빈 딕셔너리를 구분하기 위해 None을 반환한다.
    return None


def main() -> None:
    if len(sys.argv) != 3:
        script_name = Path(sys.argv[0]).name
        raise SystemExit(
            f"사용법: python3 {script_name} <메뉴 JSON 경로> <item_id>"
        )

    json_path = sys.argv[1]
    item_id = sys.argv[2]

    menu_data = load_menu_data(json_path)
    menu_items = get_menu_items(menu_data)
    found_menu = find_menu_by_id(menu_data, item_id)

    print(f"전체 메뉴 개수: {len(menu_items)}")

    if found_menu is None:
        print(f"메뉴를 찾지 못했습니다: {item_id}")
    else:
        print("찾은 메뉴:")
        print(json.dumps(found_menu, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


# 학습 확인(실행되지 않는 주석):
# 1. menu_item.get(____)의 빈칸에는 어떤 키가 들어가야 할까?
# 2. if found_menu = None: 는 왜 올바른 조건문이 아닐까?
# 3. 메뉴가 없을 때 빈 딕셔너리 {} 대신 None을 반환한 이유는 무엇일까?
