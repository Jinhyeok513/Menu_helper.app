import json
import os
import sys
from pathlib import Path
from time import perf_counter

from groq import Groq

from app_config import settings
from data_load import load_menu_data
from find_menu import find_menu_by_id
from menu_ui import create_menu_detail
from performance_metrics import record_performance_event


MODEL_NAME = settings.groq_text_model
ONE_LINE_PROMPT_VERSION = "menu-one-line-ko-v2"
DETAIL_PROMPT_VERSION = "menu-detail-ko-v2"
COMBINATION_PROMPT_VERSION = "menu-combination-ko-v2"


class MenuSelectionError(ValueError):
    """현재 상품에 존재하지 않거나 선택 제한을 어긴 조합이다."""


ONE_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "one_line_description_ko": {"type": "string"},
        "restaurant_facts_ko": {"type": "array", "items": {"type": "string"}},
        "general_food_knowledge_ko": {
            "type": "array",
            "items": {"type": "string"},
        },
        "inferences_ko": {"type": "array", "items": {"type": "string"}},
        "unverified_information_ko": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "one_line_description_ko",
        "restaurant_facts_ko",
        "general_food_knowledge_ko",
        "inferences_ko",
        "unverified_information_ko",
    ],
    "additionalProperties": False,
}

EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
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
        "option_descriptions_ko": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description_ko": {"type": "string"},
                    "basis": {
                        "type": "string",
                        "enum": [
                            "restaurant_fact",
                            "general_food_knowledge",
                            "inference",
                        ],
                    },
                },
                "required": ["description_ko", "basis"],
                "additionalProperties": False,
            },
        },
        "combination_description_ko": {"type": ["string", "null"]},
    },
    "required": [
        "one_line_description_ko",
        "detailed_description_ko",
        "restaurant_facts_ko",
        "general_food_knowledge_ko",
        "inferences_ko",
        "unverified_information_ko",
        "option_descriptions_ko",
        "combination_description_ko",
    ],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = """
당신은 식당 메뉴를 한국어로 이해하도록 돕는 설명 도우미입니다.

규칙:
- 입력된 메뉴 JSON만 현재 식당의 사실 근거로 사용하세요.
- 식별자는 서버가 관리하므로 item_id, source_id, product_id, variant_id,
  choice_id를 출력하지 마세요.
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
- option_descriptions_ko에는 selected_options.choices와 같은 순서로 각 선택지를
  한 줄씩 설명하세요. 선택지마다 정확히 하나의 설명을 작성하세요.
- 선택하지 않은 옵션이나 존재하지 않는 조합을 설명하지 마세요.
- combination_description_ko는 선택 조합이 있을 때만 짧은 한두 문장으로 쓰세요.
- 옵션 특징의 근거가 식당 원문인지, 일반 음식 지식인지, 추정인지 basis로 구분하세요.
- 가격을 계산하거나 식당이 보장하지 않은 조합 결과를 확정적으로 말하지 마세요.
""".strip()

ONE_LINE_SYSTEM_INSTRUCTIONS = """
당신은 낯선 식당 메뉴의 맛·향·식감을 한국어 한 문장으로 쉽게 설명합니다.

규칙:
- 입력 JSON만 현재 식당이 확인한 사실로 사용하세요.
- 식별자는 서버가 관리하므로 item_id, source_id, product_id를 출력하지 마세요.
- 메뉴명과 description_original, ingredients 필드에 실제로 있는 정보를 우선 사용하세요.
- 정보가 부족하면 일반 음식 지식이나 가능성임을 문장에 드러내고 재료를 만들지 마세요.
- 알레르기 안전, 건강 효과, 인기, 가격, 조리 과정을 만들지 마세요.
- one_line_description_ko는 짧고 자연스러운 한 문장으로 작성하세요.
- 식당 사실, 일반 음식 지식, 추정, 미확인 정보는 각각의 배열에 구분하세요.
""".strip()


