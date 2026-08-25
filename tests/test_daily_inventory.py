from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from runner import (
    DAILY_STATE_CLAIMABLE,
    DAILY_STATE_CLAIMED,
    DAILY_STATE_TODO,
    DailyOcrText,
    claim_daily_completion_and_exit,
    claim_daily_100_reward,
    classify_daily_viewport,
    click_bottom_commercial_street,
    complete_artist_daily_group,
    complete_commercial_daily_group,
    complete_factory_acquisition,
    complete_factory_research_actions,
    daily_forward_button_center,
    enter_artist_from_daily,
    enter_fresh_supermarket_from_daily,
    enter_lucky_draw_from_daily,
    reenter_factory_level_tab_for_acquisition,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]


class DailyInventoryClassificationTests(unittest.TestCase):
    def test_associates_each_status_with_the_title_on_the_same_row(self) -> None:
        texts = [
            DailyOcrText("任意店铺升级10次", (50, 300, 260, 40)),
            DailyOcrText("已领取", (545, 305, 110, 45)),
            DailyOcrText("生鲜超市进货1次", (50, 500, 260, 40)),
            DailyOcrText("前往>>", (545, 505, 110, 45)),
            # 另一行的状态不能串到上面两个任务。
            DailyOcrText("领取", (545, 700, 110, 45)),
        ]

        states = classify_daily_viewport(texts)

        self.assertEqual(states["store_upgrade"], DAILY_STATE_CLAIMED)
        self.assertEqual(states["fresh_stock"], DAILY_STATE_TODO)

    def test_distinguishes_claimable_from_claimed(self) -> None:
        texts = [
            DailyOcrText("幸运扭蛋抽奖1次", (50, 300, 260, 40)),
            DailyOcrText("领取", (545, 305, 110, 45)),
            DailyOcrText("私人会馆商店兑换1次商品", (50, 500, 350, 40)),
            DailyOcrText("已领取", (545, 505, 110, 45)),
        ]

        states = classify_daily_viewport(texts)

        self.assertEqual(states["lucky_draw"], DAILY_STATE_CLAIMABLE)
        self.assertEqual(states["club_exchange"], DAILY_STATE_CLAIMED)

    def test_recognizes_club_exchange_when_title_wraps_to_two_ocr_boxes(self) -> None:
        texts = [
            DailyOcrText("私人会馆商店兑换1次", (40, 480, 250, 30)),
            DailyOcrText("商品", (40, 520, 55, 30)),
            DailyOcrText("前往>>", (549, 505, 110, 37)),
        ]

        states = classify_daily_viewport(texts)

        self.assertEqual(states["club_exchange"], DAILY_STATE_TODO)


class DailyPlanExecutionTests(unittest.TestCase):
    @patch("runner.run_daily_forward")
    def test_claimed_commercial_tasks_are_skipped(self, run_daily_forward) -> None:
        plan = {
            "store_upgrade": DAILY_STATE_CLAIMED,
            "fresh_stock": DAILY_STATE_CLAIMED,
            "lucky_draw": DAILY_STATE_CLAIMABLE,
            "club_exchange": DAILY_STATE_CLAIMED,
        }
        reports: list[str] = []

        complete_commercial_daily_group(
            object(), object(), plan, report=reports.append
        )

        run_daily_forward.assert_not_called()
        self.assertIn("整组跳过", reports[-1])

    @patch("runner.run_daily_forward")
    def test_claimed_artist_task_is_skipped(self, run_daily_forward) -> None:
        reports: list[str] = []

        complete_artist_daily_group(
            object(),
            object(),
            {"artist_promote": DAILY_STATE_CLAIMED},
            report=reports.append,
        )

        run_daily_forward.assert_not_called()
        self.assertIn("状态=已领取", reports[-1])

    @patch("runner.return_to_daily")
    @patch("runner.dismiss_result_overlay")
    @patch("runner.run_task")
    @patch("runner.run_confirmed_transition")
    @patch("runner.run_daily_forward")
    def test_club_exchange_goes_via_main_screen_and_home_entry(
        self,
        run_daily_forward,
        run_confirmed_transition,
        run_task,
        dismiss_result_overlay,
        return_to_daily,
    ) -> None:
        tasker = object()
        controller = object()
        reports: list[str] = []
        plan = {
            "store_upgrade": DAILY_STATE_CLAIMED,
            "fresh_stock": DAILY_STATE_CLAIMED,
            "lucky_draw": DAILY_STATE_CLAIMED,
            "club_exchange": DAILY_STATE_TODO,
        }

        complete_commercial_daily_group(
            tasker, controller, plan, report=reports.append
        )

        run_daily_forward.assert_called_once_with(
            tasker,
            controller,
            "私人会馆兑换任务前往",
            "主界面已到达",
            reports.append,
            None,
        )
        run_confirmed_transition.assert_any_call(
            tasker,
            "点击主页私人会馆入口",
            "私人会馆界面已打开",
            reports.append,
            None,
        )
        run_confirmed_transition.assert_any_call(
            tasker,
            "私人会馆返回主页",
            "主界面已到达",
            reports.append,
            None,
        )
        return_to_daily.assert_called_once_with(tasker, reports.append, None)


