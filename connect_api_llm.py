import os

from fastapi import HTTPException
from groq import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field

from app_config import settings
from find_menu import find_menu_by_id
from llm import (
    MenuSelectionError,
    explanation_generation_metadata,
    generate_menu_explanation,
    generate_menu_one_line_description,
)
from menu_image_parser import VISION_PROMPT_VERSION, extract_menu_from_image
from menu_api import app, menu_data
from menu_ui import create_menu_detail, create_menu_ui_data
from menu_url_fetcher import (
    MenuPageFetchError,
    MenuURLValidationError,
    import_menu_item_detail_from_url,
)
from html_menu_parser import UnsupportedMenuPageError


class MenuSelectionRequest(BaseModel):
    variant_id: str | None = Field(default=None, max_length=200)
    choice_ids: list[str] = Field(default_factory=list, max_length=100)
    include_combination: bool = False


class URLMenuExplanationRequest(MenuSelectionRequest):
    url: str = Field(min_length=8, max_length=2048)


class MenuImageRequest(BaseModel):
    image_data_url: str = Field(min_length=32, max_length=14_000_000)


class ImageMenuExplanationRequest(MenuSelectionRequest):
    menu_item: dict


class MenuDescriptionItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=300)
    product_id: str = Field(min_length=1, max_length=300)
    source_product_id: str | None = Field(default=None, max_length=300)
    restaurant_id: str = Field(min_length=1, max_length=300)
    source_id: str = Field(min_length=1, max_length=300)
    category_original: str | None = Field(default=None, max_length=500)
    name_original: str = Field(min_length=1, max_length=500)
    name_ko: str | None = Field(default=None, max_length=500)
    description_original: str | None = Field(default=None, max_length=4000)
    ingredients_listed: list[str] = Field(default_factory=list, max_length=100)
    ingredients_from_name: list[str] = Field(default_factory=list, max_length=100)


class OneLineDescriptionRequest(BaseModel):
    menu_item: MenuDescriptionItem


def _generate_explanation_or_raise(
    menu_item: dict,
    selection: MenuSelectionRequest,
) -> dict:
    try:
        return generate_menu_explanation(
            menu_item,
            {
                "variant_id": selection.variant_id,
                "choice_ids": selection.choice_ids,
            },
            include_combination=selection.include_combination,
        )
    except MenuSelectionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except RateLimitError as error:
        raise HTTPException(
            status_code=429,
            detail="Groq 무료 사용 한도에 도달했습니다. 잠시 후 다시 시도하세요.",
        ) from error
    except APIConnectionError as error:
        raise HTTPException(
            status_code=502,
            detail="Groq API 서버에 연결하지 못했습니다.",
        ) from error
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Groq API가 오류 상태 {error.status_code}를 반환했습니다.",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _generate_one_line_or_raise(menu_item: dict) -> dict:
    try:
        return generate_menu_one_line_description(menu_item)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except RateLimitError as error:
        raise HTTPException(
            status_code=429,
            detail="Groq 무료 사용 한도에 도달했습니다. 잠시 후 다시 시도하세요.",
        ) from error
    except APIConnectionError as error:
        raise HTTPException(status_code=502, detail="Groq API 서버에 연결하지 못했습니다.") from error
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Groq API가 오류 상태 {error.status_code}를 반환했습니다.",
        ) from error
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/ai/config")
def read_ai_config() -> dict:
    """비밀값 없이 앱 캐시 갱신에 필요한 AI 버전과 사용 가능 여부만 반환한다."""
    return {
        "available": bool(os.environ.get("GROQ_API_KEY")),
        "descriptions": {
            kind: explanation_generation_metadata(kind)
            for kind in ("one_line", "detail", "combination")
        },
        "vision": {
            "model": settings.groq_vision_model,
            "prompt_version": VISION_PROMPT_VERSION,
        },
    }


@app.post("/menu-descriptions/one-line")
def create_one_line_description(request_data: OneLineDescriptionRequest) -> dict:
    """저장 JSON·URL·사진 목록 카드의 확인된 정보만 사용해 한 줄을 만든다."""
    menu_item = request_data.menu_item.model_dump()
    result = _generate_one_line_or_raise(menu_item)
    return {
        "description": result,
        "generation": explanation_generation_metadata("one_line"),
    }


