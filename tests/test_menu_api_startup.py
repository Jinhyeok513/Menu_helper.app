import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MenuAPIStartupTest(unittest.TestCase):
    def _assert_server_imports(self, menu_json_path: str, expected_status: str) -> None:
        environment = os.environ.copy()
        environment["MENU_JSON_PATH"] = menu_json_path
        check_code = (
            "from fastapi.testclient import TestClient; "
            "from connect_api_llm import app; "
            "response = TestClient(app).get('/menus'); "
            "body = response.json(); "
            "assert response.status_code == 200, response.text; "
            "assert body['total_items'] == 0, body; "
            f"assert body['source']['dataset_status'] == {expected_status!r}, body"
        )
        completed = subprocess.run(
            [sys.executable, "-c", check_code],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_server_imports_without_stored_json_configuration(self) -> None:
        self._assert_server_imports("", "not_configured")

    def test_server_imports_when_configured_json_is_missing(self) -> None:
        self._assert_server_imports(
            "/tmp/menu-helper-missing-menu.json",
            "configured_file_missing",
        )


if __name__ == "__main__":
    unittest.main()