def explanation_generation_metadata(kind: str) -> dict:
    """클라이언트 캐시가 모델·프롬프트 변경을 구분할 공개 메타데이터다."""
    versions = {
        "one_line": ONE_LINE_PROMPT_VERSION,
        "detail": DETAIL_PROMPT_VERSION,
        "combination": COMBINATION_PROMPT_VERSION,
    }
    if kind not in versions:
        raise ValueError(f"지원하지 않는 설명 종류입니다: {kind}")
    return {
        "language": "ko",
        "kind": kind,
        "model": MODEL_NAME,
        "prompt_version": versions[kind],
    }


def _create_client(api_key: str) -> Groq:
    return Groq(
        api_key=api_key,
        timeout=settings.groq_timeout_seconds,
        max_retries=settings.groq_max_retries,
    )


def _require_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY가 없습니다. 백엔드 루트 .env에 키를 설정하세요."
        )
    return api_key


def _usage_value(usage: object | None, field_name: str) -> int | None:
    value = getattr(usage, field_name, None)
    return value if isinstance(value, int) else None


def _create_measured_completion(
    *,
    client: Groq,
    operation: str,
    prompt_version: str,
    messages: list[dict],
    schema_name: str,
    schema: dict,
):
    """한 번의 Groq 호출 시간·결과·토큰만 기록하고 본문은 기록하지 않는다."""
    started_at = perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            reasoning_effort="low",
        )
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        error_name = type(error).__name__
        is_rate_limited = status_code == 429 or error_name == "RateLimitError"
        is_timeout = "timeout" in error_name.lower()
        record_performance_event(
            component="backend",
            event="llm_call",
            operation=operation,
            outcome=(
                "rate_limited"
                if is_rate_limited
                else "timeout"
                if is_timeout
                else "failure"
            ),
            duration_ms=(perf_counter() - started_at) * 1000,
            model=MODEL_NAME,
            prompt_version=prompt_version,
            http_status=status_code if isinstance(status_code, int) else None,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            error_type=error_name,
            retry_count=0 if settings.groq_max_retries == 0 else None,
            retry_limit=settings.groq_max_retries,
            timeout=is_timeout,
            rate_limited=is_rate_limited,
            concurrency=1,
            measurement_method="groq_sdk_completion",
        )
        raise

    usage = getattr(response, "usage", None)
    record_performance_event(
        component="backend",
        event="llm_call",
        operation=operation,
        outcome="success",
        duration_ms=(perf_counter() - started_at) * 1000,
        model=MODEL_NAME,
        prompt_version=prompt_version,
        http_status=200,
        input_tokens=_usage_value(usage, "prompt_tokens"),
        output_tokens=_usage_value(usage, "completion_tokens"),
        total_tokens=_usage_value(usage, "total_tokens"),
        retry_count=0 if settings.groq_max_retries == 0 else None,
        retry_limit=settings.groq_max_retries,
        timeout=False,
        rate_limited=False,
        concurrency=1,
        measurement_method="groq_sdk_completion",
    )
    return response


def generate_menu_one_line_description(menu_item: dict) -> dict:
    """목록을 막지 않고 개별 호출할 수 있는 짧은 설명 하나를 생성한다."""
    required_identifiers = ("item_id", "source_id", "product_id")
    if any(not isinstance(menu_item.get(name), str) for name in required_identifiers):
        raise ValueError("목록 설명에 필요한 메뉴 식별자가 없습니다.")

    response = _create_measured_completion(
        client=_create_client(_require_api_key()),
        operation="one_line_description",
        prompt_version=ONE_LINE_PROMPT_VERSION,
        messages=[
            {"role": "system", "content": ONE_LINE_SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": (
                    "다음 메뉴를 한국어 한 문장으로 설명하세요:\n"
                    + json.dumps(menu_item, ensure_ascii=False, indent=2)
                ),
            },
        ],
        schema_name="menu_one_line_description",
        schema=ONE_LINE_SCHEMA,
    )
    response_text = response.choices[0].message.content
    if response_text is None:
        raise ValueError("Groq 응답에 한 줄 설명이 없습니다.")
    result = json.loads(response_text)
    if not result["one_line_description_ko"].strip():
        raise ValueError("Groq 응답의 한 줄 설명이 비어 있습니다.")
    # 식별자는 생성 모델이 복사하지 않는다. 검증된 원본 값만 서버가 결합한다.
    for field_name in ("item_id", "source_id", "product_id"):
        result[field_name] = menu_item[field_name]
    return result


