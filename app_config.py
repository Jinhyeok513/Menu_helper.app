import os
from dataclasses import dataclass
from pathlib import Path


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
    )


settings = load_app_settings()
