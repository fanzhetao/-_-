from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from client import FashionMallClient


class AccountQueueTests(unittest.TestCase):
    def make_client(self) -> FashionMallClient:
        client = FashionMallClient.__new__(FashionMallClient)
        client._report = MagicMock()
        client._emit = MagicMock()
        client.debug_screenshot_dir = Path("debug-screenshots")
        return client

    @patch("client.runner.ensure_not_cancelled")
    @patch("client.runner.run_automation", side_effect=[True, True])
    def test_runs_active_accounts_in_order(
        self, run_automation, ensure_not_cancelled
    ) -> None:
        client = self.make_client()
        accounts = [
            {"account": "first", "password": "one", "server_number": 1},
            {"account": "second", "password": "two", "server_number": 2},
        ]
        cancel_event = object()

        client._run_worker(accounts, cancel_event)

        self.assertEqual(run_automation.call_count, 2)
        self.assertEqual(
            [item.args[:2] for item in run_automation.call_args_list],
            [("first", "one"), ("second", "two")],
        )
        self.assertEqual(
            [item.kwargs["debug_screenshot_dir"] for item in run_automation.call_args_list],
            [Path("debug-screenshots/account-1"), Path("debug-screenshots/account-2")],
        )
        client._emit.assert_called_once_with("done", "账号队列已完成，共执行 2 个账号。")
        self.assertEqual(ensure_not_cancelled.call_count, 2)

    @patch("client.runner.ensure_not_cancelled")
    @patch("client.runner.run_automation", return_value=False)
    def test_stops_before_next_account_when_current_is_incomplete(
        self, run_automation, ensure_not_cancelled
    ) -> None:
        client = self.make_client()
        accounts = [
            {"account": "first", "password": "one", "server_number": 1},
            {"account": "second", "password": "two", "server_number": 2},
        ]

        client._run_worker(accounts, object())

        run_automation.assert_called_once()
        client._emit.assert_called_once()
        event_kind, message = client._emit.call_args.args
        self.assertEqual(event_kind, "incomplete")
        self.assertIn("账号队列已停止", message)


if __name__ == "__main__":
    unittest.main()
