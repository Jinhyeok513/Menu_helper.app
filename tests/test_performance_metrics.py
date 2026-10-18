import json
import tempfile
import unittest
from pathlib import Path

from performance_metrics import (
    read_performance_events,
    record_performance_event,
    summarise_performance_events,
)


class PerformanceMetricsTest(unittest.TestCase):
    def test_writes_only_explicit_safe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "events.jsonl"
            wrote = record_performance_event(
                component="backend",
                event="llm_call",
                operation="detail_explanation",
                outcome="success",
                duration_ms=123.4567,
                request_id="test-request",
                enabled=True,
                log_path=log_path,
                model="test-model",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                stage="extraction",
                error_code="UNSUPPORTED_MENU_STRUCTURE",
                content_type="text/html",
            )

            self.assertTrue(wrote)
            event = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(event["request_id"], "test-request")
            self.assertEqual(event["duration_ms"], 123.457)
            self.assertNotIn("url", event)
            self.assertNotIn("api_key", event)
            self.assertEqual(event["stage"], "extraction")

    def test_rejects_fields_that_could_leak_request_data(self) -> None:
        with self.assertRaises(ValueError):
            record_performance_event(
                component="backend",
                event="external_web_request",
                operation="url_menu_import",
                outcome="success",
                enabled=False,
                url="https://example.com/private-query",
            )

        with self.assertRaises(ValueError):
            record_performance_event(
                component="backend",
                event="external_web_request",
                operation="url_menu_import",
                outcome="failure",
                enabled=False,
                authorization="Bearer secret",
                response_body="private menu response",
            )

    def test_aggregate_separates_cache_and_limits_percentiles(self) -> None:
        events = [
            {
                "component": "mobile",
                "event": "screen_displayed",
                "operation": "detail_explanation",
                "cache_status": "hit",
                "duration_ms": 10,
                "outcome": "success",
                "code_version": "abc",
                "session_id": "one",
            },
            {
                "component": "mobile",
                "event": "screen_displayed",
                "operation": "detail_explanation",
                "cache_status": "miss",
                "duration_ms": 100,
                "outcome": "success",
                "code_version": "abc",
                "session_id": "one",
            },
        ]

        summary = summarise_performance_events(events)

        self.assertEqual(len(summary["groups"]), 2)
        self.assertTrue(all(group["p50_ms"] is None for group in summary["groups"]))
        self.assertTrue(all(group["p95_ms"] is None for group in summary["groups"]))

    def test_reader_reports_invalid_lines_without_stopping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "events.jsonl"
            log_path.write_text('{"duration_ms": 1}\nnot-json\n', encoding="utf-8")

            events, errors = read_performance_events([log_path])

            self.assertEqual(len(events), 1)
            self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
