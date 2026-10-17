import json
import sys
from pathlib import Path


def load_menu_data(json_path: str | Path) -> dict:
    """메뉴 JSON을 읽고 기본 구조를 확인한 뒤 전체 데이터를 반환한다."""
    menu_path = Path(json_path)

    with menu_path.open("r", encoding="utf-8") as menu_file:
        menu_data = json.load(menu_file)

    if not isinstance(menu_data, dict):
        raise TypeError("최상위 데이터는 딕셔너리여야 합니다.") # raise 와 return 차이

    if "items" not in menu_data:
        raise KeyError("최상위 데이터에 'items' 키가 없습니다.")

    menu_items = menu_data["items"]
    if not isinstance(menu_items, list):
        raise TypeError("'items' 값은 리스트여야 합니다.")

    for item_index, menu_item in enumerate(menu_items):
        if not isinstance(menu_item, dict):
            raise TypeError(
                f"items[{item_index}] 메뉴 항목은 딕셔너리여야 합니다."
            )

    # 메뉴 목록만 반환하면 식당과 출처 정보가 사라지므로 전체 딕셔너리를 반환한다.(Codex) -> 내 질문: 어디서 식당과 출처 정보가 있는거지?
    return menu_data

def main() -> None:
    if len(sys.argv) != 2:
        script_name = Path(sys.argv[0]).name
        raise SystemExit(f"사용법: python3 {script_name} <메뉴 JSON 경로>")

    json_path = sys.argv[1]
    menu_data = load_menu_data(json_path)
    menu_items = menu_data["items"]

    print(f"메뉴 개수: {len(menu_items)}")

    # 빈 목록일 때 items[0]을 실행하지 않아 IndexError를 방지한다.
    if menu_items:
        print("첫 번째 메뉴:")
        print(json.dumps(menu_items[0], ensure_ascii=False, indent=2))
    else:
        print("첫 번째 메뉴: 메뉴 목록이 비어 있습니다.")


if __name__ == "__main__":
    main()


# 학습 확인(실행되지 않는 주석):
# 1. isinstance(menu_data, ____)의 빈칸에는 어떤 자료형이 들어가야 할까?
# 2. if __name__ = "__main__": 는 왜 올바른 조건문이 아닐까?
