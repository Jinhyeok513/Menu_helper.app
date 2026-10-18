import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parent
# 실행한 터미널의 현재 폴더와 관계없이 백엔드 루트의 비밀 설정을 먼저 읽는다.
# 이미 셸에 설정한 값은 override=False로 보존한다.
load_dotenv(BACKEND_ROOT / ".env", override=False)


def _read_bool(environment_name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(environment_name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _read_allowed_hosts() -> tuple[str, ...]:
    raw_hosts = os.environ.get("MENU_ALLOWED_HOSTS", "")
    return tuple(
        host.strip().lower()
        for host in raw_hosts.split(",")
        if host.strip()
    )


def _read_optional_menu_json_path() -> Path | None:
    """설정한 경우에만 저장 메뉴 JSON 경로를 반환한다."""
    raw_path = os.environ.get("MENU_JSON_PATH", "").strip()
    if not raw_path:
        return None
    return Path(raw_path).expanduser()


def _read_optional_database_url() -> str | None:
    """비어 있는 DATABASE_URL은 설정되지 않은 상태로 구분한다."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    return database_url or None


def _read_performance_log_path() -> Path:
    configured_path = Path(
        os.environ.get(
            "MENU_PERFORMANCE_LOG_PATH",
            "performance_logs/v1_events.jsonl",
        )
    ).expanduser()
    return (
        configured_path
        if configured_path.is_absolute()
        else BACKEND_ROOT / configured_path
    )


@dataclass(frozen=True)
class AppSettings:
    menu_json_path: Path | None
    database_url: str | None
    database_connect_timeout_seconds: float
    database_statement_timeout_ms: int
    source_artifact_max_bytes: int
    source_artifact_max_compressed_bytes: int
    api_host: str
    api_port: int
    allow_private_menu_urls: bool
    allowed_menu_hosts: tuple[str, ...]
    menu_fetch_timeout_seconds: float
    menu_max_html_bytes: int
    groq_text_model: str
    groq_vision_model: str
    groq_timeout_seconds: float
    groq_max_retries: int
    performance_logging_enabled: bool
    performance_log_path: Path


def load_app_settings() -> AppSettings:
    """환경변수를 읽어 백엔드 실행 설정을 한곳에서 만든다."""
    return AppSettings(
        # URL·QR·사진 메뉴는 로컬 샘플 JSON 없이도 실행되어야 한다.
        menu_json_path=_read_optional_menu_json_path(),
        # V1.1: 메뉴 파일 경로가 아니라 식당별 스냅샷을 서버 DB에서 관리한다.
        database_url=_read_optional_database_url(),
        database_connect_timeout_seconds=float(
            os.environ.get("MENU_DATABASE_CONNECT_TIMEOUT_SECONDS", "5")
        ),
        database_statement_timeout_ms=int(
            os.environ.get("MENU_DATABASE_STATEMENT_TIMEOUT_MS", "10000")
        ),
        source_artifact_max_bytes=int(
            os.environ.get("MENU_SOURCE_ARTIFACT_MAX_BYTES", "2000000")
        ),
        source_artifact_max_compressed_bytes=int(
            os.environ.get("MENU_SOURCE_ARTIFACT_MAX_COMPRESSED_BYTES", "750000")
        ),
        api_host=os.environ.get("MENU_API_HOST", "0.0.0.0"),
        api_port=int(os.environ.get("MENU_API_PORT", "8000")),
        allow_private_menu_urls=_read_bool("MENU_ALLOW_PRIVATE_URLS"),
        allowed_menu_hosts=_read_allowed_hosts(),
        menu_fetch_timeout_seconds=float(
            os.environ.get("MENU_FETCH_TIMEOUT_SECONDS", "10")
        ),
        menu_max_html_bytes=int(
            os.environ.get("MENU_MAX_HTML_BYTES", "2000000")
        ),
        groq_text_model=os.environ.get(
            "MENU_TEXT_MODEL", "openai/gpt-oss-20b"
        ),
        groq_vision_model=os.environ.get(
            "MENU_VISION_MODEL", "qwen/qwen3.8-27b"
        ),
        groq_timeout_seconds=float(
            os.environ.get("GROQ_TIMEOUT_SECONDS", "45")
        ),
        # 한 번의 사용자 요청이 공급자 API를 여러 번 호출하지 않도록 기본 재시도를 끈다.
        groq_max_retries=int(os.environ.get("GROQ_MAX_RETRIES", "0")),
        performance_logging_enabled=_read_bool("MENU_PERFORMANCE_LOG_ENABLED"),
        performance_log_path=_read_performance_log_path(),
    )


settings = load_app_settings()
