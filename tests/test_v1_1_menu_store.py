import unittest
import gzip
from dataclasses import replace

from app_config import settings
from v1_1_menu_store import (
    _prepare_artifact,
    canonicalise_source_url,
    menu_content_hash,
)


class V11MenuStoreTest(unittest.TestCase):
    def test_canonical_url_removes_session_values_but_keeps_store_identity(self) -> None:
        result = canonicalise_source_url(
            "https://example.com/menu?shopId=store-1&tableId=table-9&ms=123&bizType=1300#cart"
        )

        self.assertEqual(
            result,
            "https://example.com/menu?bizType=1300&shopId=store-1",
        )

    def test_content_hash_ignores_request_metadata_but_detects_price_change(self) -> None:
        first = {
            "restaurant": {"restaurant_id": "cafe-1", "name": "Cafe"},
            "provenance": {"retrieved_at": "2026-01-01", "source_url": "https://one"},
            "items": [
                {
                    "item_id": "tea",
                    "name_original": "Tea",
                    "price_amount": 5,
                    "retrieved_at": "2026-01-01",
                }
            ],
        }
        same_menu_later = {
            **first,
            "provenance": {"retrieved_at": "2026-02-01", "source_url": "https://two"},
            "items": [{**first["items"][0], "retrieved_at": "2026-02-01"}],
        }
        changed = {
            **same_menu_later,
            "items": [{**same_menu_later["items"][0], "price_amount": 6}],
        }

        self.assertEqual(menu_content_hash(first), menu_content_hash(same_menu_later))
        self.assertNotEqual(menu_content_hash(first), menu_content_hash(changed))

    def test_artifact_redacts_secret_values_before_compression(self) -> None:
        artifact = _prepare_artifact(
            {
                "role": "json",
                "content_type": "application/json",
                "body": '{"access_token":"private-value","menu":"Tea"}',
            },
            replace(
                settings,
                source_artifact_max_bytes=10_000,
                source_artifact_max_compressed_bytes=10_000,
            ),
        )

        stored_text = gzip.decompress(artifact["payload"]).decode("utf-8")
        self.assertNotIn("private-value", stored_text)
        self.assertIn("[REDACTED]", stored_text)

    def test_oversized_artifact_records_reason_without_payload(self) -> None:
        artifact = _prepare_artifact(
            {"role": "html", "content_type": "text/html", "body": "12345"},
            replace(
                settings,
                source_artifact_max_bytes=4,
                source_artifact_max_compressed_bytes=4,
            ),
        )

        self.assertEqual(artifact["storage_kind"], "omitted")
        self.assertIsNone(artifact["payload"])
        self.assertEqual(artifact["omission_reason"], "source_artifact_too_large")


if __name__ == "__main__":
    unittest.main()
