from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app_config import settings
from data_load import load_menu_data
from find_menu import find_menu_by_id
from html_menu_parser import UnsupportedMenuPageError
from menu_ui import create_menu_detail, create_menu_ui_data
from menu_url_fetcher import (
    MenuPageFetchError,
    MenuURLValidationError,
    import_menu_from_url,
    import_menu_item_detail_from_url,
)


app = FastAPI(title="menu-helper API")

# 현재 학습 단계에서는 확보된 정적 JSON을 서버 시작 시 한 번 읽는다.
menu_data = load_menu_data(settings.menu_json_path)


class MenuURLRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


@app.get("/health")
def read_health() -> dict:
    """앱이 백엔드 연결 여부를 가볍게 확인할 때 사용한다."""
    return {"status": "ok"}


@app.get("/menus")
def read_menus() -> dict:
    """정적 JSON을 음식·음료 탭용 목록 구조로 반환한다."""
    return create_menu_ui_data(menu_data)


@app.post("/menu-sources/url")
def create_menu_from_url(request_data: MenuURLRequest) -> dict:
    """검증된 URL의 HTML 메뉴를 읽어 같은 목록 구조로 반환한다."""
    try:
        imported_menu_data = import_menu_from_url(request_data.url)
    except MenuURLValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except UnsupportedMenuPageError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MenuPageFetchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "status": "ready",
        "menu": create_menu_ui_data(imported_menu_data),
    }


@app.post("/menu-sources/url/items/{source_product_id}")
def read_imported_menu_item(
    source_product_id: str,
    request_data: MenuURLRequest,
) -> dict:
    """URL과 원본 상품 ID를 함께 사용해 해당 식당의 상세를 다시 조회한다."""
    try:
        product = import_menu_item_detail_from_url(
            request_data.url,
            source_product_id,
        )
    except MenuURLValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except UnsupportedMenuPageError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MenuPageFetchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "status": "ready",
        "source": {
            "url": product["source_url"],
            "restaurant_id": product["restaurant_id"],
            "source_product_id": product["source_product_id"],
        },
        "product": product,
    }


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

    return create_menu_detail(found_menu)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


# 학습 확인(실행되지 않는 주석):
# 1. @app.get("/menus/{____}")의 빈칸은 어느 함수 매개변수와 같아야 할까?
# 2. if found_menu = None: 는 왜 조건 비교가 되지 않을까?
# 3. 메뉴가 없을 때 200 대신 404를 반환하는 이유는 무엇일까?
