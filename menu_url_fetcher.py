import ipaddress
import json
import socket
from dataclasses import replace
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app_config import AppSettings, settings
from html_menu_parser import parse_menu_html
from square_menu_parser import (
    build_square_catalog_urls,
    build_square_product_detail_urls,
    extract_square_storefront_info,
    parse_square_catalog,
    parse_square_product_detail,
)


class MenuURLValidationError(ValueError):
    """외부 요청 전에 URL이 안전 조건을 통과하지 못했을 때 발생한다."""


class MenuPageFetchError(RuntimeError):
    """검증된 메뉴 URL을 읽지 못했을 때 발생한다."""


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

    try:
        with opener.open(
            request,
            timeout=app_settings.menu_fetch_timeout_seconds,
        ) as response:
            final_url = validate_menu_url(response.geturl(), app_settings)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise MenuPageFetchError(
                    f"HTML 메뉴가 아닌 응답입니다: {content_type}"
                )

            content = response.read(app_settings.menu_max_html_bytes + 1)
            if len(content) > app_settings.menu_max_html_bytes:
                raise MenuPageFetchError("메뉴 HTML이 허용 크기를 초과했습니다.")

            charset = response.headers.get_content_charset() or "utf-8"
            return content.decode(charset, errors="replace"), final_url
    except HTTPError as error:
        raise MenuPageFetchError(
            f"메뉴 페이지가 HTTP {error.code}을 반환했습니다."
        ) from error
    except URLError as error:
        raise MenuPageFetchError("메뉴 페이지에 연결하지 못했습니다.") from error
    except TimeoutError as error:
        raise MenuPageFetchError("메뉴 페이지 응답 시간이 초과됐습니다.") from error


def fetch_menu_json(
    url: str,
    app_settings: AppSettings = settings,
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

    try:
        with opener.open(
            request,
            timeout=app_settings.menu_fetch_timeout_seconds,
        ) as response:
            validate_menu_url(response.geturl(), app_settings)
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise MenuPageFetchError(
                    f"JSON 메뉴가 아닌 응답입니다: {content_type}"
                )

            content = response.read(app_settings.menu_max_html_bytes + 1)
            if len(content) > app_settings.menu_max_html_bytes:
                raise MenuPageFetchError("메뉴 JSON이 허용 크기를 초과했습니다.")

            charset = response.headers.get_content_charset() or "utf-8"
            try:
                return json.loads(content.decode(charset, errors="replace"))
            except json.JSONDecodeError as error:
                raise MenuPageFetchError(
                    "메뉴 API 응답을 JSON으로 읽지 못했습니다."
                ) from error
    except HTTPError as error:
        raise MenuPageFetchError(
            f"메뉴 API가 HTTP {error.code}을 반환했습니다."
        ) from error
    except URLError as error:
        raise MenuPageFetchError("메뉴 API에 연결하지 못했습니다.") from error
    except TimeoutError as error:
        raise MenuPageFetchError("메뉴 API 응답 시간이 초과됐습니다.") from error


def import_menu_from_url(
    url: str,
    app_settings: AppSettings = settings,
) -> dict:
    """URL의 HTML을 읽고 공통 메뉴 데이터로 변환한다."""
    html, final_url = fetch_menu_html(url, app_settings)

    square_storefront_info = extract_square_storefront_info(html)
    if square_storefront_info is not None:
        product_url, category_url = build_square_catalog_urls(
            square_storefront_info
        )
        product_document = fetch_menu_json(product_url, app_settings)
        category_document = fetch_menu_json(category_url, app_settings)
        return parse_square_catalog(
            product_document,
            category_document,
            final_url,
            square_storefront_info,
        )

    return parse_menu_html(html, final_url)


def import_menu_item_detail_from_url(
    url: str,
    source_product_id: str,
    app_settings: AppSettings = settings,
) -> dict:
    """URL이 가리키는 Square 식당에서 상품 한 건의 옵션·변형을 다시 읽는다."""
    if not source_product_id or len(source_product_id) > 200:
        raise MenuURLValidationError("올바른 원본 상품 ID가 필요합니다.")

    html, final_url = fetch_menu_html(url, app_settings)
    storefront_info = extract_square_storefront_info(html)
    if storefront_info is None:
        raise UnsupportedMenuPageError(
            "현재 URL 상품 상세 연결은 확인된 Square Online 구조만 지원합니다."
        )

    detail_url, sku_url = build_square_product_detail_urls(
        storefront_info,
        source_product_id,
    )
    product_document = fetch_menu_json(detail_url, app_settings)
    try:
        sku_document = fetch_menu_json(sku_url, app_settings)
    except MenuPageFetchError:
        # SKU 실패가 이미 확보한 옵션과 이미지를 지우지 않도록 상태로 남긴다.
        sku_document = None
        sku_fetch_failed = True
    else:
        sku_fetch_failed = False

    item = parse_square_product_detail(
        product_document,
        sku_document,
        final_url,
        storefront_info,
        sku_fetch_failed=sku_fetch_failed,
    )
    if item["source_product_id"] != source_product_id:
        raise UnsupportedMenuPageError(
            "요청한 상품과 Square 상세 응답의 상품 ID가 일치하지 않습니다."
        )
    return item


def settings_with_private_urls_for_development() -> AppSettings:
    """로컬 fixture 서버를 사용할 때만 명시적으로 선택하는 개발 설정이다."""
    return replace(settings, allow_private_menu_urls=True)
