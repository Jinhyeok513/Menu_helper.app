from pathlib import Path

from fastapi import FastAPI, HTTPException

from data_load import load_menu_data
from find_menu import find_menu_by_id, get_menu_items


app = FastAPI(title="menu-helper API")

# 현재 학습 단계에서는 확보된 정적 JSON을 서버 시작 시 한 번 읽는다.
MENU_JSON_PATH = (
    Path.home() / "Desktop" / "Menu_helper" / "Noelles_Cafe_Menu.json"
)
menu_data = load_menu_data(MENU_JSON_PATH)


@app.get("/menus")
def read_menus() -> list[dict]:
    """전체 메뉴 목록을 JSON 응답으로 반환한다."""
    return get_menu_items(menu_data)


@app.get("/menus/{item_id}")
def read_menu(item_id: str) -> dict:
    """item_id로 메뉴 하나를 찾아 JSON 응답으로 반환한다."""
    found_menu = find_menu_by_id(menu_data, item_id)

    if found_menu is None:
        # HTTP 404는 요청한 자원이 현재 목록에 없다는 의미다.
        raise HTTPException(
            status_code=404,
            detail=f"메뉴를 찾지 못했습니다: {item_id}",
        )

    return found_menu


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


# 학습 확인(실행되지 않는 주석):
# 1. @app.get("/menus/{____}")의 빈칸은 어느 함수 매개변수와 같아야 할까?
# 2. if found_menu = None: 는 왜 조건 비교가 되지 않을까?
# 3. 메뉴가 없을 때 200 대신 404를 반환하는 이유는 무엇일까?
