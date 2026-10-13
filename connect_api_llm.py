from fastapi import HTTPException
from groq import APIConnectionError, APIStatusError, RateLimitError

from find_menu import find_menu_by_id
from llm import generate_menu_explanation
from menu_api import app, menu_data


@app.post("/menus/{item_id}/explanation")
def create_menu_explanation(item_id: str) -> dict:
    """메뉴를 조회하고 Groq 설명을 생성해 하나의 응답으로 반환한다."""
    menu_item = find_menu_by_id(menu_data, item_id)

    if menu_item is None:
        raise HTTPException(
            status_code=404,
            detail=f"메뉴를 찾지 못했습니다: {item_id}",
        )

    try:
        explanation = generate_menu_explanation(menu_item)
    except RuntimeError as error:
        # 서버에 API 키가 없는 상태는 사용자의 잘못된 메뉴 요청과 구분한다.
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
        # JSON 파싱 또는 원본 item_id·source_id 검증 실패를 외부 응답 오류로 표시한다.
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "menu": menu_item,
        "explanation": explanation,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


# 학습 확인(실행되지 않는 주석):
# 1. @app.____("/menus/{item_id}/explanation")에 POST를 사용한 이유는 뭘까?
# 2. raise HTTPException(...)과 return {...}은 실행 흐름이 어떻게 다를까?
# 3. 모든 예외를 except Exception 하나로 묶으면 어떤 원인을 구분하기 어려울까?
