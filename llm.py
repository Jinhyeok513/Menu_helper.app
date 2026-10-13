import json
import os
import sys
from pathlib import Path

from groq import Groq

from data_load import load_menu_data
from find_menu import find_menu_by_id


MODEL_NAME = "openai/gpt-oss-20b"

EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string"},
        "source_id": {"type": "string"},
        "one_line_description_ko": {"type": "string"},
        "detailed_description_ko": {"type": "string"},
        "restaurant_facts_ko": {
            "type": "array",
            "items": {"type": "string"},
        },
        "general_food_knowledge_ko": {
            "type": "array",
            "items": {"type": "string"},
        },
        "inferences_ko": {
            "type": "array",
            "items": {"type": "string"},
        },
        "unverified_information_ko": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "item_id",
        "source_id",
        "one_line_description_ko",
        "detailed_description_ko",
        "restaurant_facts_ko",
        "general_food_knowledge_ko",
        "inferences_ko",
        "unverified_information_ko",
    ],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = """
당신은 식당 메뉴를 한국어로 이해하도록 돕는 설명 도우미입니다.

규칙:
- 입력된 메뉴 JSON만 현재 식당의 사실 근거로 사용하세요.
- item_id와 source_id를 입력값 그대로 복사하세요.
- ingredients_listed, ingredients_from_name, options에 없는 재료를 식당의
  실제 재료라고 단정하지 마세요.
- 일반적인 음식 지식은 restaurant_facts_ko가 아니라
  general_food_knowledge_ko에만 적으세요.
- 맛·향·식감의 추정은 inferences_ko에 적고 '~일 수 있어요'처럼
  추정임이 드러나게 표현하세요.
- review_note와 null 값은 확인되지 않은 정보로 처리하세요.
- 알레르기 안전 여부, 인기, 건강 효과를 만들지 마세요.
- 조리 과정이 아니라 주요 재료·소스와 맛·향·식감을 중심으로 설명하세요.
- 모든 설명 문장은 자연스러운 한국어로 작성하세요.
""".strip()


def generate_menu_explanation(menu_item: dict) -> dict:
    """메뉴 한 건을 Groq에 전달하고 구조화된 한국어 설명을 반환한다."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY 환경변수가 없습니다. API 키를 먼저 설정하세요."
        )

    client = Groq(api_key=api_key)
    menu_json = json.dumps(menu_item, ensure_ascii=False, indent=2)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": f"다음 메뉴를 설명하세요:\n{menu_json}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "menu_explanation",
                "strict": True,
                "schema": EXPLANATION_SCHEMA,
            },
        },
        reasoning_effort="low",
    )

    response_text = response.choices[0].message.content
    if response_text is None:
        raise ValueError("Groq 응답에 설명 내용이 없습니다.")

    explanation = json.loads(response_text)

    # 구조가 맞더라도 원본 식별자가 바뀌면 다른 메뉴의 설명으로 사용할 수 없다.
    if explanation["item_id"] != menu_item.get("item_id"):
        raise ValueError("LLM 응답의 item_id가 원본 메뉴와 일치하지 않습니다.")

    if explanation["source_id"] != menu_item.get("source_id"):
        raise ValueError("LLM 응답의 source_id가 원본 출처와 일치하지 않습니다.")

    return explanation


def main() -> None:
    if len(sys.argv) != 3:
        script_name = Path(sys.argv[0]).name
        raise SystemExit(
            f"사용법: python3 {script_name} <메뉴 JSON 경로> <item_id>"
        )

    json_path = sys.argv[1]
    item_id = sys.argv[2]

    menu_data = load_menu_data(json_path)
    menu_item = find_menu_by_id(menu_data, item_id)

    if menu_item is None:
        raise SystemExit(f"메뉴를 찾지 못했습니다: {item_id}")

    explanation = generate_menu_explanation(menu_item)
    print(json.dumps(explanation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


# 학습 확인(실행되지 않는 주석):
# 1. os.environ.get(____)의 빈칸에는 어떤 환경변수 이름이 들어갈까?
# 2. explanation["item_id"] = menu_item.get("item_id")는 왜 비교가 아닐까?
# 3. menu_item 대신 menu_data 전체를 모델에 보내면 어떤 문제가 생길까?