def validate_menu_selection(menu_item: dict, selection: dict | None) -> dict:
    """사용자가 고른 ID가 현재 상품에 실제로 존재하고 제한을 지키는지 확인한다."""
    selection = selection or {}
    selected_variant_id = selection.get("variant_id")
    selected_choice_ids = selection.get("choice_ids") or []
    if selected_variant_id is not None and not isinstance(selected_variant_id, str):
        raise MenuSelectionError("variant_id는 문자열 또는 null이어야 합니다.")
    if not isinstance(selected_choice_ids, list) or not all(
        isinstance(choice_id, str) for choice_id in selected_choice_ids
    ):
        raise MenuSelectionError("choice_ids는 문자열 리스트여야 합니다.")
    if len(selected_choice_ids) != len(set(selected_choice_ids)):
        raise MenuSelectionError("같은 옵션 선택지를 중복해서 선택할 수 없습니다.")

    variants = menu_item.get("variants") or []
    variants_by_id = {
        variant.get("variant_id"): variant
        for variant in variants
        if isinstance(variant, dict) and isinstance(variant.get("variant_id"), str)
    }
    if selected_variant_id is not None:
        selected_variant = variants_by_id.get(selected_variant_id)
        if selected_variant is None:
            raise MenuSelectionError("현재 상품에 없는 변형 ID입니다.")
        if selected_variant.get("sold_out"):
            raise MenuSelectionError("품절된 상품 변형은 선택할 수 없습니다.")
    elif len(variants_by_id) > 1:
        raise MenuSelectionError("상품 사이즈 또는 변형을 하나 선택해야 합니다.")

    option_groups = [
        group
        for group in menu_item.get("options") or []
        if isinstance(group, dict)
    ]
    known_choice_ids = {
        choice.get("choice_id")
        for group in option_groups
        for choice in group.get("choices") or []
        if isinstance(choice, dict)
        and isinstance(choice.get("choice_id"), str)
        and not choice.get("hidden")
    }
    unknown_ids = set(selected_choice_ids) - known_choice_ids
    if unknown_ids:
        raise MenuSelectionError(
            f"현재 상품에 없는 옵션 ID입니다: {sorted(unknown_ids)}"
        )

    selected_choices = []
    for group in option_groups:
        group_choices = {
            choice.get("choice_id"): choice
            for choice in group.get("choices") or []
            if isinstance(choice, dict)
            and isinstance(choice.get("choice_id"), str)
            and not choice.get("hidden")
        }
        group_selected_ids = [
            choice_id for choice_id in selected_choice_ids if choice_id in group_choices
        ]
        minimum = group.get("min_selected")
        maximum = group.get("max_selected")
        if isinstance(minimum, int | float) and len(group_selected_ids) < minimum:
            raise MenuSelectionError(
                f"{group.get('name_original') or '옵션'}에서 최소 {minimum}개를 선택해야 합니다."
            )
        if isinstance(maximum, int | float) and len(group_selected_ids) > maximum:
            raise MenuSelectionError(
                f"{group.get('name_original') or '옵션'}에서는 최대 {maximum}개만 선택할 수 있습니다."
            )
        for choice_id in group_selected_ids:
            choice = group_choices[choice_id]
            if choice.get("sold_out"):
                raise MenuSelectionError("품절된 옵션 선택지는 선택할 수 없습니다.")
            selected_choices.append(
                {
                    "group_id": group.get("group_id"),
                    "group_name": group.get("name_original"),
                    "choice_id": choice_id,
                    "choice_name": choice.get("name_original"),
                    "price_delta_aud": choice.get("price_delta_aud"),
                    "price_status": choice.get("price_status"),
                }
            )

    selected_variant = variants_by_id.get(selected_variant_id)
    return {
        "variant_id": selected_variant_id,
        "variant": (
            {
                "variant_id": selected_variant_id,
                "name": selected_variant.get("name_original"),
                "price_aud": selected_variant.get("price_aud"),
                "price_kind": selected_variant.get("price_kind"),
            }
            if selected_variant is not None
            else None
        ),
        "choice_ids": selected_choice_ids,
        "choices": selected_choices,
    }