class DailyCompletionTests(unittest.TestCase):
    @patch("runner.close_game_application", return_value=False)
    @patch("runner.dismiss_result_overlay")
    @patch("runner.run_task")
    @patch("runner.try_recognize", side_effect=[True, True, True])
    @patch("runner.claim_all_daily_rewards")
    def test_does_not_continue_account_queue_if_game_cannot_be_closed(
        self,
        claim_all_daily_rewards,
        try_recognize,
        run_task,
        dismiss_result_overlay,
        close_game_application,
    ) -> None:
        tasker = object()
        controller = object()
        device = object()
        reports: list[str] = []

        completed = claim_daily_completion_and_exit(
            tasker, controller, device, report=reports.append
        )

        self.assertFalse(completed)
        run_task.assert_called_once_with(
            tasker, "领取日常100活跃礼包", reports.append, None
        )
        dismiss_result_overlay.assert_called_once_with(
            tasker,
            controller,
            "日常100活跃礼包结果弹层",
            reports.append,
            None,
        )
        close_game_application.assert_called_once_with(device, reports.append)
        self.assertTrue(any("任务完全完成" in line for line in reports))

    @patch("runner.time.sleep")
    @patch("runner.time.monotonic", side_effect=[0.0, 0.0, 5.1])
    @patch("runner.run_task")
    @patch("runner.try_recognize", side_effect=[False, True])
    @patch("runner.dismiss_result_overlay")
    def test_already_claimed_100_gift_skips_result_overlay(
        self,
        dismiss_result_overlay,
        try_recognize,
        run_task,
        monotonic,
        sleep,
    ) -> None:
        reports: list[str] = []

        claim_daily_100_reward(object(), object(), report=reports.append)

        self.assertEqual(run_task.call_count, 2)
        self.assertEqual(
            run_task.call_args_list[1].args[1],
            "关闭日常100活跃礼包重复领取弹窗",
        )
        self.assertTrue(any("已是领取状态" in line for line in reports))
        self.assertTrue(any("不会继续下一个账号" in line for line in reports))


