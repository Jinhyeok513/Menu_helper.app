from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app_config import settings
from data_load import load_menu_data
from find_menu import find_menu_by_id
from html_menu_parser import UnsupportedMenuPageError
from menu_ui import create_menu_detail, create_menu_ui_data
from menu_url_fetcher import (
    MenuPageFetchError,
    MenuURLValidationError,
    import_menu_item_detail_from_url,
)
from performance_metrics import (
    bind_request_id,
    current_request_id,
    normalise_request_id,
    performance_log_enabled,
    record_performance_event,
    reset_request_id,
)
from v1_1_extraction_pipeline import extract_menu_snapshot
from v1_1_menu_store import (
    MenuDatabaseError,
    MenuDatabaseNotConfiguredError,
    MenuDatabaseSchemaError,
    MenuDatabaseUnavailableError,
    MenuStore,
)


app = FastAPI(title="menu-helper API")


def _empty_stored_menu_data(dataset_status: str) -> dict:
    """저장 JSON이 없어도 URL 메뉴 API가 시작될 수 있는 빈 공통 구조다."""
    return {
        "restaurant": None,
        "items": [],
        "dataset_status": dataset_status,
        "provenance": {
            "source_url": None,
            "extraction_method": None,
            "unique_product_count": 0,
            "category_listing_count": 0,
        },
    }


def _load_configured_menu_data() -> dict:
    """MENU_JSON_PATH가 있고 실제 파일이 있을 때만 저장 메뉴를 읽는다."""
    json_path = settings.menu_json_path
    if json_path is None:
        return _empty_stored_menu_data("not_configured")
    if not json_path.is_file():
        return _empty_stored_menu_data("configured_file_missing")
    return load_menu_data(json_path)


# 저장 JSON은 선택 사항이다. URL·QR·사진 흐름은 이 파일 없이도 실행된다.
menu_data = _load_configured_menu_data()

# V1.1: 연결은 요청 시점에 열어 서버 시작과 일반 health 확인을 분리한다.
menu_store = MenuStore(settings)


def _diagnostic_headers(error_code: str, failure_stage: str) -> dict[str, str]:
    """기존 오류 본문은 유지하면서 앱이 안정적으로 분류할 헤더를 만든다."""
    return {
        "X-Menu-Error-Code": error_code,
        "X-Menu-Failure-Stage": failure_stage,
        "X-Request-ID": current_request_id(),
    }


def _menu_http_error(
    *,
    operation: str,
    status_code: int,
    detail: str,
    error_code: str,
    failure_stage: str,
    error: Exception,
) -> HTTPException:
    record_performance_event(
        component="backend",
        event="request_failure",
        operation=operation,
        outcome="timeout" if error_code == "SOURCE_TIMEOUT" else "failure",
        stage=failure_stage,
        error_code=error_code,
        error_type=type(error).__name__,
        http_status=status_code,
        retry_count=0,
        retry_limit=0,
        timeout=error_code == "SOURCE_TIMEOUT",
        rate_limited=False,
        concurrency=1,
        measurement_method="exception_mapping",
    )
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers=_diagnostic_headers(error_code, failure_stage),
    )


def _database_http_error(error: MenuDatabaseError) -> HTTPException:
    if isinstance(error, MenuDatabaseNotConfiguredError):
        code = "MENU_DATABASE_NOT_CONFIGURED"
        detail = "메뉴 저장 데이터베이스가 설정되지 않았습니다."
    elif isinstance(error, MenuDatabaseSchemaError):
        code = "MENU_DATABASE_SCHEMA_MISSING"
        detail = "메뉴 저장 스키마가 적용되지 않았습니다."
    else:
        code = "MENU_DATABASE_UNAVAILABLE"
        detail = "메뉴 저장 데이터베이스에 연결하지 못했습니다."
    return _menu_http_error(
        operation="menu_storage",
        status_code=503,
        detail=detail,
        error_code=code,
        failure_stage="storage",
        error=error,
    )


class MenuURLRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class MobilePerformanceEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=100)
    event: Literal[
        "api_response_received",
        "screen_displayed",
        "operation_failed",
        "description_ready",
    ]
    operation: Literal[
        "backend_wakeup",
        "stored_menu_load",
        "url_menu_import",
        "detail_explanation",
        "combination_explanation",
        "one_line_description",
    ]
    duration_ms: float = Field(ge=0, le=600_000)
    outcome: Literal["success", "failure", "timeout", "rate_limited"]
    cache_status: Literal["hit", "miss", "coalesced", "not_applicable"]
    attempt: int = Field(ge=1, le=100)
    retry_count: int = Field(ge=0, le=10)
    retry_limit: int = Field(ge=0, le=10)
    http_status: int | None = Field(default=None, ge=100, le=599)
    timeout: bool = False
    rate_limited: bool = False
    item_count: int | None = Field(default=None, ge=0, le=100_000)
    error_type: Literal[
        "api_error",
        "connection_error",
        "timeout",
        "rate_limit",
        "validation_error",
        "request_cancelled",
        "source_request_error",
        "unsupported_menu_structure",
        "transformation_error",
        "unknown",
    ] | None = None
    error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Z0-9_]+$",
    )
    failure_stage: Literal[
        "validation",
        "app_connection",
        "source_request",
        "extraction",
        "transformation",
        "storage",
        "server",
    ] | None = None
    measurement_method: Literal[
        "fetch_response_body_parsed",
        "request_animation_frame_after_react_commit",
        "async_storage_result_ready",
        "promise_rejected",
    ]


@app.middleware("http")
async def measure_backend_request(request: Request, call_next):
    """모바일 요청 ID를 보존하고 백엔드 전체 처리 시간을 기록한다."""
    request_id = normalise_request_id(request.headers.get("X-Request-ID"))
    token = bind_request_id(request_id)
    started_at = perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    except Exception as error:
        if request.url.path != "/performance/mobile-events":
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched_request")
            record_performance_event(
                component="backend",
                event="api_request",
                operation=route_path,
                outcome="failure",
                duration_ms=(perf_counter() - started_at) * 1000,
                error_type=type(error).__name__,
                error_code="UNHANDLED_SERVER_ERROR",
                stage="server",
                http_status=500,
                retry_count=0,
                retry_limit=0,
                timeout=False,
                rate_limited=False,
                concurrency=1,
                measurement_method="asgi_middleware",
            )
        raise
    finally:
        if response is not None:
            duration_ms = (perf_counter() - started_at) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["Server-Timing"] = f"menu_helper;dur={duration_ms:.3f}"
            if request.url.path != "/performance/mobile-events":
                route = request.scope.get("route")
                route_path = getattr(route, "path", "unmatched_request")
                status_code = response.status_code
                outcome = (
                    "success"
                    if status_code < 400
                    else "rate_limited"
                    if status_code == 429
                    else "timeout"
                    if status_code in {408, 504}
                    else "failure"
                )
                error_code = response.headers.get("X-Menu-Error-Code")
                failure_stage = response.headers.get("X-Menu-Failure-Stage")
                record_performance_event(
                    component="backend",
                    event="api_request",
                    operation=route_path,
                    outcome=outcome,
                    duration_ms=duration_ms,
                    http_status=status_code,
                    error_code=error_code,
                    stage=failure_stage or "server",
                    retry_count=0,
                    retry_limit=0,
                    timeout=outcome == "timeout",
                    rate_limited=outcome == "rate_limited",
                    concurrency=1,
                    measurement_method="asgi_middleware",
                )
        reset_request_id(token)


def _create_measured_menu_ui(menu_source: dict, operation: str) -> dict:
    started_at = perf_counter()
    try:
        result = create_menu_ui_data(menu_source)
    except (KeyError, TypeError, ValueError) as error:
        record_performance_event(
            component="backend",
            event="menu_ui_transform",
            operation=operation,
            outcome="failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            stage="transformation",
            error_code="MENU_TRANSFORM_FAILED",
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=False,
            rate_limited=False,
            concurrency=1,
            measurement_method="perf_counter",
        )
        raise HTTPException(
            status_code=422,
            detail="메뉴 데이터를 화면 구조로 변환하지 못했습니다.",
            headers=_diagnostic_headers(
                "MENU_TRANSFORM_FAILED",
                "transformation",
            ),
        ) from error
    record_performance_event(
        component="backend",
        event="menu_ui_transform",
        operation=operation,
        outcome="success",
        duration_ms=(perf_counter() - started_at) * 1000,
        item_count=result["total_items"],
        stage="transformation",
        retry_count=0,
        retry_limit=0,
        timeout=False,
        rate_limited=False,
        concurrency=1,
        measurement_method="perf_counter",
    )
    return result


@app.get("/health")
def read_health() -> dict:
    """앱이 백엔드 연결 여부를 가볍게 확인할 때 사용한다."""
    return {"status": "ok"}


@app.get("/ready")
def read_readiness():
    """V1.1 DB 연결과 스키마를 일반 프로세스 health와 별도로 확인한다."""
    readiness = menu_store.readiness()
    return JSONResponse(
        status_code=200 if readiness["ready"] else 503,
        content={"status": "ready" if readiness["ready"] else "not_ready", **readiness},
    )


