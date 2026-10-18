"""Menu Helper V1의 개발용 구조화 성능 로그와 집계 함수."""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import threading
from collections import Counter, defaultdict
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from app_config import BACKEND_ROOT, settings


LOG_SCHEMA_VERSION = "menu-helper-performance-v1"
_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "menu_helper_request_id",
    default=None,
)
_WRITE_LOCK = threading.Lock()


def _safe_identifier(value: str | None, maximum_length: int = 100) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if 1 <= len(candidate) <= maximum_length and all(
        character.isalnum() or character in "-_.:"
        for character in candidate
    ):
        return candidate
    return None


_SESSION_ID = (
    _safe_identifier(os.environ.get("MENU_PERFORMANCE_SESSION_ID"))
    or uuid4().hex
)

# 자유 형식 문자열을 허용하면 URL·인증정보가 실수로 로그에 들어갈 수 있다.
# 측정에 필요한 비민감 필드만 명시적으로 저장한다.
SAFE_DETAIL_FIELDS = {
    "attempt",
    "bytes_received",
    "cache_status",
    "category_count",
    "concurrency",
    "content_type",
    "data_origin",
    "error_code",
    "error_type",
    "http_status",
    "input_tokens",
    "item_count",
    "measurement_method",
    "model",
    "output_tokens",
    "parser",
    "prompt_version",
    "rate_limited",
    "request_role",
    "retry_count",
    "retry_limit",
    "source_host",
    "source_type",
    "stage",
    "timeout",
    "total_tokens",
    "validation_status",
}


def _detect_code_version() -> str:
    configured_version = _safe_identifier(os.environ.get("MENU_CODE_VERSION"))
    if configured_version:
        return configured_version
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=BACKEND_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BACKEND_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        return f"{commit}-dirty" if dirty else commit
    except (OSError, subprocess.SubprocessError):
        return "unknown"


CODE_VERSION = _detect_code_version()


def normalise_request_id(value: str | None = None) -> str:
    """외부 요청 ID는 제한된 문자만 허용하고, 아니면 새 ID를 만든다."""
    return _safe_identifier(value) or uuid4().hex


def bind_request_id(request_id: str) -> Token:
    return _REQUEST_ID.set(normalise_request_id(request_id))


def reset_request_id(token: Token) -> None:
    _REQUEST_ID.reset(token)


def current_request_id() -> str:
    return _REQUEST_ID.get() or normalise_request_id()


def performance_log_enabled() -> bool:
    return settings.performance_logging_enabled


