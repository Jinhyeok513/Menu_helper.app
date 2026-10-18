import ipaddress
import json
import socket
from dataclasses import replace
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app_config import AppSettings, settings
from html_menu_parser import UnsupportedMenuPageError, parse_menu_html
from square_menu_parser import (
    build_square_catalog_urls,
    build_square_product_detail_urls,
    extract_square_storefront_info,
    parse_square_catalog,
    parse_square_product_detail,
)
from performance_metrics import record_performance_event


class MenuURLValidationError(ValueError):
    """외부 요청 전에 URL이 안전 조건을 통과하지 못했을 때 발생한다."""


class MenuPageFetchError(RuntimeError):
    """검증된 메뉴 URL을 읽지 못했을 때 발생한다."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "SOURCE_REQUEST_FAILED",
        http_status: int | None = None,
        is_timeout: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status
        self.is_timeout = is_timeout


def _host_matches_allowlist(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    return any(
        hostname == allowed_host or hostname.endswith(f".{allowed_host}")
        for allowed_host in allowed_hosts
    )


def _is_private_address(address: str) -> bool:
    ip_address = ipaddress.ip_address(address)
    return any(
        (
            ip_address.is_private,
            ip_address.is_loopback,
            ip_address.is_link_local,
            ip_address.is_multicast,
            ip_address.is_reserved,
            ip_address.is_unspecified,
        )
    )


def validate_menu_url(url: str, app_settings: AppSettings = settings) -> str:
    """HTTP(S) URL, 호스트와 목적지 IP를 외부 요청 전에 검사한다."""
    if len(url) > 2048:
        raise MenuURLValidationError("URL은 2048자 이하여야 합니다.")

    parsed_url = urlsplit(url.strip())
    if parsed_url.scheme not in {"http", "https"}:
        raise MenuURLValidationError("http 또는 https 메뉴 URL만 지원합니다.")
    if not parsed_url.hostname:
        raise MenuURLValidationError("URL에 호스트 이름이 없습니다.")
    if parsed_url.username or parsed_url.password:
        raise MenuURLValidationError("사용자 정보가 포함된 URL은 지원하지 않습니다.")

    hostname = parsed_url.hostname.lower().rstrip(".")
    if app_settings.allowed_menu_hosts and not _host_matches_allowlist(
        hostname,
        app_settings.allowed_menu_hosts,
    ):
        raise MenuURLValidationError("허용된 메뉴 호스트가 아닙니다.")

    try:
        address_info = socket.getaddrinfo(
            hostname,
            parsed_url.port or (443 if parsed_url.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise MenuURLValidationError("메뉴 URL의 호스트를 확인할 수 없습니다.") from error

    addresses = {entry[4][0] for entry in address_info}
    if not addresses:
        raise MenuURLValidationError("메뉴 URL의 목적지 주소가 없습니다.")

    if not app_settings.allow_private_menu_urls:
        for address in addresses:
            if _is_private_address(address):
                raise MenuURLValidationError(
                    "내부망·localhost 메뉴 URL은 허용되지 않습니다."
                )

    return parsed_url.geturl()


class _ValidatedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, app_settings: AppSettings) -> None:
        super().__init__()
        self.app_settings = app_settings

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        absolute_url = urljoin(request.full_url, new_url)
        validate_menu_url(absolute_url, self.app_settings)
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            absolute_url,
        )


def fetch_menu_html(
    url: str,
    app_settings: AppSettings = settings,
    *,
    operation: str = "menu_fetch",
    request_role: str = "html",
) -> tuple[str, str]:
    """검증한 공개 URL에서 크기가 제한된 HTML 문서를 읽는다."""
    validated_url = validate_menu_url(url, app_settings)
    request = Request(
        validated_url,
        headers={
            "User-Agent": "MenuHelperLearningApp/0.1 (+menu HTML reader)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    opener = build_opener(_ValidatedRedirectHandler(app_settings))
    started_at = perf_counter()
    source_host = urlsplit(validated_url).hostname
    content_type = None

    try:
        with opener.open(
            request,
            timeout=app_settings.menu_fetch_timeout_seconds,
        ) as response:
            final_url = validate_menu_url(response.geturl(), app_settings)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise MenuPageFetchError(
                    f"HTML 메뉴가 아닌 응답입니다: {content_type}",
                    error_code="SOURCE_CONTENT_TYPE_UNSUPPORTED",
                )

            content = response.read(app_settings.menu_max_html_bytes + 1)
            if len(content) > app_settings.menu_max_html_bytes:
                raise MenuPageFetchError(
                    "메뉴 HTML이 허용 크기를 초과했습니다.",
                    error_code="SOURCE_RESPONSE_TOO_LARGE",
                )

            charset = response.headers.get_content_charset() or "utf-8"
            result = content.decode(charset, errors="replace"), final_url
            record_performance_event(
                component="backend",
                event="external_web_request",
                operation=operation,
                outcome="success",
                duration_ms=(perf_counter() - started_at) * 1000,
                source_host=source_host,
                stage="source_request",
                request_role=request_role,
                http_status=getattr(response, "status", 200),
                content_type=content_type,
                bytes_received=len(content),
                retry_count=0,
                retry_limit=0,
                timeout=False,
                rate_limited=False,
                concurrency=1,
                measurement_method="urllib_response_read",
            )
            return result
    except MenuPageFetchError as error:
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            http_status=error.http_status,
            content_type=content_type,
            error_code=error.error_code,
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=error.is_timeout,
            rate_limited=False,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        raise
    except HTTPError as error:
        content_type = (
            error.headers.get_content_type() if error.headers is not None else None
        )
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="rate_limited" if error.code == 429 else "failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            http_status=error.code,
            content_type=content_type,
            error_code="SOURCE_HTTP_ERROR",
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=False,
            rate_limited=error.code == 429,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        raise MenuPageFetchError(
            f"메뉴 페이지가 HTTP {error.code}을 반환했습니다.",
            error_code="SOURCE_HTTP_ERROR",
            http_status=error.code,
        ) from error
    except URLError as error:
        is_timeout = isinstance(error.reason, (TimeoutError, socket.timeout))
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="timeout" if is_timeout else "failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            content_type=content_type,
            error_code=(
                "SOURCE_TIMEOUT" if is_timeout else "SOURCE_CONNECTION_ERROR"
            ),
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=is_timeout,
            rate_limited=False,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        if is_timeout:
            raise MenuPageFetchError(
                "메뉴 페이지 응답 시간이 초과됐습니다.",
                error_code="SOURCE_TIMEOUT",
                is_timeout=True,
            ) from error
        raise MenuPageFetchError(
            "메뉴 페이지에 연결하지 못했습니다.",
            error_code="SOURCE_CONNECTION_ERROR",
        ) from error
    except TimeoutError as error:
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="timeout",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            content_type=content_type,
            error_code="SOURCE_TIMEOUT",
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=True,
            rate_limited=False,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        raise MenuPageFetchError(
            "메뉴 페이지 응답 시간이 초과됐습니다.",
            error_code="SOURCE_TIMEOUT",
            is_timeout=True,
        ) from error


def fetch_menu_json(
    url: str,
    app_settings: AppSettings = settings,
    *,
    operation: str = "menu_fetch",
    request_role: str = "json",
) -> object:
    """검증한 공개 URL에서 크기가 제한된 JSON 문서를 읽는다."""
    validated_url = validate_menu_url(url, app_settings)
    request = Request(
        validated_url,
        headers={
            "User-Agent": "MenuHelperLearningApp/0.1 (+menu JSON reader)",
            "Accept": "application/json",
        },
    )
    opener = build_opener(_ValidatedRedirectHandler(app_settings))
    started_at = perf_counter()
    source_host = urlsplit(validated_url).hostname
    content_type = None

    try:
        with opener.open(
            request,
            timeout=app_settings.menu_fetch_timeout_seconds,
        ) as response:
            validate_menu_url(response.geturl(), app_settings)
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise MenuPageFetchError(
                    f"JSON 메뉴가 아닌 응답입니다: {content_type}",
                    error_code="SOURCE_CONTENT_TYPE_UNSUPPORTED",
                )

            content = response.read(app_settings.menu_max_html_bytes + 1)
            if len(content) > app_settings.menu_max_html_bytes:
                raise MenuPageFetchError(
                    "메뉴 JSON이 허용 크기를 초과했습니다.",
                    error_code="SOURCE_RESPONSE_TOO_LARGE",
                )

            charset = response.headers.get_content_charset() or "utf-8"
            try:
                result = json.loads(content.decode(charset, errors="replace"))
                record_performance_event(
                    component="backend",
                    event="external_web_request",
                    operation=operation,
                    outcome="success",
                    duration_ms=(perf_counter() - started_at) * 1000,
                    source_host=source_host,
                    stage="source_request",
                    request_role=request_role,
                    http_status=getattr(response, "status", 200),
                    content_type=content_type,
                    bytes_received=len(content),
                    retry_count=0,
                    retry_limit=0,
                    timeout=False,
                    rate_limited=False,
                    concurrency=1,
                    measurement_method="urllib_response_read",
                )
                return result
            except json.JSONDecodeError as error:
                raise MenuPageFetchError(
                    "메뉴 API 응답을 JSON으로 읽지 못했습니다.",
                    error_code="SOURCE_INVALID_JSON",
                ) from error
    except MenuPageFetchError as error:
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            http_status=error.http_status,
            content_type=content_type,
            error_code=error.error_code,
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=error.is_timeout,
            rate_limited=False,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        raise
    except HTTPError as error:
        content_type = (
            error.headers.get_content_type() if error.headers is not None else None
        )
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="rate_limited" if error.code == 429 else "failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            http_status=error.code,
            content_type=content_type,
            error_code="SOURCE_HTTP_ERROR",
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=False,
            rate_limited=error.code == 429,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        raise MenuPageFetchError(
            f"메뉴 API가 HTTP {error.code}을 반환했습니다.",
            error_code="SOURCE_HTTP_ERROR",
            http_status=error.code,
        ) from error
    except URLError as error:
        is_timeout = isinstance(error.reason, (TimeoutError, socket.timeout))
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="timeout" if is_timeout else "failure",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            content_type=content_type,
            error_code=(
                "SOURCE_TIMEOUT" if is_timeout else "SOURCE_CONNECTION_ERROR"
            ),
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=is_timeout,
            rate_limited=False,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        if is_timeout:
            raise MenuPageFetchError(
                "메뉴 API 응답 시간이 초과됐습니다.",
                error_code="SOURCE_TIMEOUT",
                is_timeout=True,
            ) from error
        raise MenuPageFetchError(
            "메뉴 API에 연결하지 못했습니다.",
            error_code="SOURCE_CONNECTION_ERROR",
        ) from error
    except TimeoutError as error:
        record_performance_event(
            component="backend",
            event="external_web_request",
            operation=operation,
            outcome="timeout",
            duration_ms=(perf_counter() - started_at) * 1000,
            source_host=source_host,
            stage="source_request",
            request_role=request_role,
            content_type=content_type,
            error_code="SOURCE_TIMEOUT",
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=True,
            rate_limited=False,
            concurrency=1,
            measurement_method="urllib_response_read",
        )
        raise MenuPageFetchError(
            "메뉴 API 응답 시간이 초과됐습니다.",
            error_code="SOURCE_TIMEOUT",
            is_timeout=True,
        ) from error


def import_menu_from_url(
    url: str,
    app_settings: AppSettings = settings,
    *,
    artifact_collector: list[dict] | None = None,
) -> dict:
    """URL의 HTML을 읽고 공통 메뉴 데이터로 변환한다."""
    operation = "url_menu_import"
    html, final_url = fetch_menu_html(
        url,
        app_settings,
        operation=operation,
        request_role="storefront_html",
    )
    if artifact_collector is not None:
        # V1.1: 파싱 입력을 스냅샷과 연결하되 저장 계층에서 크기·민감정보를 다시 검사한다.
        artifact_collector.append(
            {
                "role": "storefront_html",
                "content_type": "text/html",
                "body": html,
            }
        )

    square_storefront_info = extract_square_storefront_info(html)
    if square_storefront_info is not None:
        product_url, category_url = build_square_catalog_urls(
            square_storefront_info
        )
        product_document = fetch_menu_json(
            product_url,
            app_settings,
            operation=operation,
            request_role="square_products",
        )
        category_document = fetch_menu_json(
            category_url,
            app_settings,
            operation=operation,
            request_role="square_categories",
        )
        if artifact_collector is not None:
            artifact_collector.extend(
                [
                    {
                        "role": "square_products",
                        "content_type": "application/json",
                        "body": product_document,
                    },
                    {
                        "role": "square_categories",
                        "content_type": "application/json",
                        "body": category_document,
                    },
                ]
            )
        parser_name = "square_storefront"
        parse_started_at = perf_counter()
        try:
            result = parse_square_catalog(
                product_document,
                category_document,
                final_url,
                square_storefront_info,
            )
        except Exception as error:
            error_code = (
                "UNSUPPORTED_MENU_STRUCTURE"
                if isinstance(error, UnsupportedMenuPageError)
                else "MENU_EXTRACTION_FAILED"
            )
            record_performance_event(
                component="backend",
                event="menu_parse_transform",
                operation=operation,
                outcome="failure",
                duration_ms=(perf_counter() - parse_started_at) * 1000,
                parser=parser_name,
                stage="extraction",
                source_type="live_web",
                error_code=error_code,
                error_type=type(error).__name__,
                retry_count=0,
                retry_limit=0,
                timeout=False,
                rate_limited=False,
                concurrency=1,
                measurement_method="perf_counter",
            )
            raise
    else:
        parser_name = "html_embedded_data"
        parse_started_at = perf_counter()
        try:
            result = parse_menu_html(html, final_url)
        except Exception as error:
            error_code = (
                "UNSUPPORTED_MENU_STRUCTURE"
                if isinstance(error, UnsupportedMenuPageError)
                else "MENU_EXTRACTION_FAILED"
            )
            record_performance_event(
                component="backend",
                event="menu_parse_transform",
                operation=operation,
                outcome="failure",
                duration_ms=(perf_counter() - parse_started_at) * 1000,
                parser=parser_name,
                stage="extraction",
                source_type="live_web",
                error_code=error_code,
                error_type=type(error).__name__,
                retry_count=0,
                retry_limit=0,
                timeout=False,
                rate_limited=False,
                concurrency=1,
                measurement_method="perf_counter",
            )
            raise

    items = result.get("items") if isinstance(result, dict) else None
    category_count = len(
        {
            item.get("category_original")
            for item in items or []
            if isinstance(item, dict) and item.get("category_original")
        }
    )
    record_performance_event(
        component="backend",
        event="menu_parse_transform",
        operation=operation,
        outcome="success",
        duration_ms=(perf_counter() - parse_started_at) * 1000,
        parser=parser_name,
        stage="extraction",
        source_type="live_web",
        item_count=len(items or []),
        category_count=category_count,
        retry_count=0,
        retry_limit=0,
        timeout=False,
        rate_limited=False,
        concurrency=1,
        measurement_method="perf_counter",
    )
    return result


def import_menu_item_detail_from_url(
    url: str,
    source_product_id: str,
    app_settings: AppSettings = settings,
    *,
    operation: str = "url_item_detail",
) -> dict:
    """URL이 가리키는 Square 식당에서 상품 한 건의 옵션·변형을 다시 읽는다."""
    if not source_product_id or len(source_product_id) > 200:
        raise MenuURLValidationError("올바른 원본 상품 ID가 필요합니다.")

    html, final_url = fetch_menu_html(
        url,
        app_settings,
        operation=operation,
        request_role="storefront_html",
    )
    storefront_info = extract_square_storefront_info(html)
    if storefront_info is None:
        raise UnsupportedMenuPageError(
            "현재 URL 상품 상세 연결은 확인된 Square Online 구조만 지원합니다."
        )

    detail_url, sku_url = build_square_product_detail_urls(
        storefront_info,
        source_product_id,
    )
    product_document = fetch_menu_json(
        detail_url,
        app_settings,
        operation=operation,
        request_role="square_product_detail",
    )
    try:
        sku_document = fetch_menu_json(
            sku_url,
            app_settings,
            operation=operation,
            request_role="square_product_skus",
        )
    except MenuPageFetchError:
        # SKU 실패가 이미 확보한 옵션과 이미지를 지우지 않도록 상태로 남긴다.
        sku_document = None
        sku_fetch_failed = True
    else:
        sku_fetch_failed = False

    parse_started_at = perf_counter()
    try:
        item = parse_square_product_detail(
            product_document,
            sku_document,
            final_url,
            storefront_info,
            sku_fetch_failed=sku_fetch_failed,
        )
    except Exception as error:
        error_code = (
            "UNSUPPORTED_MENU_STRUCTURE"
            if isinstance(error, UnsupportedMenuPageError)
            else "MENU_EXTRACTION_FAILED"
        )
        record_performance_event(
            component="backend",
            event="menu_parse_transform",
            operation=operation,
            outcome="failure",
            duration_ms=(perf_counter() - parse_started_at) * 1000,
            parser="square_product_detail",
            stage="extraction",
            source_type="live_web",
            error_code=error_code,
            error_type=type(error).__name__,
            retry_count=0,
            retry_limit=0,
            timeout=False,
            rate_limited=False,
            concurrency=1,
            measurement_method="perf_counter",
        )
        raise
    record_performance_event(
        component="backend",
        event="menu_parse_transform",
        operation=operation,
        outcome="success",
        duration_ms=(perf_counter() - parse_started_at) * 1000,
        parser="square_product_detail",
        stage="extraction",
        source_type="live_web",
        item_count=1,
        category_count=0,
        retry_count=0,
        retry_limit=0,
        timeout=False,
        rate_limited=False,
        concurrency=1,
        measurement_method="perf_counter",
    )
    if item["source_product_id"] != source_product_id:
        raise UnsupportedMenuPageError(
            "요청한 상품과 Square 상세 응답의 상품 ID가 일치하지 않습니다."
        )
    return item


def settings_with_private_urls_for_development() -> AppSettings:
    """로컬 fixture 서버를 사용할 때만 명시적으로 선택하는 개발 설정이다."""
    return replace(settings, allow_private_menu_urls=True)