@app.post("/menus/{item_id}/explanation")
def create_menu_explanation(
    item_id: str,
    request_data: MenuSelectionRequest | None = None,
) -> dict:
    """메뉴를 조회하고 Groq 설명을 생성해 하나의 응답으로 반환한다."""
    menu_item = find_menu_by_id(menu_data, item_id)

    if menu_item is None:
        raise HTTPException(
            status_code=404,
            detail=f"메뉴를 찾지 못했습니다: {item_id}",
        )

    detail = create_menu_detail(menu_item)
    explanation = _generate_explanation_or_raise(
        detail,
        request_data or MenuSelectionRequest(),
    )

    return {
        "menu": detail,
        "explanation": explanation,
        "generation": explanation_generation_metadata(
            "combination" if (request_data and request_data.include_combination) else "detail"
        ),
    }


@app.post("/menu-sources/url/items/{source_product_id}/explanation")
def create_imported_menu_explanation(
    source_product_id: str,
    request_data: URLMenuExplanationRequest,
) -> dict:
    """같은 식당 URL에서 상세를 다시 확인한 뒤 선택 조합을 설명한다."""
    try:
        menu_item = import_menu_item_detail_from_url(
            request_data.url,
            source_product_id,
        )
    except MenuURLValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except UnsupportedMenuPageError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MenuPageFetchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    explanation = _generate_explanation_or_raise(menu_item, request_data)
    return {
        "menu": menu_item,
        "explanation": explanation,
        "generation": explanation_generation_metadata(
            "combination" if request_data.include_combination else "detail"
        ),
    }


@app.post("/menu-sources/image")
def create_menu_from_image(request_data: MenuImageRequest) -> dict:
    """메뉴판 사진을 영구 저장하지 않고 Groq Vision OCR 결과를 반환한다."""
    try:
        imported_menu_data = extract_menu_from_image(request_data.image_data_url)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except RateLimitError as error:
        raise HTTPException(status_code=429, detail="Groq 사용 한도에 도달했습니다.") from error
    except APIConnectionError as error:
        raise HTTPException(status_code=502, detail="Groq API에 연결하지 못했습니다.") from error
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Groq API가 오류 상태 {error.status_code}를 반환했습니다.",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    details = {
        item["product_id"]: create_menu_detail(item)
        for item in imported_menu_data["items"]
    }
    return {
        "status": "ready",
        "menu": create_menu_ui_data(imported_menu_data),
        "details": details,
    }


@app.post("/menu-sources/image/items/explanation")
def create_image_menu_explanation(
    request_data: ImageMenuExplanationRequest,
) -> dict:
    """방금 OCR로 반환한 상품 데이터와 선택 조합을 설명한다."""
    menu_item = request_data.menu_item
    if menu_item.get("source_id") != "menu_photo_groq_vision":
        raise HTTPException(status_code=422, detail="메뉴 사진 OCR 상품만 지원합니다.")
    if not isinstance(menu_item.get("item_id"), str) or not isinstance(
        menu_item.get("product_id"), str
    ):
        raise HTTPException(status_code=422, detail="OCR 상품 식별자가 없습니다.")
    explanation = _generate_explanation_or_raise(menu_item, request_data)
    return {
        "menu": menu_item,
        "explanation": explanation,
        "generation": explanation_generation_metadata(
            "combination" if request_data.include_combination else "detail"
        ),
    }


if __name__ == "__main__":
    import uvicorn

    # 이전 코드: uvicorn.run(app, host="127.0.0.1", port=8000)
    # app_config에서 읽은 환경변수 설정을 통합 API 실행에도 동일하게 적용한다.
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


# 학습 확인(실행되지 않는 주석):
# 1. @app.____("/menus/{item_id}/explanation")에 POST를 사용한 이유는 뭘까?
# 2. raise HTTPException(...)과 return {...}은 실행 흐름이 어떻게 다를까?
# 3. 모든 예외를 except Exception 하나로 묶으면 어떤 원인을 구분하기 어려울까?