def record_performance_event(
    *,
    component: str,
    event: str,
    operation: str,
    outcome: str,
    duration_ms: float | None = None,
    request_id: str | None = None,
    enabled: bool | None = None,
    log_path: Path | None = None,
    **details: object,
) -> bool:
    """비민감 필드만 JSONL에 추가한다. 로그 실패는 앱 기능을 막지 않는다."""
    unexpected_fields = set(details) - SAFE_DETAIL_FIELDS
    if unexpected_fields:
        raise ValueError(
            "허용되지 않은 성능 로그 필드입니다: "
            + ", ".join(sorted(unexpected_fields))
        )

    should_write = performance_log_enabled() if enabled is None else enabled
    if not should_write:
        return False

    event_data = {
        "schema_version": LOG_SCHEMA_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": _SESSION_ID,
        "code_version": CODE_VERSION,
        "runtime": f"python-{sys.version_info.major}.{sys.version_info.minor}",
        "platform": f"{platform.system()}-{platform.machine()}",
        "component": component,
        "event": event,
        "operation": operation,
        "request_id": normalise_request_id(request_id or _REQUEST_ID.get()),
        "outcome": outcome,
        "duration_ms": (
            round(max(0.0, float(duration_ms)), 3)
            if duration_ms is not None
            else None
        ),
    }
    event_data.update(details)
    destination = log_path or settings.performance_log_path

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event_data, ensure_ascii=False, sort_keys=True)
        with _WRITE_LOCK:
            with destination.open("a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
    except OSError:
        return False
    return True


def read_performance_events(paths: Iterable[Path]) -> tuple[list[dict], list[str]]:
    events: list[dict] = []
    errors: list[str] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            errors.append(f"{path}: {type(error).__name__}")
            continue
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"{path}:{line_number}: invalid_json")
                continue
            if isinstance(value, dict):
                events.append(value)
            else:
                errors.append(f"{path}:{line_number}: not_an_object")
    return events, errors


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def summarise_performance_events(events: Iterable[dict]) -> dict:
    """기능·캐시 상태·세부 요청을 섞지 않고 지속 시간을 집계한다."""
    event_list = list(events)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for event in event_list:
        duration = event.get("duration_ms")
        if not isinstance(duration, int | float):
            continue
        key = (
            event.get("component"),
            event.get("event"),
            event.get("operation"),
            event.get("cache_status") or "not_recorded",
            event.get("request_role") or "not_applicable",
            event.get("model") or "not_applicable",
            event.get("prompt_version") or "not_applicable",
        )
        groups[key].append(event)

    summaries = []
    for key, grouped_events in sorted(groups.items(), key=lambda item: str(item[0])):
        durations = [float(event["duration_ms"]) for event in grouped_events]
        outcomes = Counter(str(event.get("outcome") or "unknown") for event in grouped_events)
        success_count = outcomes.get("success", 0)
        sample_count = len(durations)
        summaries.append(
            {
                "component": key[0],
                "event": key[1],
                "operation": key[2],
                "cache_status": key[3],
                "request_role": key[4],
                "model": key[5],
                "prompt_version": key[6],
                "sample_count": sample_count,
                "success_count": success_count,
                "success_rate": round(success_count / sample_count, 4),
                "failure_reasons": dict(
                    sorted(
                        Counter(
                            f"{event.get('outcome') or 'unknown'}:"
                            f"{event.get('error_type') or 'unspecified'}"
                            for event in grouped_events
                            if event.get("outcome") != "success"
                        ).items()
                    )
                ),
                "retry_count_total": sum(
                    int(event["retry_count"])
                    for event in grouped_events
                    if isinstance(event.get("retry_count"), int)
                ),
                "retry_count_unknown": sum(
                    1
                    for event in grouped_events
                    if event.get("retry_count") is None
                ),
                "retry_limit_max": max(
                    (
                        int(event["retry_limit"])
                        for event in grouped_events
                        if isinstance(event.get("retry_limit"), int)
                    ),
                    default=None,
                ),
                "timeout_count": sum(
                    1 for event in grouped_events if event.get("timeout") is True
                ),
                "rate_limited_count": sum(
                    1
                    for event in grouped_events
                    if event.get("rate_limited") is True
                ),
                "input_tokens": sum(
                    int(event["input_tokens"])
                    for event in grouped_events
                    if isinstance(event.get("input_tokens"), int)
                ),
                "output_tokens": sum(
                    int(event["output_tokens"])
                    for event in grouped_events
                    if isinstance(event.get("output_tokens"), int)
                ),
                "total_tokens": sum(
                    int(event["total_tokens"])
                    for event in grouped_events
                    if isinstance(event.get("total_tokens"), int)
                ),
                "token_usage_sample_count": sum(
                    1
                    for event in grouped_events
                    if isinstance(event.get("total_tokens"), int)
                ),
                "average_ms": round(sum(durations) / sample_count, 3),
                "p50_ms": (
                    round(_nearest_rank(durations, 0.50), 3)
                    if sample_count >= 2
                    else None
                ),
                "p95_ms": (
                    round(_nearest_rank(durations, 0.95), 3)
                    if sample_count >= 20
                    else None
                ),
                "maximum_ms": round(max(durations), 3),
                "p50_note": None if sample_count >= 2 else "표본 2개 미만",
                "p95_note": None if sample_count >= 20 else "표본 20개 미만",
            }
        )

    versions = sorted(
        {
            str(event.get("code_version"))
            for event in event_list
            if event.get("code_version")
        }
    )
    sessions = sorted(
        {
            str(event.get("session_id"))
            for event in event_list
            if event.get("session_id")
        }
    )
    return {
        "schema_version": LOG_SCHEMA_VERSION,
        "code_versions": versions,
        "session_count": len(sessions),
        "event_count": len(event_list),
        "groups": summaries,
    }
