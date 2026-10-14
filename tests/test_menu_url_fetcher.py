import unittest
from dataclasses import replace

from app_config import settings
from menu_url_fetcher import MenuURLValidationError, validate_menu_url


class MenuURLValidationTest(unittest.TestCase):
    def test_rejects_non_http_scheme(self) -> None:
        with self.assertRaises(MenuURLValidationError):
            validate_menu_url("file:///etc/passwd")

    def test_rejects_credentials_in_url(self) -> None:
        with self.assertRaises(MenuURLValidationError):
            validate_menu_url("https://user:password@example.com/menu")

    def test_rejects_localhost_by_default(self) -> None:
        with self.assertRaises(MenuURLValidationError):
            validate_menu_url("http://127.0.0.1:9000/menu.html")

    def test_development_setting_can_allow_local_fixture(self) -> None:
        development_settings = replace(settings, allow_private_menu_urls=True)

        result = validate_menu_url(
            "http://127.0.0.1:9000/menu.html",
            development_settings,
        )

        self.assertEqual(result, "http://127.0.0.1:9000/menu.html")


if __name__ == "__main__":
    unittest.main()