@app.get("/menus")
def read_menus() -> dict:
    """설정된 저장 JSON을 반환하며, 없으면 빈 메뉴 구조를 반환한다."""
    return _create_measured_menu_ui(menu_data, "stored_menu_load")


@app.post("/menu-sources/url")
def create_menu_from_url(request_data: MenuURLRequest) -> dict:
    """URL 메뉴를 추출·검증·저장한 뒤 저장된 동일 스냅샷을 반환한다."""
    started_at = datetime.now(UTC)
    try:
        menu_store.require_ready()
        extraction = extract_menu_snapshot(request_data.url)
    except MenuURLValidationError as error:
        raise _menu_http_error(
            operation="url_menu_import",
            status_code=400,
            detail=str(error),
            error_code="INVALID_MENU_URL",
            failure_stage="validation",
            error=error,
        ) from error
    except UnsupportedMenuPageError as error:
        try:
            fallback = menu_store.record_failed_attempt(
                source_url=request_data.url,
                request_id=current_request_id(),
                failure_stage="extraction",
                error_code="UNSUPPORTED_MENU_STRUCTURE",
                started_at=started_at,
            )
        except MenuDatabaseError:
            fallback = None
        if fallback is not None:
            return {
                "status": "ready",
                "menu": _create_measured_menu_ui(
                    fallback.menu_data, "url_menu_stored_fallback"
                ),
                "refresh_error": {
                    "code": "UNSUPPORTED_MENU_STRUCTURE",
                    "stage": "extraction",
                },
            }
        raise _menu_http_error(
            operation="url_menu_import",
            status_code=422,
            detail=str(error),
            error_code="UNSUPPORTED_MENU_STRUCTURE",
            failure_stage="extraction",
            error=error,
        ) from error
    except MenuPageFetchError as error:
        try:
            fallback = menu_store.record_failed_attempt(
                source_url=request_data.url,
                request_id=current_request_id(),
                failure_stage="source_request",
                error_code=error.error_code,
                started_at=started_at,
            )
        except MenuDatabaseError:
            fallback = None
        if fallback is not None:
            return {
                "status": "ready",
                "menu": _create_measured_menu_ui(
                    fallback.menu_data, "url_menu_stored_fallback"
                ),
                "refresh_error": {
                    "code": error.error_code,
                    "stage": "source_request",
                },
            }
        raise _menu_http_error(
            operation="url_menu_import",
            status_code=502,
            detail=str(error),
            error_code=error.error_code,
            failure_stage="source_request",
            error=error,
        ) from error
    except MenuDatabaseError as error:
        raise _database_http_error(error) from error
    except (KeyError, TypeError, ValueError) as error:
        try:
            fallback = menu_store.record_failed_attempt(
                source_url=request_data.url,
                request_id=current_request_id(),
                failure_stage="validation",
                error_code="MENU_VALIDATION_FAILED",
                started_at=started_at,
            )
        except MenuDatabaseError:
            fallback = None
        if fallback is not None:
            return {
                "status": "ready",
                "menu": _create_measured_menu_ui(
                    fallback.menu_data, "url_menu_stored_fallback"
                ),
                "refresh_error": {
                    "code": "MENU_VALIDATION_FAILED",
                    "stage": "validation",
                },
            }
        raise _menu_http_error(
            operation="url_menu_import",
            status_code=422,
            detail=str(error),
            error_code="MENU_VALIDATION_FAILED",
            failure_stage="validation",
            error=error,
        ) from error

    try:
        # V1.1: 원본·검증 결과·메뉴 버전을 한 transaction으로 연결한다.
        stored_snapshot = menu_store.save_menu_snapshot(
            menu_data=extraction.menu_data,
            source_url=request_data.url,
            artifacts=extraction.artifacts,
            request_id=current_request_id(),
            extraction_status=extraction.extraction_status,
            validation_status=extraction.validation_status,
            started_at=extraction.started_at,
        )
    except MenuDatabaseError as error:
        raise _database_http_error(error) from error

    return {
        "status": "ready",
        "menu": _create_measured_menu_ui(
            stored_snapshot.menu_data, "url_menu_import"
        ),
    }


