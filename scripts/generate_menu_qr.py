import argparse
from pathlib import Path
from urllib.parse import urlsplit

import qrcode


def validate_http_url(url: str) -> str:
    parsed_url = urlsplit(url.strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("http 또는 https 메뉴 URL을 입력하세요.")
    return parsed_url.geturl()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="실기기 QR 스캔 연습용 메뉴 URL 이미지를 만듭니다.",
    )
    parser.add_argument("url", help="QR에 넣을 메뉴 URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("demo_menu_qr.png"),
        help="생성할 PNG 경로",
    )
    arguments = parser.parse_args()

    menu_url = validate_http_url(arguments.url)
    qr_image = qrcode.make(menu_url)
    qr_image.save(arguments.output)

    print(f"QR URL: {menu_url}")
    print(f"저장 위치: {arguments.output.resolve()}")


if __name__ == "__main__":
    main()
