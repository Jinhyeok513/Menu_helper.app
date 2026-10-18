#!/usr/bin/env python3
"""실행 중인 V1 백엔드에 소규모 URL 메뉴 측정을 요청한다."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from performance_metrics import record_performance_event  # noqa: E402


def positive_run_count(value: str) -> int:
    count = int(value)
    if not 1 <= count <= 10:
        raise argparse.ArgumentTypeError("runs는 1~10이어야 합니다.")
    return count


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="V1 URL 메뉴 API를 자동 재시도 없이 반복 측정합니다.",
    )
    parser.add_argument("--menu-url", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=positive_run_count, default=1)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "performance_logs" / "v1_client.jsonl",
    )
    return parser.parse_args()


def validate_http_url(value: str, label: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit(f"{label}은 http(s) URL이어야 합니다.")
    if parsed.username or parsed.password:
        raise SystemExit(f"{label}에 사용자 정보가 포함되면 안 됩니다.")
    return value.strip().rstrip("/")


def main() -> None:
    arguments = parse_arguments()
    menu_url = validate_http_url(arguments.menu_url, "menu-url")
    base_url = validate_http_url(arguments.base_url, "base-url")
    if arguments.pause_seconds < 0 or arguments.timeout_seconds <= 0:
        raise SystemExit("pause-seconds는 0 이상, timeout-seconds는 0보다 커야 합니다.")

    for run_number in range(1, arguments.runs + 1):
        request_id = f"benchmark-{uuid4().hex}"
        body = json.dumps({"url": menu_url}).encode("utf-8")
        request = Request(
            f"{base_url}/menu-sources/url",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
        )
        started_at = perf_counter()
        http_status = None
        item_count = None
        outcome = "failure"
        error_type = None
        try:
            with urlopen(request, timeout=arguments.timeout_seconds) as response:
                http_status = response.status
                response_data = json.loads(response.read().decode("utf-8"))
            item_count = response_data.get("menu", {}).get("total_items")
            outcome = "success"
        except HTTPError as error:
            http_status = error.code
            outcome = "rate_limited" if error.code == 429 else "failure"
            error_type = type(error).__name__
        except (TimeoutError, URLError) as error:
            reason = getattr(error, "reason", None)
            is_timeout = isinstance(error, TimeoutError) or isinstance(
                reason,
                TimeoutError,
            )
            outcome = "timeout" if is_timeout else "failure"
            error_type = type(error).__name__
        except (json.JSONDecodeError, OSError, ValueError) as error:
            error_type = type(error).__name__

        duration_ms = (perf_counter() - started_at) * 1000
        record_performance_event(
            component="benchmark_client",
            event="api_response_received",
            operation="url_menu_import",
            outcome=outcome,
            duration_ms=duration_ms,
            request_id=request_id,
            enabled=True,
            log_path=arguments.output,
            cache_status="not_applicable",
            attempt=run_number,
            http_status=http_status,
            item_count=item_count,
            error_type=error_type,
            retry_count=0,
            retry_limit=0,
            timeout=outcome == "timeout",
            rate_limited=outcome == "rate_limited",
            concurrency=1,
            source_type="live_web",
            measurement_method="urllib_response_body_parsed",
        )
        print(
            f"run={run_number} outcome={outcome} status={http_status} "
            f"duration_ms={duration_ms:.3f} item_count={item_count} "
            f"request_id={request_id}"
        )
        if run_number < arguments.runs:
            time.sleep(arguments.pause_seconds)


if __name__ == "__main__":
    main()
