#!/usr/bin/env python3
"""Menu Helper JSONL 성능 로그를 JSON과 Markdown으로 집계한다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from performance_metrics import (  # noqa: E402
    read_performance_events,
    summarise_performance_events,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    return parser.parse_args()


def milliseconds(value: float | None, note: str | None = None) -> str:
    return f"{value:.3f}" if value is not None else f"미산출({note})"


def markdown_report(summary: dict, read_errors: list[str]) -> str:
    lines = [
        "# Menu Helper V1 성능 집계",
        "",
        f"- 구조화 로그 이벤트: {summary['event_count']}개",
        f"- 측정 세션: {summary['session_count']}개",
        f"- 코드 버전: {', '.join(summary['code_versions']) or '미확인'}",
        "- p50은 표본 2개 이상, p95는 표본 20개 이상일 때만 산출한다.",
        "- 화면 표시는 React commit 뒤 requestAnimationFrame 시점이며 실제 픽셀 표시 완료와 같다고 보장하지 않는다.",
        "",
        "| 구성요소 | 이벤트 | 기능 | 캐시 | 세부 요청 | n | 성공률 | 평균 ms | p50 ms | p95 ms | 최대 ms | 토큰(입력/출력/전체) |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in summary["groups"]:
        token_text = (
            f"{group['input_tokens']}/{group['output_tokens']}/{group['total_tokens']}"
            if group["token_usage_sample_count"]
            else "미제공"
        )
        lines.append(
            "| {component} | {event} | {operation} | {cache_status} | "
            "{request_role} | {sample_count} | {success_rate:.1%} | "
            "{average_ms:.3f} | {p50} | {p95} | {maximum_ms:.3f} | {tokens} |".format(
                **group,
                p50=milliseconds(group["p50_ms"], group["p50_note"]),
                p95=milliseconds(group["p95_ms"], group["p95_note"]),
                tokens=token_text,
            )
        )
        if group["failure_reasons"]:
            lines.append(
                f"| ↳ 실패 원인 | {json.dumps(group['failure_reasons'], ensure_ascii=False)} | | | | | | | | | | |"
            )
    if read_errors:
        lines.extend(["", "## 읽기 오류", ""])
        lines.extend(f"- {error}" for error in read_errors)
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = parse_arguments()
    events, read_errors = read_performance_events(arguments.logs)
    summary = summarise_performance_events(events)
    json_text = json.dumps(
        {"summary": summary, "read_errors": read_errors},
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    markdown_text = markdown_report(summary, read_errors)
    if arguments.output_json:
        write_text(arguments.output_json, json_text)
    if arguments.output_markdown:
        write_text(arguments.output_markdown, markdown_text)
    if not arguments.output_json and not arguments.output_markdown:
        print(markdown_text, end="")


if __name__ == "__main__":
    main()