class DailyForwardPipelineTests(unittest.TestCase):
    def test_clicks_center_of_forward_on_same_row_as_target_task(self) -> None:
        texts = [
            DailyOcrText("艺人宣传3次", (40, 430, 130, 26)),
            DailyOcrText("前往>>", (549, 469, 110, 37)),
            DailyOcrText("关卡工厂研发5次", (40, 595, 175, 25)),
            DailyOcrText("前往>>", (549, 626, 110, 37)),
            DailyOcrText("伙伴升级5次", (40, 760, 127, 26)),
            DailyOcrText("前往>>", (549, 791, 110, 36)),
        ]

        center = daily_forward_button_center(texts, "关卡工厂研发5次")

        self.assertEqual(center, (604, 644))

    def test_clicks_club_forward_when_title_wraps_to_two_ocr_boxes(self) -> None:
        texts = [
            DailyOcrText("私人会馆商店兑换1次", (40, 480, 250, 30)),
            DailyOcrText("商品", (40, 520, 55, 30)),
            DailyOcrText("前往>>", (549, 505, 110, 37)),
        ]

        center = daily_forward_button_center(
            texts, "私人会馆商店兑换1次商品"
        )

        self.assertEqual(center, (604, 523))

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = json.loads(
            (PROJECT_DIR / "resource" / "pipeline" / "login.json").read_text(
                encoding="utf-8"
            )
        )

    def test_all_supported_forward_nodes_require_forward_text(self) -> None:
        entries = (
            "任意店铺升级任务前往",
            "生鲜超市进货任务前往",
            "幸运扭蛋任务前往",
            "私人会馆兑换任务前往",
            "艺人宣传任务前往",
            "伙伴升级任务前往",
            "关卡工厂研发任务前往",
        )
        for entry_name in entries:
            with self.subTest(entry=entry_name):
                entry = self.pipeline[entry_name]
                self.assertEqual(entry["recognition"], "And")
                self.assertTrue(
                    any(item.get("expected") == "前往" for item in entry["all_of"])
                )

    def test_club_pipeline_accepts_wrapped_title_prefix(self) -> None:
        for entry_name in (
            "私人会馆兑换任务前往",
            "私人会馆兑换任务已完成",
        ):
            with self.subTest(entry=entry_name):
                title_pattern = self.pipeline[entry_name]["all_of"][0]["expected"]
                self.assertIsNotNone(
                    re.search(title_pattern, "私人会馆商店兑换1次")
                )

    def test_fresh_stock_forward_destination_is_department_store(self) -> None:
        from runner import DAILY_TASK_SPECS

        fresh_stock = next(spec for spec in DAILY_TASK_SPECS if spec.key == "fresh_stock")

        self.assertEqual(fresh_stock.destination_entry, "百货界面已打开")

    def test_return_to_main_prefers_commercial_street_ocr_with_fixed_fallback(self) -> None:
        ocr_entry = self.pipeline["点击商业街返回主页"]
        fallback_entry = self.pipeline["点击商业街返回主页固定位置"]

        self.assertEqual(ocr_entry["recognition"], "OCR")
        self.assertEqual(ocr_entry["expected"], "^商业街$")
        self.assertEqual(fallback_entry["recognition"], "DirectHit")
        self.assertEqual(fallback_entry["target"], [200, 1215])

    @patch("runner.run_confirmed_transition")
    @patch("runner.try_recognize", return_value=True)
    def test_return_to_main_uses_ocr_entry_when_commercial_street_is_recognized(
        self,
        try_recognize,
        run_transition,
    ) -> None:
        reports: list[str] = []

        click_bottom_commercial_street(object(), report=reports.append)

        run_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击商业街返回主页",
            "主界面已到达",
            reports.append,
            None,
        )

    @patch("runner.run_confirmed_transition")
    @patch("runner.try_recognize", return_value=False)
    def test_return_to_main_uses_fixed_entry_only_when_ocr_misses(
        self,
        try_recognize,
        run_transition,
    ) -> None:
        reports: list[str] = []

        click_bottom_commercial_street(object(), report=reports.append)

        run_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击商业街返回主页固定位置",
            "主界面已到达",
            reports.append,
            None,
        )

    def test_guided_fresh_supermarket_fallback_has_fixed_target(self) -> None:
        entry = self.pipeline["点击日常定位的生鲜超市入口"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [270, 570])

    def test_lucky_draw_forward_destination_is_department_store(self) -> None:
        from runner import DAILY_TASK_SPECS

        lucky_draw = next(spec for spec in DAILY_TASK_SPECS if spec.key == "lucky_draw")

        self.assertEqual(lucky_draw.destination_entry, "百货界面已打开")

    def test_club_forward_destination_is_main_screen(self) -> None:
        from runner import DAILY_TASK_SPECS

        club = next(spec for spec in DAILY_TASK_SPECS if spec.key == "club_exchange")

        self.assertEqual(club.destination_entry, "主界面已到达")

    def test_club_home_entry_uses_guided_fixed_position(self) -> None:
        entry = self.pipeline["点击主页私人会馆入口"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [175, 750])
        self.assertEqual(entry["post_delay"], 2500)

    def test_exchange_store_uses_visible_club_tab_and_minutes_card_anchors(self) -> None:
        entry = self.pipeline["兑换商店界面已打开"]

        self.assertEqual(entry["recognition"], "And")
        self.assertEqual(entry["all_of"][0]["expected"], "^会馆$")
        self.assertEqual(entry["all_of"][0]["roi"], [0, 140, 180, 120])
        self.assertEqual(entry["all_of"][1]["expected"], "分钟卡")
        self.assertEqual(entry["all_of"][1]["roi"], [20, 220, 220, 320])

    def test_minutes_card_price_uses_top_left_yellow_button(self) -> None:
        entry = self.pipeline["点击分钟卡价格"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [140, 470])
        self.assertEqual(entry["post_delay"], 1500)

    def test_daily_100_reward_clicks_the_gift_above_the_number(self) -> None:
        entry = self.pipeline["领取日常100活跃礼包"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [610, 320])
        self.assertEqual(entry["post_delay"], 1500)

    def test_duplicate_100_reward_popup_uses_two_amount_anchors(self) -> None:
        entry = self.pipeline["日常100活跃礼包重复领取弹窗"]

        self.assertEqual(entry["recognition"], "And")
        self.assertEqual(
            [item["expected"] for item in entry["all_of"]],
            ["^[0-9]+$", "^[0-9]+$"],
        )

    def test_guided_lucky_draw_fallback_has_fixed_target(self) -> None:
        entry = self.pipeline["点击日常定位的幸运扭蛋入口"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [650, 265])

    def test_movie_city_accepts_visible_signage_and_bottom_anchor(self) -> None:
        entry = self.pipeline["影视城界面已打开"]
        outer_anchor = entry["all_of"][0]

        self.assertIn("影视宣发", outer_anchor["expected"])
        self.assertEqual(outer_anchor["roi"], [0, 0, 720, 1280])

    def test_guided_artist_fallback_has_fixed_target(self) -> None:
        entry = self.pipeline["点击日常定位的艺人入口"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [335, 835])

    def test_artist_page_uses_stable_top_anchors(self) -> None:
        entry = self.pipeline["艺人界面已打开"]

        self.assertEqual(entry["all_of"][0]["expected"], "^艺人$")
        self.assertEqual(
            entry["all_of"][1]["expected"],
            "艺人数量|总魅力|默认排序",
        )

    def test_promotion_button_is_fixed_after_checkbox_guard(self) -> None:
        entry = self.pipeline["宣传"]

        self.assertEqual(entry["recognition"], "DirectHit")
        self.assertEqual(entry["target"], [650, 1110])

    def test_artist_result_uses_close_instruction_anchor(self) -> None:
        entry = self.pipeline["一键宣传结果弹层"]

        self.assertEqual(entry["expected"], "点击任意处关闭")
        self.assertEqual(entry["roi"], [140, 980, 440, 180])

    def test_partner_list_top_statistics_are_fully_covered(self) -> None:
        entry = self.pipeline["伙伴列表界面已打开"]

        self.assertEqual(entry["all_of"][0]["expected"], "^伙伴$")
        self.assertEqual(entry["all_of"][1]["roi"], [0, 80, 720, 240])

    def test_guided_sixth_partner_is_first_candidate(self) -> None:
        from runner import PARTNER_CANDIDATE_ENTRIES

        self.assertEqual(PARTNER_CANDIDATE_ENTRIES[0], "点击第六个伙伴")

    def test_factory_page_accepts_research_build_or_acquisition(self) -> None:
        page_entry = self.pipeline["关卡工厂界面已打开"]
        research_entry = self.pipeline["点击研发按钮"]
        state_entry = self.pipeline["关卡工厂操作按钮已出现"]
        build_entry = self.pipeline["点击建造按钮"]
        acquisition_entry = self.pipeline["点击收购按钮"]
        level_tab_entry = self.pipeline["点击底部关卡标签"]

        self.assertEqual(page_entry["expected"], "^(研发|建造|收购)$")
        self.assertEqual(page_entry["roi"], [0, 250, 720, 800])
        self.assertEqual(research_entry["roi"], [0, 350, 720, 650])
        self.assertEqual(state_entry["expected"], "^(研发|建造|收购)$")
        self.assertEqual(state_entry["action"], "DoNothing")
        self.assertEqual(build_entry["expected"], "^建造$")
        self.assertEqual(build_entry["roi"], [0, 350, 720, 650])
        self.assertEqual(acquisition_entry["expected"], "^收购$")
        self.assertEqual(level_tab_entry["target"], [310, 1215])
        self.assertEqual(
            self.pipeline["关卡工厂研发按钮已出现"]["timeout"],
            2000,
        )

    def test_acquisition_pipeline_has_challenge_skip_and_result_anchors(self) -> None:
        preparation = self.pipeline["收购挑战准备界面已打开"]
        result = self.pipeline["收购谈判成功结果"]

        self.assertTrue(
            any(item.get("expected") == "开始挑战" for item in preparation["all_of"])
        )
        self.assertEqual(self.pipeline["跳过收购谈判"]["expected"], "^跳过$")
        self.assertTrue(
            any(item.get("expected") == "点击任意处关闭" for item in result["all_of"])
        )