def generate_menu_explanation(
    menu_item: dict,
    selection: dict | None = None,
    *,
    include_combination: bool = False,
) -> dict:
    """메뉴 한 건을 Groq에 전달하고 구조화된 한국어 설명을 반환한다."""
    # 상세 설명은 필수 옵션을 고르기 전에도 열려야 한다. 조합 요청일 때만
    # 현재 상품의 변형·옵션 ID와 최소/최대 선택 수를 엄격히 검사한다.
    validated_selection = (
        validate_menu_selection(menu_item, selection)
        if include_combination
        else {"variant_id": None, "variant": None, "choice_ids": [], "choices": []}
    )
    client = _create_client(_require_api_key())
    request_data = {
        "menu": menu_item,
        "selected_options": validated_selection,
    }
    menu_json = json.dumps(request_data, ensure_ascii=False, indent=2)

    request_kind = "combination" if include_combination else "detail"
    mode_instruction = (
        "실제 선택 조합을 함께 설명하세요."
        if include_combination
        else (
            "기본 메뉴의 상세 맛 설명만 작성하세요. 선택 옵션 배열과 "
            "option_descriptions_ko는 비우고 combination_description_ko는 null로 두세요."
        )
    )
    response = _create_measured_completion(
        client=client,
        operation=(
            "combination_explanation" if include_combination else "detail_explanation"
        ),
        prompt_version=(
            COMBINATION_PROMPT_VERSION if include_combination else DETAIL_PROMPT_VERSION
        ),
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": f"{mode_instruction}\n설명 종류: {request_kind}\n{menu_json}",
            },
        ],
        schema_name="menu_explanation",
        schema=EXPLANATION_SCHEMA,
    )

    response_text = response.choices[0].message.content
    if response_text is None:
        raise ValueError("Groq 응답에 설명 내용이 없습니다.")

    explanation = json.loads(response_text)

    option_descriptions = explanation["option_descriptions_ko"]
    selected_choice_ids = validated_selection["choice_ids"]
    if len(option_descriptions) != len(selected_choice_ids):
        raise ValueError(
            "LLM 옵션 설명 개수가 실제 선택한 옵션 개수와 일치하지 않습니다."
        )

    if not include_combination and explanation["combination_description_ko"] is not None:
        raise ValueError("기본 상세 설명에 옵션 조합 설명이 포함되었습니다.")

    # LLM에는 설명만 맡긴다. 메뉴·선택 식별자는 검증된 서버 데이터에서 결합하므로
    # 긴 ID를 모델이 잘못 복사해 다른 상품과 연결하는 경로 자체가 없다.
    for field_name in ("item_id", "source_id", "product_id"):
        explanation[field_name] = menu_item[field_name]
    explanation["selected_variant_id"] = validated_selection["variant_id"]
    explanation["selected_choice_ids"] = selected_choice_ids.copy()
    explanation["option_descriptions_ko"] = [
        {"choice_id": choice_id, **description}
        for choice_id, description in zip(
            selected_choice_ids,
            option_descriptions,
            strict=True,
        )
    ]

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

    # 단독 실행도 API와 같은 상세 구조를 사용해야 옵션 상태와 식별자가 같다.
    menu_detail = create_menu_detail(menu_item)
    explanation = generate_menu_explanation(menu_detail)
    print(json.dumps(explanation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


# 학습 확인(실행되지 않는 주석):
# 1. os.environ.get(____)의 빈칸에는 어떤 환경변수 이름이 들어갈까?
# 2. explanation["item_id"] = menu_item.get("item_id")는 왜 비교가 아닐까?
# 3. menu_item 대신 menu_data 전체를 모델에 보내면 어떤 문제가 생길까?
