from __future__ import annotations

import unittest
from unittest.mock import patch

from runner import load_account_configs, save_account_configs


class AccountConfigTests(unittest.TestCase):
    def test_migrates_legacy_single_account_config(self) -> None:
        accounts = load_account_configs(
            {"account": "legacy", "password": "secret", "server_number": 12}
        )

        self.assertEqual(
            accounts,
            [
                {
                    "account": "legacy",
                    "password": "secret",
                    "server_number": 12,
                    "active": True,
                }
            ],
        )

    def test_preserves_order_and_active_state(self) -> None:
        accounts = load_account_configs(
            {
                "accounts": [
                    {
                        "account": "first",
                        "password": "one",
                        "server_number": 1,
                        "active": False,
                    },
                    {
                        "account": "second",
                        "password": "two",
                        "server_number": "8",
                        "active": True,
                    },
                ]
            }
        )

        self.assertEqual([item["account"] for item in accounts], ["first", "second"])
        self.assertEqual([item["active"] for item in accounts], [False, True])
        self.assertEqual(accounts[1]["server_number"], 8)

    @patch("runner.validate_server_number")
    @patch("runner.validate_credential")
    def test_save_writes_new_multi_account_schema(
        self, validate_credential, validate_server_number
    ) -> None:
        accounts = [
            {
                "account": "first",
                "password": "one",
                "server_number": 3,
                "active": True,
            }
        ]
        written: dict[str, str] = {}

        class FakeTempPath:
            def write_text(self, text, encoding):
                written["text"] = text

            def replace(self, destination):
                written["destination"] = str(destination)

        class FakeConfigPath:
            parent = unittest.mock.MagicMock()

            def with_suffix(self, suffix):
                return FakeTempPath()

            def __str__(self):
                return "client_config.json"

        with patch("runner.CLIENT_CONFIG_PATH", FakeConfigPath()):
            save_account_configs(accounts)

        self.assertIn('"accounts"', written["text"])
        self.assertIn('"active": true', written["text"])
        self.assertEqual(validate_credential.call_count, 2)
        validate_server_number.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
