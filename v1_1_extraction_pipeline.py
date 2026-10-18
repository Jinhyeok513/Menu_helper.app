"""V1.1 acquisition, common validation and artifact handoff pipeline.

``menu_api.py`` calls :func:`extract_menu_snapshot` with a validated URL. The
function reuses ``menu_url_fetcher.py`` for acquisition/parsing and returns the
common menu, validation status and bounded raw artifacts expected by
``v1_1_menu_store.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app_config import AppSettings, settings
from menu_url_fetcher import import_menu_from_url
from performance_metrics import record_performance_event


@dataclass(frozen=True)
class MenuExtractionResult:
    menu_data: dict
    artifacts: list[dict]
    extraction_status: str
    validation_status: str
    validation_warnings: tuple[str, ...]
    started_at: datetime


def validate_common_menu(menu_data: dict) -> tuple[str, str, tuple[str, ...]]:
    """Validate program usability without inventing unknown menu facts."""
    items = menu_data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("추출 결과에 사용할 수 있는 메뉴 항목이 없습니다.")
    warnings: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise TypeError(f"메뉴 {index}번 항목이 딕셔너리가 아닙니다.")
        if not isinstance(item.get("name_original"), str) or not item[
            "name_original"
        ].strip():
            raise ValueError(f"메뉴 {index}번 항목의 원문 이름이 없습니다.")
        if item.get("price_amount") is None and item.get("price_aud") is None:
            warnings.append("price_unknown")
        if item.get("currency") is None:
            warnings.append("currency_unknown")
        if item.get("item_type") == "unknown":
            warnings.append("item_type_unknown")
        if item.get("category_original") in {None, "", "Uncategorised"}:
            warnings.append("category_unknown")
        if item.get("option_status") == "none" and not item.get(
            "options_checked"
        ):
            warnings.append("option_none_without_evidence")

    unique_warnings = tuple(sorted(set(warnings)))
    extraction_status = "partial" if unique_warnings else "success"
    validation_status = "needs_review" if unique_warnings else "passed"
    return extraction_status, validation_status, unique_warnings


def extract_menu_snapshot(
    url: str,
    app_settings: AppSettings = settings,
) -> MenuExtractionResult:
    started_at = datetime.now(UTC)
    artifacts: list[dict] = []
    menu_data = import_menu_from_url(
        url,
        app_settings,
        artifact_collector=artifacts,
    )
    validation_started_at = datetime.now(UTC)
    extraction_status, validation_status, warnings = validate_common_menu(menu_data)
    provenance = menu_data.setdefault("provenance", {})
    provenance["validation_status"] = validation_status
    provenance["validation_warnings"] = list(warnings)
    menu_data["dataset_status"] = (
        "extracted_partial" if extraction_status == "partial" else "extracted"
    )
    record_performance_event(
        component="backend",
        event="menu_validation",
        operation="url_menu_import",
        outcome="success",
        duration_ms=(datetime.now(UTC) - validation_started_at).total_seconds() * 1000,
        item_count=len(menu_data["items"]),
        stage="validation",
        validation_status=validation_status,
        measurement_method="common_menu_rules",
    )
    return MenuExtractionResult(
        menu_data=menu_data,
        artifacts=artifacts,
        extraction_status=extraction_status,
        validation_status=validation_status,
        validation_warnings=warnings,
        started_at=started_at,
    )
