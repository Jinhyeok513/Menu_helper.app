import base64
import binascii
import hashlib
import json
import os
from datetime import UTC, datetime

from groq import Groq

from app_config import settings

VISION_MODEL_NAME = settings.groq_vision_model
VISION_PROMPT_VERSION = "menu-photo-ocr-v1"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}

MENU_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "restaurant_name": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category_original": {"type": "string"},
                    "item_type": {"type": "string", "enum": ["food", "beverage"]},
                    "name_original": {"type": "string"},
                    "description_original": {"type": ["string", "null"]},
                    "price": {"type": ["number", "null"]},
                },
                "required": [
                    "category_original",
                    "item_type",
                    "name_original",
                    "description_original",
                    "price",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["restaurant_name", "currency", "items"],
    "additionalProperties": False,
}

VISION_INSTRUCTIONS = """
사진에 실제로 보이는 식당 메뉴 텍스트만 읽어 JSON으로 반환하세요.

규칙:
- 보이지 않는 메뉴, 옵션, 가격, 재료를 만들지 마세요.
- 원문의 메뉴명, 카테고리, 표시 순서를 유지하세요.
- 가격을 읽을 수 없으면 null로 두세요.
- 통화를 확실히 확인할 수 없으면 null로 두세요.
- 설명이 없으면 description_original을 null로 두세요.
- 음료로 명확히 보이는 항목만 beverage, 나머지는 food로 분류하세요.
- 머리글, 주문 번호, 영업 안내는 메뉴 항목으로 만들지 마세요.
- OCR 결과는 검토가 필요하므로 철자를 임의로 교정하지 마세요.
""".strip()


def validate_image_data_url(image_data_url: str) -> tuple[str, bytes]:
    """허용한 이미지 data URL인지 확인하고 원본 바이트를 반환한다."""
    if not isinstance(image_data_url, str) or not image_data_url.startswith("data:"):
        raise ValueError("메뉴 사진은 data URL 형식이어야 합니다.")
    try:
        header, encoded_image = image_data_url.split(",", maxsplit=1)
        media_type, encoding = header[5:].split(";", maxsplit=1)
    except (binascii.Error, ValueError) as error:
        raise ValueError("메뉴 사진 data URL 형식이 올바르지 않습니다.") from error
    if media_type not in ALLOWED_IMAGE_MEDIA_TYPES or encoding != "base64":
        raise ValueError("JPEG, PNG 또는 WebP 메뉴 사진만 지원합니다.")
    try:
        image_bytes = base64.b64decode(encoded_image, validate=True)
    except ValueError as error:
        raise ValueError("메뉴 사진의 base64 데이터를 읽지 못했습니다.") from error
    if not image_bytes:
        raise ValueError("메뉴 사진이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("메뉴 사진은 10MB 이하여야 합니다.")
    return media_type, image_bytes


def build_menu_data_from_ocr(
    ocr_result: object,
    image_digest: str,
) -> dict:
    """검증 전 OCR 결과를 기존 공통 메뉴 데이터 구조로 변환한다."""
    if not isinstance(ocr_result, dict):
        raise ValueError("OCR 응답이 딕셔너리가 아닙니다.")
    raw_items = ocr_result.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("메뉴 사진에서 메뉴 항목을 찾지 못했습니다.")

    restaurant_name = ocr_result.get("restaurant_name")
    restaurant_name = (
        restaurant_name.strip()
        if isinstance(restaurant_name, str) and restaurant_name.strip()
        else "사진에서 읽은 메뉴"
    )
    currency = ocr_result.get("currency")
    currency = currency.strip().upper() if isinstance(currency, str) else None
    restaurant_id = f"photo_{image_digest[:16]}"
    retrieved_at = datetime.now(UTC).isoformat()
    items = []

    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        name = raw_item.get("name_original")
        category = raw_item.get("category_original")
        item_type = raw_item.get("item_type")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(category, str) or not category.strip():
            category = "Menu"
        if item_type not in {"food", "beverage"}:
            raise ValueError(f"지원하지 않는 OCR item_type입니다: {item_type!r}")
        price = raw_item.get("price")
        if not isinstance(price, int | float):
            price = None

        item_id = f"{restaurant_id}_{index:03d}"
        items.append(
            {
                "item_id": item_id,
                "item_id_source": "generated_from_image_digest_and_order",
                "product_id": item_id,
                "source_product_id": None,
                "restaurant_id": restaurant_id,
                "item_type": item_type,
                "category_original": category.strip(),
                "category_ko": None,
                "name_original": name.strip(),
                "name_ko": None,
                "description_original": raw_item.get("description_original"),
                "price_aud": price,
                "price_max_aud": None,
                "currency": currency,
                "ingredients_listed": [],
                "ingredients_listed_ko": [],
                "ingredients_from_name": [],
                "ingredient_coverage": "unknown",
                "options": [],
                "option_status": "not_checked",
                "variants": [],
                "variant_status": "not_checked",
                "option_note": None,
                "review_note": "메뉴 사진 OCR 결과이며 원본 사진과 대조가 필요합니다.",
                "source_id": "menu_photo_groq_vision",
                "source_url": None,
                "source_menu_type": "menu_photo_ocr",
                "source_menu_updated_at": None,
                "retrieved_at": retrieved_at,
                "google_menu_match_verified": False,
                "taste_explanation_ko": None,
                "allergen_safety": None,
                "image_url": None,
                "images": [],
                "image_status": "not_checked",
            }
        )

    if not items:
        raise ValueError("메뉴 사진에서 사용할 수 있는 메뉴 항목을 찾지 못했습니다.")
    return {
        "schema_version": "1.0",
        "dataset_status": "ocr_extracted_unverified",
        "restaurant": {"restaurant_id": restaurant_id, "name": restaurant_name},
        "provenance": {
            "source_url": None,
            "extraction_method": "groq_vision_menu_photo_ocr",
            "retrieved_at": retrieved_at,
            "image_digest": image_digest,
            "limitations_ko": [
                "메뉴 사진 OCR 결과이며 이름·가격·순서를 원본 사진과 대조해야 합니다.",
                "사진에서 확인하지 못한 옵션·재료·알레르기 정보는 추가하지 않았습니다.",
                "업로드된 이미지 파일은 menu-helper가 영구 저장하지 않습니다.",
            ],
        },
        "counts": {
            "food": sum(item["item_type"] == "food" for item in items),
            "beverage": sum(item["item_type"] == "beverage" for item in items),
            "total": len(items),
        },
        "items": items,
    }


def extract_menu_from_image(image_data_url: str) -> dict:
    """메뉴 사진을 Groq Vision에 보내고 검토 전 공통 메뉴 데이터를 반환한다."""
    _, image_bytes = validate_image_data_url(image_data_url)
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY 환경변수가 없어 메뉴 사진을 분석할 수 없습니다."
        )

    client = Groq(
        api_key=api_key,
        timeout=settings.groq_timeout_seconds,
        max_retries=settings.groq_max_retries,
    )
    response = client.chat.completions.create(
        model=VISION_MODEL_NAME,
        messages=[
            {"role": "system", "content": VISION_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "이 메뉴판의 메뉴를 구조화하세요."},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "menu_photo_ocr",
                "strict": True,
                "schema": MENU_IMAGE_SCHEMA,
            },
        },
        reasoning_effort="low",
    )
    response_text = response.choices[0].message.content
    if response_text is None:
        raise ValueError("Groq Vision 응답에 OCR 결과가 없습니다.")
    image_digest = hashlib.sha256(image_bytes).hexdigest()
    return build_menu_data_from_ocr(json.loads(response_text), image_digest)