@app.post("/performance/mobile-events", status_code=202)
def record_mobile_performance_event(
    request_data: MobilePerformanceEventRequest,
) -> dict:
    """개발 기기의 비민감 화면 측정값을 백엔드 JSONL에 함께 저장한다."""
    wrote_event = record_performance_event(
        component="mobile",
        event=request_data.event,
        operation=request_data.operation,
        outcome=request_data.outcome,
        duration_ms=request_data.duration_ms,
        request_id=request_data.request_id,
        cache_status=request_data.cache_status,
        attempt=request_data.attempt,
        retry_count=request_data.retry_count,
        retry_limit=request_data.retry_limit,
        http_status=request_data.http_status,
        timeout=request_data.timeout,
        rate_limited=request_data.rate_limited,
        item_count=request_data.item_count,
        error_type=request_data.error_type,
        error_code=request_data.error_code,
        stage=request_data.failure_stage or "app_connection",
        concurrency=1,
        measurement_method=request_data.measurement_method,
    )
    return {
        "status": "recorded" if wrote_event else "disabled",
        "request_id": current_request_id(),
        "logging_enabled": performance_log_enabled(),
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
        raise _menu_http_error(
            operation="url_item_detail",
            status_code=400,
            detail=str(error),
            error_code="INVALID_MENU_URL",
            failure_stage="validation",
            error=error,
        ) from error
    except UnsupportedMenuPageError as error:
        raise _menu_http_error(
            operation="url_item_detail",
            status_code=422,
            detail=str(error),
            error_code="UNSUPPORTED_MENU_STRUCTURE",
            failure_stage="extraction",
            error=error,
        ) from error
    except MenuPageFetchError as error:
        raise _menu_http_error(
            operation="url_item_detail",
            status_code=502,
            detail=str(error),
            error_code=error.error_code,
            failure_stage="source_request",
            error=error,
        ) from error

    return {
        "status": "ready",
        "source": {
            "url": product["source_url"],
            "restaurant_id": product["restaurant_id"],
            "source_product_id": product["source_product_id"],
        },
        "product": product,
    }


@app.get("/menu-snapshots/{snapshot_id}")
def read_menu_snapshot(snapshot_id: str) -> dict:
    """저장된 불변 메뉴 버전을 다시 목록 구조로 반환한다."""
    try:
        snapshot = menu_store.get_snapshot(snapshot_id)
    except MenuDatabaseError as error:
        raise _database_http_error(error) from error
    if snapshot is None:
        raise HTTPException(status_code=404, detail="메뉴 스냅샷을 찾지 못했습니다.")
    return {
        "status": "ready",
        "menu": _create_measured_menu_ui(snapshot.menu_data, "menu_snapshot_read"),
    }


@app.get("/menu-snapshots/{snapshot_id}/items/{item_identifier}")
def read_menu_snapshot_item(snapshot_id: str, item_identifier: str) -> dict:
    """목록과 같은 스냅샷에서 item/product/source ID가 일치하는 상세를 찾는다."""
    return load_snapshot_item_detail(snapshot_id, item_identifier)


def load_snapshot_item_detail(snapshot_id: str, item_identifier: str) -> dict:
    """Read stored detail and lazily preserve verified Square SKU enrichment."""
    try:
        menu_item = menu_store.get_snapshot_item(snapshot_id, item_identifier)
    except MenuDatabaseError as error:
        raise _database_http_error(error) from error
    if menu_item is None:
        raise HTTPException(status_code=404, detail="스냅샷 메뉴를 찾지 못했습니다.")
    if (
        menu_item.get("source_id") == "square_storefront_api"
        and menu_item.get("source_product_id")
        and menu_item.get("variant_status") == "not_checked"
    ):
        try:
            source_context = menu_store.get_snapshot_source_context(snapshot_id)
            if source_context is not None:
                # V1.1: Square 상세를 최초 한 번만 보강하고 목록 스냅샷에 귀속시킨다.
                enriched = import_menu_item_detail_from_url(
                    source_context["canonical_url"],
                    menu_item["source_product_id"],
                    operation="snapshot_item_detail",
                )
                if enriched.get("source_product_id") != menu_item.get(
                    "source_product_id"
                ):
                    raise ValueError("상세 상품 식별자가 목록 스냅샷과 다릅니다.")
                enriched.update(
                    {
                        "menu_source_id": source_context["menu_source_id"],
                        "snapshot_id": source_context["snapshot_id"],
                        "snapshot_version": source_context["snapshot_version"],
                    }
                )
                menu_store.save_snapshot_item_detail(
                    snapshot_id=snapshot_id,
                    item_detail=enriched,
                    extraction_method="square_product_detail_api",
                )
                menu_item = enriched
        except MenuDatabaseError as error:
            raise _database_http_error(error) from error
        except (MenuPageFetchError, UnsupportedMenuPageError, ValueError):
            # 목록에 이미 확인된 정보는 유지하고 상세 보강 실패만 상태로 남긴다.
            menu_item = dict(menu_item)
            menu_item["variant_status"] = "fetch_failed"
            menu_item["detail_refresh_status"] = "fetch_failed"
    return create_menu_detail(menu_item)


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