class FactoryResearchFlowTests(unittest.TestCase):
    @patch("runner.time.sleep")
    @patch("runner.capture_debug_step")
    @patch("runner.ensure_factory_auto_research_unselected")
    @patch("runner._try_recognize_once")
    @patch("runner._try_execute_once")
    def test_builds_first_then_counts_only_research_clicks(
        self,
        try_execute_once,
        try_recognize_once,
        ensure_auto_research_unselected,
        capture_debug_step,
        sleep,
    ) -> None:
        states = ["建造"] + ["研发"] * 7
        clicked: list[str] = []
        research_detection_timeouts: list[int] = []

        def execute(_tasker, entry: str, _timeout: int) -> bool:
            if entry not in {"点击研发按钮", "点击建造按钮"}:
                return False
            expected = "研发" if entry == "点击研发按钮" else "建造"
            if states and states[0] == expected:
                clicked.append(states.pop(0))
                return True
            return False

        def recognize(_tasker, entry: str, timeout_ms: int) -> bool:
            if entry == "关卡工厂研发按钮已出现":
                research_detection_timeouts.append(timeout_ms)
                return bool(states and states[0] == "研发")
            if entry == "点击收购按钮":
                return False
            return False

        try_execute_once.side_effect = execute
        try_recognize_once.side_effect = recognize
        reports: list[str] = []

        complete_factory_research_actions(object(), object(), report=reports.append)

        self.assertEqual(clicked, ["建造"] + ["研发"] * 7)
        self.assertEqual(states, [])
        self.assertTrue(any("建造" in message and "不计入" in message for message in reports))
        self.assertTrue(any("研发进度 7/7" in message for message in reports))
        self.assertEqual(ensure_auto_research_unselected.call_count, 7)
        self.assertTrue(research_detection_timeouts)
        self.assertTrue(all(value == 2000 for value in research_detection_timeouts))
        capture_debug_step.assert_not_called()

    @patch("runner.complete_factory_acquisition")
    @patch("runner.run_confirmed_transition")
    def test_reenters_level_tab_when_current_factory_has_no_build_or_research(
        self,
        run_confirmed_transition,
        complete_factory_acquisition,
    ) -> None:
        reports: list[str] = []

        reenter_factory_level_tab_for_acquisition(object(), report=reports.append)

        run_confirmed_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击底部关卡标签",
            "关卡地图收购已出现",
            reports.append,
            None,
        )
        complete_factory_acquisition.assert_called_once_with(
            unittest.mock.ANY,
            reports.append,
            None,
        )
        self.assertTrue(any("本关建设已完成" in message for message in reports))

    @patch("runner.confirm_transition")
    @patch("runner.run_task")
    @patch("runner.run_confirmed_transition")
    @patch("runner.time.sleep")
    @patch("runner._try_execute_once", return_value=True)
    @patch("runner._try_recognize_once", side_effect=[False, True])
    def test_acquisition_clicks_optional_skip_then_closes_success_result(
        self,
        try_recognize_once,
        try_execute_once,
        sleep,
        run_confirmed_transition,
        run_task,
        confirm_transition,
    ) -> None:
        reports: list[str] = []

        complete_factory_acquisition(object(), report=reports.append)

        run_confirmed_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击收购按钮",
            "收购挑战准备界面已打开",
            reports.append,
            None,
        )
        self.assertEqual(
            [call.args[1] for call in run_task.call_args_list],
            ["点击开始收购挑战", "关闭收购谈判成功结果"],
        )
        try_execute_once.assert_called_once_with(
            unittest.mock.ANY,
            "跳过收购谈判",
            unittest.mock.ANY,
        )
        confirm_transition.assert_called_once()
        self.assertTrue(any("是否点击过跳过=是" in message for message in reports))

    @patch("runner.confirm_transition")
    @patch("runner.run_task")
    @patch("runner.run_confirmed_transition")
    @patch("runner._try_execute_once")
    @patch("runner._try_recognize_once", return_value=True)
    def test_acquisition_allows_result_to_finish_before_skip_is_detected(
        self,
        try_recognize_once,
        try_execute_once,
        run_confirmed_transition,
        run_task,
        confirm_transition,
    ) -> None:
        reports: list[str] = []

        complete_factory_acquisition(object(), report=reports.append)

        try_execute_once.assert_not_called()
        self.assertTrue(any("是否点击过跳过=否" in message for message in reports))


