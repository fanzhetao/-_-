from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from runner import ensure_checkbox_selected, factory_auto_research_selection


PROJECT_DIR = Path(__file__).resolve().parents[1]


class CheckboxLoggingTests(unittest.TestCase):
    @patch("runner.capture_debug_step")
    @patch("runner.run_task")
    @patch("runner.checkbox_is_selected", side_effect=[False, True])
    def test_logs_unselected_click_and_confirmed_states(
        self,
        checkbox_is_selected,
        run_task,
        capture_debug_step,
    ) -> None:
        reports: list[str] = []

        ensure_checkbox_selected(
            object(),
            "一键进货已勾选",
            "勾选一键进货",
            report=reports.append,
        )

        run_task.assert_called_once()
        self.assertTrue(any("初始状态=未选中" in line for line in reports))
        self.assertTrue(any("勾选点击已执行" in line for line in reports))
        self.assertTrue(any("点击后复核 1：状态=已选中" in line for line in reports))
        self.assertTrue(any("最终确认=已选中" in line for line in reports))
        self.assertEqual(capture_debug_step.call_count, 2)

    @patch("runner.capture_debug_step")
    @patch("runner.run_task")
    @patch("runner.checkbox_is_selected", return_value=True)
    def test_logs_already_selected_without_clicking(
        self,
        checkbox_is_selected,
        run_task,
        capture_debug_step,
    ) -> None:
        reports: list[str] = []

        ensure_checkbox_selected(
            object(),
            "一键进货已勾选",
            "勾选一键进货",
            report=reports.append,
        )

        run_task.assert_not_called()
        self.assertTrue(any("初始状态=已选中" in line for line in reports))
        capture_debug_step.assert_called_once()


class FactoryAutoResearchCheckboxTests(unittest.TestCase):
    def test_uses_only_green_pixels_inside_checkbox_center(self) -> None:
        text_box = (100, 100, 80, 20)
        unselected = np.zeros((200, 200, 3), dtype=np.uint8)
        selected = unselected.copy()
        # “自动研发”文字左侧 13px 是圆框中心；仅选中态中央存在绿色勾。
        selected[107:114, 84:91] = (70, 220, 90)

        unselected_state, unselected_count, center = factory_auto_research_selection(
            unselected,
            text_box,
        )
        selected_state, selected_count, _ = factory_auto_research_selection(
            selected,
            text_box,
        )

        self.assertEqual(center, (87, 110))
        self.assertFalse(unselected_state)
        self.assertEqual(unselected_count, 0)
        self.assertTrue(selected_state)
        self.assertGreaterEqual(selected_count, 5)


class RestockingPipelineSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = json.loads(
            (PROJECT_DIR / "resource" / "pipeline" / "login.json").read_text(
                encoding="utf-8"
            )
        )

    def test_restoking_page_uses_stable_stamina_anchor(self) -> None:
        entry = self.pipeline["进货界面已打开"]
        self.assertEqual(entry["recognition"], "OCR")
        self.assertEqual(entry["expected"], "体力")

    def test_start_restoking_is_fixed_only_after_checkbox_guard(self) -> None:
        entry = self.pipeline["开始进货"]
        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [360, 875])


if __name__ == "__main__":
    unittest.main()
