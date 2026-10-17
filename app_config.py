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


@dataclass(frozen=True)
class AppSettings:
    menu_json_path: Path
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


def load_app_settings() -> AppSettings:
    """환경변수를 읽어 백엔드 실행 설정을 한곳에서 만든다."""
    default_menu_path = (
        Path.home() / "Desktop" / "Menu_helper" / "Noelles_Cafe_Menu.json"
    )

    return AppSettings(
        menu_json_path=Path(
            os.environ.get("MENU_JSON_PATH", default_menu_path)
        ).expanduser(),
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
    )


settings = load_app_settings()
