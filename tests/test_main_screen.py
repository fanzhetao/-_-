from __future__ import annotations

import unittest
from unittest.mock import patch

from runner import main_screen_is_reached, wait_for_main_screen


class MainScreenRecognitionTests(unittest.TestCase):
    @patch("runner._try_recognize_once", side_effect=[True, False, True])
    def test_accepts_two_of_three_anchors_and_logs_each_result(
        self,
        recognize_once,
    ) -> None:
        reports: list[str] = []

        reached = main_screen_is_reached(
            object(),
            report=reports.append,
            context="测试轮",
        )

        self.assertTrue(reached)
        self.assertEqual(recognize_once.call_count, 3)
        self.assertTrue(any("左下“百货”=命中" in line for line in reports))
        self.assertTrue(any("底部“关卡/伙伴”=未命中" in line for line in reports))
        self.assertTrue(any("命中 2/3" in line and "结论=已到达" in line for line in reports))

    @patch("runner._try_recognize_once", side_effect=[True, False, False])
    def test_rejects_one_of_three_anchors_with_detailed_summary(
        self,
        recognize_once,
    ) -> None:
        reports: list[str] = []

        reached = main_screen_is_reached(object(), report=reports.append)

        self.assertFalse(reached)
        self.assertTrue(any("命中 1/3" in line and "结论=未到达" in line for line in reports))

    @patch("runner.capture_debug_step")
    @patch("runner.main_screen_is_reached", return_value=True)
    def test_waiter_stops_on_first_successful_round(
        self,
        main_screen_is_reached_mock,
        capture_debug_step,
    ) -> None:
        reports: list[str] = []

        wait_for_main_screen(object(), report=reports.append)

        main_screen_is_reached_mock.assert_called_once()
        self.assertTrue(any("已确认到达主界面" in line for line in reports))
        capture_debug_step.assert_called_once()


if __name__ == "__main__":
    unittest.main()