class FreshSupermarketEntryTests(unittest.TestCase):
    @patch("runner.run_confirmed_transition")
    @patch("runner.try_recognize", return_value=False)
    @patch("runner.run_task")
    @patch("runner.run_daily_forward")
    def test_uses_guided_position_when_text_is_obscured(
        self,
        run_daily_forward,
        run_task,
        try_recognize,
        run_confirmed_transition,
    ) -> None:
        reports: list[str] = []

        enter_fresh_supermarket_from_daily(
            object(), object(), report=reports.append
        )

        run_daily_forward.assert_called_once_with(
            unittest.mock.ANY,
            unittest.mock.ANY,
            "生鲜超市进货任务前往",
            "百货界面已打开",
            reports.append,
            None,
        )
        run_task.assert_called_once_with(
            unittest.mock.ANY,
            "百货界面已打开",
            reports.append,
            None,
        )
        run_confirmed_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击日常定位的生鲜超市入口",
            "生鲜超市界面已打开",
            reports.append,
            None,
        )
        self.assertTrue(any("引导手指遮挡" in message for message in reports))


class LuckyDrawEntryTests(unittest.TestCase):
    @patch("runner.run_confirmed_transition")
    @patch("runner.try_recognize", return_value=False)
    @patch("runner.run_task")
    @patch("runner.run_daily_forward")
    def test_enters_department_store_then_uses_guided_position_when_ocr_fails(
        self,
        run_daily_forward,
        run_task,
        try_recognize,
        run_confirmed_transition,
    ) -> None:
        reports: list[str] = []

        enter_lucky_draw_from_daily(
            object(), object(), report=reports.append
        )

        run_daily_forward.assert_called_once_with(
            unittest.mock.ANY,
            unittest.mock.ANY,
            "幸运扭蛋任务前往",
            "百货界面已打开",
            reports.append,
            None,
        )
        run_task.assert_called_once_with(
            unittest.mock.ANY,
            "百货界面已打开",
            reports.append,
            None,
        )
        run_confirmed_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击日常定位的幸运扭蛋入口",
            "幸运扭蛋界面已打开",
            reports.append,
            None,
        )
        self.assertTrue(any("右上入口区域" in message for message in reports))


