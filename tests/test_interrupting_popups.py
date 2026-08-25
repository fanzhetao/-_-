from __future__ import annotations

import unittest
from unittest.mock import patch

from runner import (
    ARTIST_PROMOTION_RESULT_TIMEOUT_SECONDS,
    LUCKY_DRAW_RESULT_TIMEOUT_SECONDS,
    confirm_transition,
    dismiss_result_overlay,
    handle_interrupting_tap_anywhere_popup,
    run_task,
    try_unknown_popup_fallback,
)


class TapAnywherePopupTests(unittest.TestCase):
    @patch("runner.time.sleep")
    @patch("runner._try_execute_once", return_value=True)
    @patch("runner._try_recognize_once", side_effect=[True, False])
    def test_detects_closes_and_confirms_popup_is_gone(
        self,
        recognize_once,
        execute_once,
        sleep,
    ) -> None:
        reports: list[str] = []

        handled = handle_interrupting_tap_anywhere_popup(
            object(),
            report=reports.append,
        )

        self.assertTrue(handled)
        self.assertEqual(recognize_once.call_count, 2)
        execute_once.assert_called_once_with(
            unittest.mock.ANY,
            "点击关闭商战冠军弹窗固定位置",
            timeout_ms=1000,
        )
        sleep.assert_called_once()
        self.assertIn("已关闭", reports[-1])

    @patch("runner._try_recognize_once", return_value=False)
    def test_returns_false_when_popup_is_absent(self, recognize_once) -> None:
        self.assertFalse(handle_interrupting_tap_anywhere_popup(object()))
        recognize_once.assert_called_once()

    @patch("runner.capture_debug_step")
    @patch("runner._task_succeeded", return_value=True)
    @patch("runner.handle_interrupting_popups")
    def test_run_task_checks_popups_before_starting_action(
        self,
        handle_popups,
        task_succeeded,
        capture_debug_step,
    ) -> None:
        events: list[str] = []
        handle_popups.side_effect = lambda *args, **kwargs: events.append(
            "popup-check"
        ) or True

        class FakeTasker:
            def post_task(self, entry):
                events.append(entry)
                return object()

        run_task(FakeTasker(), "测试动作", report=events.append)

        handle_popups.assert_called_once()
        task_succeeded.assert_called_once()
        capture_debug_step.assert_called_once()
        self.assertIn("[弹窗恢复] 已在执行前清除中断弹窗：测试动作", events)
        self.assertLess(events.index("popup-check"), events.index("测试动作"))


class UnknownPopupFallbackTests(unittest.TestCase):
    @patch("runner.capture_debug_step")
    @patch("runner.time.sleep")
    @patch("runner._try_unknown_popup_return_click", return_value=True)
    @patch("runner._task_succeeded", side_effect=[False, True])
    def test_stops_return_clicks_as_soon_as_task_recovers(
        self,
        task_succeeded,
        return_click,
        sleep,
        capture_debug_step,
    ) -> None:
        class FakeTasker:
            def post_task(self, entry):
                return entry

        reports: list[str] = []
        recovered = try_unknown_popup_fallback(
            FakeTasker(),
            "打开测试页面",
            report=reports.append,
        )

        self.assertTrue(recovered)
        self.assertEqual(return_click.call_count, 2)
        return_click.assert_called_with(unittest.mock.ANY)
        self.assertEqual(task_succeeded.call_count, 2)
        self.assertIn("第 2 轮", reports[-1])
        self.assertTrue(any("(50, 1230)" in report for report in reports))
        self.assertEqual(sleep.call_count, 2)
        capture_debug_step.assert_called()

    @patch("runner.capture_debug_step")
    @patch("runner.time.sleep")
    @patch("runner._try_unknown_popup_return_click", return_value=True)
    @patch("runner._task_succeeded", return_value=False)
    def test_returns_false_only_after_three_failed_rounds(
        self,
        task_succeeded,
        return_click,
        sleep,
        capture_debug_step,
    ) -> None:
        class FakeTasker:
            def post_task(self, entry):
                return entry

        self.assertFalse(try_unknown_popup_fallback(FakeTasker(), "打开测试页面"))
        self.assertEqual(return_click.call_count, 3)
        self.assertEqual(task_succeeded.call_count, 3)
        self.assertEqual(sleep.call_count, 3)

    @patch("runner.try_unknown_popup_fallback", return_value=True)
    @patch("runner.capture_debug_step")
    @patch("runner._transition_confirmed", return_value=False)
    def test_transition_uses_fallback_before_stopping(
        self,
        transition_confirmed,
        capture_debug_step,
        fallback,
    ) -> None:
        reports: list[str] = []

        confirm_transition(
            object(),
            "点击测试入口",
            "测试页面已打开",
            report=reports.append,
        )

        fallback.assert_called_once_with(
            unittest.mock.ANY,
            "测试页面已打开",
            reports.append,
            None,
        )
        self.assertIn("兜底后已确认", reports[-1])


class ResultOverlayTests(unittest.TestCase):
    def test_artist_promotion_uses_five_second_maximum_timeout(self) -> None:
        self.assertEqual(ARTIST_PROMOTION_RESULT_TIMEOUT_SECONDS, 5.0)

    def test_lucky_draw_has_a_dedicated_long_timeout(self) -> None:
        self.assertEqual(LUCKY_DRAW_RESULT_TIMEOUT_SECONDS, 20.0)

    @patch("runner.capture_debug_step")
    @patch("runner.time.sleep")
    @patch("runner.wait_job")
    @patch("runner.try_recognize", side_effect=[False, True, False])
    @patch("runner.time.monotonic", return_value=0.0)
    def test_waits_until_result_appears_and_logs_close_confirmation(
        self,
        monotonic,
        try_recognize,
        wait_job,
        sleep,
        capture_debug_step,
    ) -> None:
        class FakeController:
            def post_click(self, x, y):
                return (x, y)

        reports: list[str] = []

        dismiss_result_overlay(
            object(),
            FakeController(),
            "幸运扭蛋结果弹层",
            report=reports.append,
            wait_timeout_seconds=20.0,
        )

        self.assertEqual(try_recognize.call_count, 3)
        self.assertTrue(
            all(
                call.kwargs.get("recover_interrupting_popup") is False
                for call in try_recognize.call_args_list
            )
        )
        wait_job.assert_called_once_with((80, 220), "关闭结果弹层")
        self.assertTrue(any("第 1 次尚未识别" in line for line in reports))
        self.assertTrue(any("已识别" in line for line in reports))
        self.assertIn("已确认关闭", reports[-1])
        self.assertEqual(capture_debug_step.call_count, 2)


if __name__ == "__main__":
    unittest.main()