class ArtistEntryTests(unittest.TestCase):
    @patch("runner.run_confirmed_transition")
    @patch("runner.try_recognize", return_value=False)
    @patch("runner.run_task")
    @patch("runner.run_daily_forward")
    def test_recognizes_movie_city_then_uses_guided_position_when_ocr_fails(
        self,
        run_daily_forward,
        run_task,
        try_recognize,
        run_confirmed_transition,
    ) -> None:
        reports: list[str] = []

        enter_artist_from_daily(object(), object(), report=reports.append)

        run_daily_forward.assert_called_once_with(
            unittest.mock.ANY,
            unittest.mock.ANY,
            "艺人宣传任务前往",
            "影视城界面已打开",
            reports.append,
            None,
        )
        run_task.assert_called_once_with(
            unittest.mock.ANY,
            "影视城界面已打开",
            reports.append,
            None,
        )
        run_confirmed_transition.assert_called_once_with(
            unittest.mock.ANY,
            "点击日常定位的艺人入口",
            "艺人界面已打开",
            reports.append,
            None,
        )
        self.assertTrue(any("引导手指遮挡" in message for message in reports))

    @patch("runner.return_to_daily")
    @patch("runner.click_bottom_commercial_street")
    @patch("runner.run_confirmed_transition")
    @patch("runner.dismiss_result_overlay")
    @patch("runner.run_task")
    @patch("runner.ensure_checkbox_selected")
    @patch("runner.enter_artist_from_daily")
    def test_selects_one_click_promotion_before_clicking_promotion(
        self,
        enter_artist,
        ensure_checkbox,
        run_task,
        dismiss_result,
        run_transition,
        click_bottom,
        return_daily,
    ) -> None:
        events: list[str] = []
        enter_artist.side_effect = lambda *args, **kwargs: events.append("enter")
        ensure_checkbox.side_effect = lambda *args, **kwargs: events.append("checkbox")
        run_task.side_effect = lambda *args, **kwargs: events.append(args[1])
        dismiss_result.side_effect = lambda *args, **kwargs: events.append("result")

        complete_artist_daily_group(
            object(),
            object(),
            {"artist_promote": DAILY_STATE_TODO},
        )

        self.assertEqual(events[:4], ["enter", "checkbox", "宣传", "result"])


if __name__ == "__main__":
    unittest.main()
