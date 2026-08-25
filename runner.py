from __future__ import annotations

from dataclasses import dataclass
from getpass import getpass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Callable

import numpy as np
from PIL import Image
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import AdbDevice, Toolkit


SOURCE_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
APPLICATION_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_DIR
RESOURCE_DIR = BUNDLE_DIR / "resource"
RUNTIME_DIR = APPLICATION_DIR / "runtime"
OCR_DIR = RESOURCE_DIR / "model" / "ocr"
OCR_FILES = ("det.onnx", "rec.onnx", "keys.txt")
RUNTIME_OPTION_PATH = RUNTIME_DIR / "config" / "maa_option.json"
CLIENT_CONFIG_PATH = RUNTIME_DIR / "config" / "client_config.json"
LOCAL_ADB_CANDIDATES = (
    Path(r"D:\Android\Sdk\platform-tools\adb.exe"),
    Path(r"C:\Android\Sdk\platform-tools\adb.exe"),
)
MUMU_MANAGER_CANDIDATES = (
    Path(r"D:\MuMu Player 12\nx_main\MuMuManager.exe"),
    Path(r"C:\Program Files\Netease\MuMuPlayer-12.0\nx_main\MuMuManager.exe"),
)
ADB_SCREEN_EMULATOR_EXTRAS = 1 << 6
ADB_INPUT_DEFAULT = (1 << 64) - 1 - (1 << 3)
REFERENCE_SCREEN_WIDTH = 720
REFERENCE_SCREEN_HEIGHT = 1280
POPUP_QUIET_SECONDS = 5.0
OFFLINE_REWARD_WAIT_SECONDS = 20.0
POPUP_POLL_TIMEOUT_MS = 250
POPUP_POLL_INTERVAL_SECONDS = 0.15
INTERRUPTING_POPUP_MAX_RECOVERIES = 30
INTERRUPTING_POPUP_REFRESH_SECONDS = 0.5
INTERRUPTING_POPUP_MAX_CONSECUTIVE_ROUNDS = 30
INTERRUPTING_POPUP_CHECKBOX_SETTLE_SECONDS = 1.0
INTERRUPTING_POPUP_CLOSE_SETTLE_SECONDS = 1.0
INTERRUPTING_POPUP_CLOSE_ATTEMPTS = 3
INTERRUPTING_POPUP_ENTRIES = {
    "商战冠军点击任意处弹窗",
    "本次登录不再提示弹窗",
    "任意活动稍后再去弹窗",
}
UNKNOWN_POPUP_FALLBACK_ROUNDS = 3
UNKNOWN_POPUP_FALLBACK_RETURN_POSITION = (50, 1230)
UNKNOWN_POPUP_CLICK_SETTLE_SECONDS = 0.75
UNKNOWN_POPUP_FALLBACK_EXCLUDED_ENTRIES = {"打开游戏到登录页"}
MAIN_SCREEN_ANCHORS = (
    ("主界面锚点百货", "左下“百货”"),
    ("主界面锚点关卡伙伴", "底部“关卡/伙伴”"),
    ("主界面锚点影视城背包", "底部“影视城/背包”"),
)
MAIN_SCREEN_FIXED_ENTRY_ANCHOR = (
    "主界面锚点日常商店",
    "右侧“日常/商店”",
)
MAIN_SCREEN_REQUIRED_ANCHORS = 2
MAIN_SCREEN_INITIAL_CHECK_ROUNDS = 3
MAIN_SCREEN_CHECK_INTERVAL_SECONDS = 0.5
CHECKBOX_CONFIRM_TIMEOUT_SECONDS = 3.0
CHECKBOX_CONFIRM_INTERVAL_SECONDS = 0.25
DO_NOT_REMIND_CHECKBOX = (278, 1122)
DO_NOT_REMIND_CLOSE = (646, 194)
MONTHLY_SIGN_IN_BUTTON = (360, 994)
MONTHLY_SIGN_IN_MAX_ATTEMPTS = 2
SERVER_LIST_MAX_SWIPES = 24
DAILY_LIST_MAX_SWIPES = 20
DAILY_TASK_SEEK_SWIPES = 20
DAILY_TASK_REWIND_SWIPES = 8
DAILY_INVENTORY_MAX_SWIPES = 20
DAILY_TASK_ROW_Y_TOLERANCE = 85
DAILY_FORWARD_POST_CLICK_SECONDS = 2.0
DAILY_100_REWARD_RESULT_TIMEOUT_SECONDS = 5.0
DEFAULT_GAME_PACKAGE = "com.tomato.android.ssbhw"
DAILY_STATE_TODO = "待完成"
DAILY_STATE_CLAIMABLE = "可领取"
DAILY_STATE_CLAIMED = "已领取"
DAILY_STATE_UNKNOWN = "未识别"
DAILY_TASK_LABEL_ALIASES = {
    "私人会馆商店兑换1次商品": ("私人会馆商店兑换1次",),
}
FACTORY_RESEARCH_TARGET_COUNT = 7
FACTORY_STATE_MAX_TRANSITIONS = 40
FACTORY_STATE_RECOGNITION_TIMEOUT_MS = 2000
FACTORY_STATE_SETTLE_SECONDS = 0.8
FACTORY_ACQUISITION_TIMEOUT_SECONDS = 30.0
FACTORY_ACQUISITION_POLL_SECONDS = 0.25
FACTORY_AUTO_RESEARCH_FIXED_CENTER = (85, 699)
FACTORY_AUTO_RESEARCH_CHECK_OFFSET_X = 13
FACTORY_AUTO_RESEARCH_INNER_RADIUS = 6
FACTORY_AUTO_RESEARCH_GREEN_COUNT = 5
DEPARTMENT_STORE_VERTICAL_VIEWPORTS = 8
DEPARTMENT_STORE_HORIZONTAL_VIEWPORTS = 3
DEPARTMENT_STORE_VERTICAL_REWIND_SWIPES = 6
DEPARTMENT_STORE_HORIZONTAL_REWIND_SWIPES = 3
DAILY_ACTION_RETRIES = 4
DAILY_TRANSITION_CHECKS = 3
DAILY_DESTINATION_TIMEOUT_MS = 2000
DAILY_SOURCE_PAGE_TIMEOUT_MS = 1000
TRANSITION_CONFIRM_TIMEOUT_SECONDS = 3.0
TRANSITION_CONFIRM_POLL_TIMEOUT_MS = 500
TRANSITION_CONFIRM_POLL_INTERVAL_SECONDS = 0.1
TRANSITION_ACTION_RETRIES = 3
LUCKY_DRAW_RESULT_TIMEOUT_SECONDS = 20.0
ARTIST_PROMOTION_RESULT_TIMEOUT_SECONDS = 5.0
PARTNER_CANDIDATE_ENTRIES = (
    "点击第六个伙伴",
    "点击第五个伙伴",
    "点击第四个伙伴",
)
Reporter = Callable[[str], None]


@dataclass(frozen=True)
class DailyTaskSpec:
    key: str
    label: str
    forward_entry: str
    destination_entry: str
    group: str


@dataclass(frozen=True)
class DailyOcrText:
    text: str
    box: tuple[int, int, int, int]


DAILY_TASK_SPECS = (
    DailyTaskSpec(
        "store_upgrade",
        "任意店铺升级10次",
        "任意店铺升级任务前往",
        "百货界面已打开",
        "百货",
    ),
    DailyTaskSpec(
        "fresh_stock",
        "生鲜超市进货1次",
        "生鲜超市进货任务前往",
        "百货界面已打开",
        "百货",
    ),
    DailyTaskSpec(
        "lucky_draw",
        "幸运扭蛋抽奖1次",
        "幸运扭蛋任务前往",
        "百货界面已打开",
        "百货",
    ),
    DailyTaskSpec(
        "club_exchange",
        "私人会馆商店兑换1次商品",
        "私人会馆兑换任务前往",
        "主界面已到达",
        "百货",
    ),
    DailyTaskSpec(
        "artist_promote",
        "艺人宣传3次",
        "艺人宣传任务前往",
        "影视城界面已打开",
        "艺人",
    ),
    DailyTaskSpec(
        "partner_upgrade",
        "伙伴升级5次",
        "伙伴升级任务前往",
        "伙伴列表界面已打开",
        "伙伴",
    ),
    DailyTaskSpec(
        "factory_research",
        "关卡工厂研发5次",
        "关卡工厂研发任务前往",
        "关卡工厂界面已打开",
        "工厂",
    ),
)


class AutomationCancelled(RuntimeError):
    pass


class StepScreenshotRecorder:
    """按执行顺序保存调试截图；截图失败不影响自动化主流程。"""

    def __init__(
        self,
        controller: AdbController,
        output_dir: Path,
        report: Reporter,
    ) -> None:
        self.controller = controller
        self.output_dir = output_dir
        self.report = report
        self.counter = 0
        self.disabled = False
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def capture(self, label: str) -> None:
        if self.disabled:
            return
        self.counter += 1
        path = self.output_dir / f"step-{self.counter:04d}.png"
        try:
            job = self.controller.post_screencap()
            job.wait()
            if not job.succeeded:
                raise RuntimeError("MaaFramework 截图任务失败")
            image = job.get()
            if image is None or image.ndim != 3 or image.shape[2] != 3:
                raise RuntimeError("截图数据为空或通道数异常")
            rgb_image = np.ascontiguousarray(image[:, :, ::-1])
            Image.fromarray(rgb_image).save(path, format="PNG")
            self.report(f"[调试截图] {path.name}：{label}")
        except Exception as error:
            self.disabled = True
            self.report(f"[调试截图] 保存失败，已停止本次截图：{error}")


_ACTIVE_STEP_SCREENSHOT_RECORDER: StepScreenshotRecorder | None = None


def capture_debug_step(label: str) -> None:
    recorder = _ACTIVE_STEP_SCREENSHOT_RECORDER
    if recorder is not None:
        recorder.capture(label)


def ensure_not_cancelled(cancel_event=None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AutomationCancelled("用户已停止任务。")


def prepare_secure_runtime() -> None:
    RUNTIME_OPTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    options = {
        "draw_quality": 85,
        "logging": False,
        "save_draw": False,
        "save_on_error": False,
        "stdout_level": 2,
    }
    RUNTIME_OPTION_PATH.write_text(
        json.dumps(options, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def load_local_config() -> dict:
    if not CLIENT_CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(CLIENT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_account_configs(config: dict | None = None) -> list[dict]:
    """读取多账号配置，并兼容旧版单账号配置结构。"""
    if config is None:
        config = load_local_config()

    raw_accounts = config.get("accounts")
    if isinstance(raw_accounts, list):
        accounts = []
        for item in raw_accounts:
            if not isinstance(item, dict):
                continue
            try:
                server_number = int(item.get("server_number", 1))
            except (TypeError, ValueError):
                server_number = 1
            accounts.append(
                {
                    "account": str(item.get("account", "")).strip(),
                    "password": str(item.get("password", "")),
                    "server_number": server_number,
                    "active": bool(item.get("active", True)),
                }
            )
        if accounts:
            return accounts

    account = str(config.get("account", "")).strip()
    password = str(config.get("password", ""))
    try:
        server_number = int(config.get("server_number", 1))
    except (TypeError, ValueError):
        server_number = 1
    if account or password:
        return [
            {
                "account": account,
                "password": password,
                "server_number": server_number,
                "active": True,
            }
        ]
    return []


def save_account_configs(accounts: list[dict]) -> None:
    """原子保存账号队列；每个账号保留独立的启用状态。"""
    normalized_accounts = []
    for item in accounts:
        account = str(item.get("account", "")).strip()
        password = str(item.get("password", ""))
        server_number = int(item.get("server_number", 1))
        validate_credential(account, "账号")
        validate_credential(password, "密码")
        validate_server_number(server_number)
        normalized_accounts.append(
            {
                "account": account,
                "password": password,
                "server_number": server_number,
                "active": bool(item.get("active", True)),
            }
        )

    CLIENT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"accounts": normalized_accounts}
    temp_path = CLIENT_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(CLIENT_CONFIG_PATH)


def save_local_config(account: str, password: str, server_number: int) -> None:
    save_account_configs(
        [
            {
                "account": account,
                "password": password,
                "server_number": server_number,
                "active": True,
            }
        ]
    )


def clear_local_config() -> None:
    if CLIENT_CONFIG_PATH.is_file():
        CLIENT_CONFIG_PATH.unlink()


def require_ocr_model() -> None:
    missing = [name for name in OCR_FILES if not (OCR_DIR / name).is_file()]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"缺少 OCR 模型文件：{names}\n"
            f"请将 MaaCommonAssets 的中文 OCR 模型放入：{OCR_DIR}"
        )


def distribution_self_check() -> None:
    """供便携包构建流程验证资源和 MaaFramework 原生库。"""
    from maa.library import Library

    require_ocr_model()
    version = Library.version()
    if not version:
        raise RuntimeError("无法读取 MaaFramework 版本。")


def validate_reference_canvas(controller: AdbController, report: Reporter = print) -> None:
    """确认 MaaFramework 已生成 720×1280 的竖屏识别画布。"""
    image = capture_screen(controller)
    height, width = image.shape[:2]
    raw_width, raw_height = controller.resolution
    report(
        f"[显示适配] 模拟器原始分辨率 {raw_width}×{raw_height}，"
        f"识别画布 {width}×{height}"
    )
    if (width, height) != (REFERENCE_SCREEN_WIDTH, REFERENCE_SCREEN_HEIGHT):
        raise RuntimeError(
            "模拟器必须使用 9:16 竖屏分辨率。支持 720×1280、1080×1920、"
            "1440×2560、2160×3840 等同比例分辨率；"
            f"当前识别画布为 {width}×{height}。"
        )


def find_mumu_devices() -> list[AdbDevice]:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for manager_path in MUMU_MANAGER_CANDIDATES:
        if not manager_path.is_file():
            continue

        process = subprocess.run(
            [str(manager_path), "info", "--vmindex", "all"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=creation_flags,
        )
        if process.returncode != 0:
            continue

        try:
            raw_info = json.loads(process.stdout)
        except json.JSONDecodeError:
            continue

        infos = (
            list(raw_info.values())
            if isinstance(raw_info, dict) and "index" not in raw_info
            else [raw_info]
        )
        devices: list[AdbDevice] = []
        for info in infos:
            if not isinstance(info, dict) or not info.get("is_process_started"):
                continue
            host = info.get("adb_host_ip")
            port = info.get("adb_port")
            index = info.get("index")
            if not host or not isinstance(port, int) or not str(index).isdigit():
                continue

            adb_path = manager_path.parent / "adb.exe"
            if not adb_path.is_file():
                continue
            devices.append(
                AdbDevice(
                    name="MuMu安卓设备-MuMuPlayer v5+",
                    adb_path=adb_path,
                    address=f"{host}:{port}",
                    screencap_methods=ADB_SCREEN_EMULATOR_EXTRAS,
                    input_methods=ADB_INPUT_DEFAULT,
                    config={
                        "extras": {
                            "mumu": {
                                "enable": True,
                                "path": str(manager_path.parent.parent),
                                "index": int(index),
                            }
                        }
                    },
                )
            )
        if devices:
            return devices

    return []


def find_adb_devices():
    devices = Toolkit.find_adb_devices()
    special_devices = [device for device in devices if device.config.get("extras")]
    if special_devices:
        return special_devices

    mumu_devices = find_mumu_devices()
    if mumu_devices:
        return mumu_devices

    if devices:
        return devices

    candidates: list[Path] = []
    configured = os.environ.get("ADB_PATH")
    if configured:
        candidates.append(Path(configured))

    path_adb = shutil.which("adb")
    if path_adb:
        candidates.append(Path(path_adb))

    candidates.extend(LOCAL_ADB_CANDIDATES)
    for adb_path in candidates:
        if not adb_path.is_file():
            continue
        devices = Toolkit.find_adb_devices(adb_path)
        if devices:
            return devices

    return []


def choose_device():
    devices = find_adb_devices()
    if not devices:
        raise RuntimeError(
            "没有发现 ADB 设备。请先启动 MuMu 模拟器并开启 ADB；"
            "如 ADB 位于自定义目录，请设置 ADB_PATH。"
        )

    if len(devices) == 1:
        return devices[0]

    print("发现多个 ADB 设备：")
    for index, device in enumerate(devices, start=1):
        print(f"  {index}. {device.name} ({device.address})")

    while True:
        raw = input("请选择设备编号：").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(devices):
            return devices[int(raw) - 1]
        print("设备编号无效，请重新输入。")


def wait_job(job, label: str):
    job.wait()
    if not job.succeeded:
        capture_debug_step(f"失败：{label}")
        raise RuntimeError(f"{label}失败。请检查模拟器当前页面后重试。")
    capture_debug_step(f"完成：{label}")
    return job


def _task_succeeded(job) -> bool:
    job.wait()
    if not job.succeeded:
        return False
    detail = job.get()
    return detail is not None and detail.status.succeeded


def _try_recognize_once(
    tasker: Tasker,
    entry: str,
    timeout_ms: int,
) -> bool:
    override = {
        entry: {
            "action": "DoNothing",
            "next": [],
            "pre_delay": 0,
            "post_delay": 0,
            "timeout": timeout_ms,
        }
    }
    return _task_succeeded(tasker.post_task(entry, override))


def _try_execute_once(
    tasker: Tasker,
    entry: str,
    timeout_ms: int,
) -> bool:
    override = {
        entry: {
            "next": [],
            "pre_delay": 0,
            "post_delay": 0,
            "timeout": timeout_ms,
        }
    }
    succeeded = _task_succeeded(tasker.post_task(entry, override))
    if succeeded:
        capture_debug_step(f"完成可选动作：{entry}")
    return succeeded


def handle_interrupting_login_popup(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
    detection_timeout_ms: int = 1000,
) -> bool:
    """循环关闭反复出现的登录赠礼页及其随后奖励层。"""
    ensure_not_cancelled(cancel_event)
    handled_rounds = 0
    next_detection_timeout_ms = detection_timeout_ms

    while _try_recognize_once(
        tasker,
        "本次登录不再提示弹窗",
        timeout_ms=next_detection_timeout_ms,
    ):
        ensure_not_cancelled(cancel_event)
        handled_rounds += 1
        if handled_rounds > INTERRUPTING_POPUP_MAX_CONSECUTIVE_ROUNDS:
            raise RuntimeError(
                "本次登录赠礼连续出现超过"
                f" {INTERRUPTING_POPUP_MAX_CONSECUTIVE_ROUNDS} 轮，已停止后续操作。"
            )

        report(
            f"[弹窗恢复] 检测到本次登录赠礼（第 {handled_rounds} 轮），"
            "勾选不再提示并关闭"
        )
        if not _try_execute_once(
            tasker,
            "勾选本次登录不再提示固定位置",
            timeout_ms=1000,
        ):
            raise RuntimeError("检测到本次登录赠礼，但勾选不再提示失败。")
        report("[选项检查] 勾选点击已执行：本次登录不再提示")
        time.sleep(INTERRUPTING_POPUP_CHECKBOX_SETTLE_SECONDS)

        gift_still_visible = True
        reward_found = False
        for close_attempt in range(1, INTERRUPTING_POPUP_CLOSE_ATTEMPTS + 1):
            ensure_not_cancelled(cancel_event)
            report(
                f"[弹窗恢复] 第 {handled_rounds} 轮点击关闭登录赠礼"
                f"（{close_attempt}/{INTERRUPTING_POPUP_CLOSE_ATTEMPTS}）"
            )
            if not _try_execute_once(
                tasker,
                "关闭本次登录幸运赠礼固定位置",
                timeout_ms=1000,
            ):
                raise RuntimeError("检测到本次登录赠礼，但关闭弹窗点击失败。")
            time.sleep(INTERRUPTING_POPUP_CLOSE_SETTLE_SECONDS)

            if _try_recognize_once(
                tasker,
                "中断赠礼恭喜获得弹层",
                timeout_ms=1500,
            ):
                reward_found = True
                break

            gift_still_visible = _try_recognize_once(
                tasker,
                "本次登录不再提示弹窗",
                timeout_ms=750,
            )
            if gift_still_visible:
                if close_attempt < INTERRUPTING_POPUP_CLOSE_ATTEMPTS:
                    report(
                        f"[弹窗恢复] 第 {handled_rounds} 轮关闭未生效，"
                        "原赠礼页仍在；等待后只重试关闭，不再点击勾选框"
                    )
                    time.sleep(INTERRUPTING_POPUP_CLOSE_SETTLE_SECONDS)
                continue

            # 原赠礼页已经消失，但奖励层可能仍在过场动画中；此时只等待，
            # 不能继续点击固定关闭位置，以免误触底层页面。
            for _ in range(4):
                ensure_not_cancelled(cancel_event)
                time.sleep(0.5)
                if _try_recognize_once(
                    tasker,
                    "中断赠礼恭喜获得弹层",
                    timeout_ms=1000,
                ):
                    reward_found = True
                    break
            break

        if not reward_found:
            if gift_still_visible:
                raise RuntimeError(
                    "本次登录赠礼连续 3 次点击关闭仍未生效，原赠礼页仍然遮挡界面。"
                )
            report(
                f"[弹窗恢复] 第 {handled_rounds} 轮登录赠礼页已关闭，"
                "等待后未出现“恭喜获得”；按可选后续弹窗处理，继续原流程"
            )
            next_detection_timeout_ms = 1000
            continue

        report(
            f"[弹窗恢复] 第 {handled_rounds} 轮检测到“恭喜获得”，"
            "点击任意位置关闭"
        )
        reward_closed = False
        for close_attempt in range(1, INTERRUPTING_POPUP_CLOSE_ATTEMPTS + 1):
            ensure_not_cancelled(cancel_event)
            if not _try_execute_once(
                tasker,
                "关闭中断赠礼恭喜获得固定位置",
                timeout_ms=1000,
            ):
                raise RuntimeError("检测到“恭喜获得”奖励层，但点击关闭失败。")
            time.sleep(INTERRUPTING_POPUP_CLOSE_SETTLE_SECONDS)
            if not _try_recognize_once(
                tasker,
                "中断赠礼恭喜获得弹层",
                timeout_ms=750,
            ):
                reward_closed = True
                break
            if close_attempt < INTERRUPTING_POPUP_CLOSE_ATTEMPTS:
                report(
                    f"[弹窗恢复] 第 {handled_rounds} 轮“恭喜获得”仍在，"
                    f"重试关闭（{close_attempt + 1}/{INTERRUPTING_POPUP_CLOSE_ATTEMPTS}）"
                )
        if not reward_closed:
            raise RuntimeError("“恭喜获得”奖励层关闭后仍然遮挡界面。")

        # 赠礼可能在奖励层关闭后立即重新弹出。下一轮继续完整处理，
        # 不能把新弹窗误判为上一轮关闭失败。
        next_detection_timeout_ms = 1000

    if handled_rounds == 0:
        return False

    report(
        f"[弹窗恢复] 已连续处理 {handled_rounds} 轮登录赠礼，"
        "当前界面不再被遮挡，恢复原流程"
    )
    return True


def handle_interrupting_activity_popup(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
    detection_timeout_ms: int = 1000,
) -> bool:
    """处理任意时机出现、以“稍后再去”为稳定锚点的活动弹窗。"""
    ensure_not_cancelled(cancel_event)
    if not _try_recognize_once(
        tasker,
        "任意活动稍后再去弹窗",
        timeout_ms=detection_timeout_ms,
    ):
        return False

    report("[弹窗恢复] 检测到活动跳转弹窗，勾选今天不再提示")
    if not _try_execute_once(
        tasker,
        "勾选任意活动今天不再提示固定位置",
        timeout_ms=1000,
    ):
        raise RuntimeError("检测到活动跳转弹窗，但勾选今天不再提示失败。")
    report("[选项检查] 勾选点击已执行：活动今天不再提示")
    time.sleep(INTERRUPTING_POPUP_CHECKBOX_SETTLE_SECONDS)

    for close_attempt in range(1, INTERRUPTING_POPUP_CLOSE_ATTEMPTS + 1):
        ensure_not_cancelled(cancel_event)
        report(
            "[弹窗恢复] 点击稍后再去关闭活动弹窗"
            f"（{close_attempt}/{INTERRUPTING_POPUP_CLOSE_ATTEMPTS}）"
        )
        if not _try_execute_once(
            tasker,
            "点击任意活动稍后再去",
            timeout_ms=1000,
        ):
            raise RuntimeError("检测到活动跳转弹窗，但点击稍后再去失败。")
        time.sleep(INTERRUPTING_POPUP_CLOSE_SETTLE_SECONDS)
        if not _try_recognize_once(
            tasker,
            "任意活动稍后再去弹窗",
            timeout_ms=750,
        ):
            report("[弹窗恢复] 活动跳转弹窗已关闭，恢复原流程")
            return True
        if close_attempt < INTERRUPTING_POPUP_CLOSE_ATTEMPTS:
            report("[弹窗恢复] 活动跳转弹窗仍在，准备重试稍后再去")

    raise RuntimeError("活动跳转弹窗连续 3 次点击稍后再去仍未关闭。")


def handle_interrupting_tap_anywhere_popup(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
    detection_timeout_ms: int = 1000,
) -> bool:
    """处理任意时机出现、以“点击任意处关闭”为锚点的展示弹窗。"""
    ensure_not_cancelled(cancel_event)
    if not _try_recognize_once(
        tasker,
        "商战冠军点击任意处弹窗",
        timeout_ms=detection_timeout_ms,
    ):
        return False

    report("[弹窗恢复] 检测到商战冠军展示弹窗，点击任意处关闭")
    for close_attempt in range(1, INTERRUPTING_POPUP_CLOSE_ATTEMPTS + 1):
        ensure_not_cancelled(cancel_event)
        if not _try_execute_once(
            tasker,
            "点击关闭商战冠军弹窗固定位置",
            timeout_ms=1000,
        ):
            raise RuntimeError("检测到商战冠军展示弹窗，但点击关闭失败。")
        time.sleep(INTERRUPTING_POPUP_CLOSE_SETTLE_SECONDS)
        if not _try_recognize_once(
            tasker,
            "商战冠军点击任意处弹窗",
            timeout_ms=750,
        ):
            report("[弹窗恢复] 商战冠军展示弹窗已关闭，恢复原流程")
            return True
        if close_attempt < INTERRUPTING_POPUP_CLOSE_ATTEMPTS:
            report(
                "[弹窗恢复] 商战冠军展示弹窗仍在，准备重试任意处关闭"
                f"（{close_attempt + 1}/{INTERRUPTING_POPUP_CLOSE_ATTEMPTS}）"
            )

    raise RuntimeError("商战冠军展示弹窗连续 3 次点击后仍未关闭。")


def handle_interrupting_popups(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
    detection_timeout_ms: int = 1000,
) -> bool:
    """持续清理所有允许在自动化任意阶段出现的中断弹窗。"""
    handled_any = False
    next_detection_timeout_ms = detection_timeout_ms
    for _ in range(INTERRUPTING_POPUP_MAX_CONSECUTIVE_ROUNDS):
        if handle_interrupting_tap_anywhere_popup(
            tasker,
            report,
            cancel_event,
            detection_timeout_ms=next_detection_timeout_ms,
        ):
            handled_any = True
            next_detection_timeout_ms = 500
            continue
        if handle_interrupting_activity_popup(
            tasker,
            report,
            cancel_event,
            detection_timeout_ms=next_detection_timeout_ms,
        ):
            handled_any = True
            next_detection_timeout_ms = 500
            continue
        if handle_interrupting_login_popup(
            tasker,
            report,
            cancel_event,
            detection_timeout_ms=next_detection_timeout_ms,
        ):
            handled_any = True
            next_detection_timeout_ms = 500
            continue
        return handled_any

    raise RuntimeError(
        "连续处理中断弹窗超过"
        f" {INTERRUPTING_POPUP_MAX_CONSECUTIVE_ROUNDS} 轮，已停止后续操作。"
    )


def main_screen_is_reached(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
    total_timeout_ms: int = 1500,
    context: str = "检查",
) -> bool:
    """底部导航多数命中且主页固定入口命中时，才确认到达主界面。"""
    ensure_not_cancelled(cancel_event)
    total_checks = len(MAIN_SCREEN_ANCHORS) + 1
    per_anchor_timeout_ms = max(1, total_timeout_ms // total_checks)
    results: list[tuple[str, bool]] = []
    for entry, label in MAIN_SCREEN_ANCHORS:
        ensure_not_cancelled(cancel_event)
        matched = _try_recognize_once(
            tasker,
            entry,
            timeout_ms=per_anchor_timeout_ms,
        )
        results.append((label, matched))
        report(
            f"[主界面识别] {context}：{label}="
            f"{'命中' if matched else '未命中'}"
        )

    fixed_entry, fixed_label = MAIN_SCREEN_FIXED_ENTRY_ANCHOR
    ensure_not_cancelled(cancel_event)
    fixed_entry_matched = _try_recognize_once(
        tasker,
        fixed_entry,
        timeout_ms=per_anchor_timeout_ms,
    )
    report(
        f"[主界面识别] {context}：{fixed_label}="
        f"{'命中' if fixed_entry_matched else '未命中'}"
    )

    matched_count = sum(matched for _, matched in results)
    navigation_reached = matched_count >= MAIN_SCREEN_REQUIRED_ANCHORS
    reached = navigation_reached and fixed_entry_matched
    summary = "，".join(
        f"{label}:{'✓' if matched else '×'}" for label, matched in results
    )
    report(
        f"[主界面识别] {context}汇总：{summary}；"
        f"导航命中 {matched_count}/{len(results)}，"
        f"要求至少 {MAIN_SCREEN_REQUIRED_ANCHORS} 项；"
        f"{fixed_label}:{'✓' if fixed_entry_matched else '×'}（必须命中），"
        f"结论={'已到达' if reached else '未到达'}"
    )
    return reached


def wait_for_main_screen(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report(
        "[主界面识别] 开始确认主界面："
        f"{len(MAIN_SCREEN_ANCHORS)} 个锚点中至少命中 "
        f"{MAIN_SCREEN_REQUIRED_ANCHORS} 个，且必须命中右侧固定入口"
    )
    for round_number in range(1, MAIN_SCREEN_INITIAL_CHECK_ROUNDS + 1):
        if main_screen_is_reached(
            tasker,
            report,
            cancel_event,
            context=f"初始第 {round_number}/{MAIN_SCREEN_INITIAL_CHECK_ROUNDS} 轮",
        ):
            report(f"[主界面识别] 已确认到达主界面（第 {round_number} 轮）")
            capture_debug_step("主界面详细识别成功")
            return

        capture_debug_step(
            f"主界面详细识别未通过（第 {round_number}/{MAIN_SCREEN_INITIAL_CHECK_ROUNDS} 轮）"
        )
        if handle_interrupting_popups(
            tasker,
            report,
            cancel_event,
            detection_timeout_ms=POPUP_POLL_TIMEOUT_MS,
        ):
            report("[主界面识别] 已清除已知中断弹窗，继续下一轮确认")
        if round_number < MAIN_SCREEN_INITIAL_CHECK_ROUNDS:
            time.sleep(MAIN_SCREEN_CHECK_INTERVAL_SECONDS)

    report("[主界面识别] 连续详细检查仍未通过，进入未知弹窗兜底")
    if try_unknown_popup_fallback(
        tasker,
        "主界面已到达",
        report,
        cancel_event,
    ):
        report("[主界面识别] 未知弹窗兜底后已确认到达主界面")
        capture_debug_step("未知弹窗兜底后主界面识别成功")
        return

    capture_debug_step("主界面详细识别最终失败")
    raise RuntimeError(
        "主界面识别失败：连续检查及未知弹窗兜底后，"
        f"仍未达到至少 {MAIN_SCREEN_REQUIRED_ANCHORS} 个导航锚点"
        "且命中右侧固定入口的要求。"
    )


def _try_unknown_popup_return_click(tasker: Tasker) -> bool:
    entry = "未知弹窗固定返回点击"
    x, y = UNKNOWN_POPUP_FALLBACK_RETURN_POSITION
    override = {
        entry: {
            "next": [],
            "pre_delay": 0,
            "post_delay": 0,
            "timeout": 1000,
            "target": [x, y],
        }
    }
    succeeded = _task_succeeded(tasker.post_task(entry, override))
    if succeeded:
        capture_debug_step(f"完成未知弹窗固定返回点击：({x}, {y})")
    return succeeded


def try_unknown_popup_fallback(
    tasker: Tasker,
    entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> bool:
    """最多点击左下返回键三轮；每轮后重新执行原任务，成功即停止点击。"""
    report(
        f"[未知弹窗兜底] {entry} 未识别成功，"
        f"开始最多 {UNKNOWN_POPUP_FALLBACK_ROUNDS} 轮固定返回点击恢复"
    )
    for round_number in range(1, UNKNOWN_POPUP_FALLBACK_ROUNDS + 1):
        ensure_not_cancelled(cancel_event)
        x, y = UNKNOWN_POPUP_FALLBACK_RETURN_POSITION
        report(
            f"[未知弹窗兜底] 第 {round_number}/{UNKNOWN_POPUP_FALLBACK_ROUNDS} 轮，"
            f"点击左下返回键固定位置 ({x}, {y})"
        )
        if not _try_unknown_popup_return_click(tasker):
            capture_debug_step(
                f"未知弹窗固定返回点击失败：第 {round_number} 轮 ({x}, {y})"
            )
            continue

        time.sleep(UNKNOWN_POPUP_CLICK_SETTLE_SECONDS)
        ensure_not_cancelled(cancel_event)
        report(f"[未知弹窗兜底] 重新判断原任务：{entry}")
        if entry == "主界面已到达":
            task_recovered = main_screen_is_reached(
                tasker,
                report,
                cancel_event,
                context=(
                    f"未知弹窗兜底第 {round_number}/{UNKNOWN_POPUP_FALLBACK_ROUNDS} 轮"
                ),
            )
        else:
            task_recovered = _task_succeeded(tasker.post_task(entry))
        if task_recovered:
            capture_debug_step(f"未知弹窗兜底后完成任务：{entry}")
            report(
                f"[未知弹窗兜底] 原任务已恢复（第 {round_number} 轮）：{entry}"
            )
            return True
        capture_debug_step(
            f"未知弹窗兜底后任务仍未完成：{entry}（第 {round_number} 轮）"
        )

    report(
        f"[未知弹窗兜底] 已完成 {UNKNOWN_POPUP_FALLBACK_ROUNDS} 轮固定返回点击，"
        f"原任务仍未识别成功：{entry}"
    )
    return False


def run_task(
    tasker: Tasker,
    entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report(f"[执行] {entry}")
    if handle_interrupting_popups(
        tasker,
        report,
        cancel_event,
        detection_timeout_ms=POPUP_POLL_TIMEOUT_MS,
    ):
        report(f"[弹窗恢复] 已在执行前清除中断弹窗：{entry}")
    for recovery in range(INTERRUPTING_POPUP_MAX_RECOVERIES + 1):
        ensure_not_cancelled(cancel_event)
        if _task_succeeded(tasker.post_task(entry)):
            ensure_not_cancelled(cancel_event)
            capture_debug_step(f"完成任务：{entry}")
            return
        capture_debug_step(f"任务未完成：{entry}（尝试 {recovery + 1}）")
        if recovery >= INTERRUPTING_POPUP_MAX_RECOVERIES:
            break
        if not handle_interrupting_popups(
            tasker,
            report,
            cancel_event,
            detection_timeout_ms=2500,
        ):
            if (
                entry not in UNKNOWN_POPUP_FALLBACK_EXCLUDED_ENTRIES
                and try_unknown_popup_fallback(tasker, entry, report, cancel_event)
            ):
                return
            break
        report(
            f"[弹窗恢复] 重新执行：{entry}"
            f"（{recovery + 1}/{INTERRUPTING_POPUP_MAX_RECOVERIES}）"
        )

    raise RuntimeError(f"{entry}失败。请检查模拟器当前页面后重试。")


def try_recognize(
    tasker: Tasker,
    entry: str,
    timeout_ms: int = POPUP_POLL_TIMEOUT_MS,
    report: Reporter = print,
    cancel_event=None,
    recover_interrupting_popup: bool = True,
) -> bool:
    for recovery in range(INTERRUPTING_POPUP_MAX_RECOVERIES + 1):
        ensure_not_cancelled(cancel_event)
        if _try_recognize_once(tasker, entry, timeout_ms):
            return True
        if (
            not recover_interrupting_popup
            or entry in INTERRUPTING_POPUP_ENTRIES
            or recovery >= INTERRUPTING_POPUP_MAX_RECOVERIES
            or not handle_interrupting_popups(tasker, report, cancel_event)
        ):
            return False
        report(f"[弹窗恢复] 重新识别：{entry}")
    return False


def try_execute(
    tasker: Tasker,
    entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> bool:
    if handle_interrupting_popups(
        tasker,
        report,
        cancel_event,
        detection_timeout_ms=POPUP_POLL_TIMEOUT_MS,
    ):
        report(f"[弹窗恢复] 已在可选动作前清除中断弹窗：{entry}")
    for recovery in range(INTERRUPTING_POPUP_MAX_RECOVERIES + 1):
        ensure_not_cancelled(cancel_event)
        if _try_execute_once(tasker, entry, POPUP_POLL_TIMEOUT_MS):
            return True
        if (
            recovery >= INTERRUPTING_POPUP_MAX_RECOVERIES
            or not handle_interrupting_popups(tasker, report, cancel_event)
        ):
            return False
        report(f"[弹窗恢复] 重新执行可选动作：{entry}")
    return False


def _transition_confirmed(
    tasker: Tasker,
    destination_entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> bool:
    deadline = time.monotonic() + TRANSITION_CONFIRM_TIMEOUT_SECONDS
    while True:
        ensure_not_cancelled(cancel_event)
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break
        timeout_ms = min(
            TRANSITION_CONFIRM_POLL_TIMEOUT_MS,
            max(1, int(remaining_seconds * 1000)),
        )
        if destination_entry == "主界面已到达":
            destination_confirmed = main_screen_is_reached(
                tasker,
                report,
                cancel_event,
                total_timeout_ms=timeout_ms,
                context="跳转确认",
            )
        else:
            destination_confirmed = try_recognize(
                tasker,
                destination_entry,
                timeout_ms=timeout_ms,
                report=report,
                cancel_event=cancel_event,
                recover_interrupting_popup=False,
            )
        if destination_confirmed:
            return True
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds > 0:
            time.sleep(min(TRANSITION_CONFIRM_POLL_INTERVAL_SECONDS, remaining_seconds))
    return False


def confirm_transition(
    tasker: Tasker,
    action_entry: str,
    destination_entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """点击跳转后，在限定时间内确认目标界面，避免在原页面继续执行。"""
    if _transition_confirmed(
        tasker,
        destination_entry,
        report,
        cancel_event,
    ):
        report(
            f"[跳转确认] {action_entry} -> {destination_entry}："
            "已确认跳转成功"
        )
        return

    capture_debug_step(f"跳转确认失败：{action_entry} -> {destination_entry}")
    if try_unknown_popup_fallback(
        tasker,
        destination_entry,
        report,
        cancel_event,
    ):
        report(
            f"[跳转确认] {action_entry} -> {destination_entry}："
            "未知弹窗兜底后已确认跳转成功"
        )
        return
    raise RuntimeError(
        f"执行“{action_entry}”后等待 {TRANSITION_CONFIRM_TIMEOUT_SECONDS:g} 秒，"
        f"仍未确认目标界面“{destination_entry}”；已停止后续操作。"
    )


def run_confirmed_transition(
    tasker: Tasker,
    action_entry: str,
    destination_entry: str,
    report: Reporter = print,
    cancel_event=None,
    action_already_performed: bool = False,
) -> None:
    total_attempts = TRANSITION_ACTION_RETRIES + 1
    for attempt in range(1, total_attempts + 1):
        if not (action_already_performed and attempt == 1):
            run_task(tasker, action_entry, report, cancel_event)
        if _transition_confirmed(
            tasker,
            destination_entry,
            report,
            cancel_event,
        ):
            report(
                f"[跳转确认] {action_entry} -> {destination_entry}："
                f"已确认跳转成功（点击 {attempt}/{total_attempts}）"
            )
            return

        capture_debug_step(
            f"跳转确认失败：{action_entry} -> {destination_entry}"
            f"（点击 {attempt}/{total_attempts}）"
        )
        if attempt < total_attempts:
            report(
                f"[跳转确认] {action_entry} -> {destination_entry}："
                f"等待 {TRANSITION_CONFIRM_TIMEOUT_SECONDS:g} 秒仍未成功，"
                f"准备重新点击（重试 {attempt}/{TRANSITION_ACTION_RETRIES}）"
            )

    if try_unknown_popup_fallback(
        tasker,
        destination_entry,
        report,
        cancel_event,
    ):
        report(
            f"[跳转确认] {action_entry} -> {destination_entry}："
            "未知弹窗兜底后已确认跳转成功"
        )
        return
    raise RuntimeError(
        f"执行“{action_entry}”后连续重试 {TRANSITION_ACTION_RETRIES} 次，"
        f"每次等待 {TRANSITION_CONFIRM_TIMEOUT_SECONDS:g} 秒，"
        f"仍未确认目标界面“{destination_entry}”；已停止后续操作。"
    )


def server_pattern(server_number: int) -> str:
    return rf"^{server_number}(?:区|服)(?:-+.*)?$"


def try_select_visible_server(tasker: Tasker, server_number: int) -> bool:
    entry = "动态选择区服"
    override = {
        entry: {
            "recognition": "OCR",
            "expected": server_pattern(server_number),
            "roi": [230, 200, 440, 850],
            "action": "Click",
            "next": [],
            "pre_delay": 0,
            "post_delay": 500,
            "timeout": 350,
        }
    }
    job = tasker.post_task(entry, override)
    job.wait()
    if not job.succeeded:
        return False
    detail = job.get()
    return detail is not None and detail.status.succeeded


def verify_selected_server(tasker: Tasker, server_number: int) -> bool:
    entry = "验证目标区服"
    override = {
        entry: {
            "recognition": "And",
            "all_of": [
                {
                    "recognition": "OCR",
                    "expected": server_pattern(server_number),
                    "roi": [130, 850, 460, 180],
                },
                {
                    "recognition": "OCR",
                    "expected": "点击开始",
                    "roi": [140, 960, 440, 180],
                },
            ],
            "box_index": 0,
            "action": "DoNothing",
            "next": [],
            "timeout": 3000,
        }
    }
    job = tasker.post_task(entry, override)
    job.wait()
    if not job.succeeded:
        return False
    detail = job.get()
    return detail is not None and detail.status.succeeded


def select_server(
    tasker: Tasker,
    controller: AdbController,
    server_number: int,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    run_confirmed_transition(
        tasker,
        "打开选服列表",
        "选服列表已打开",
        report,
        cancel_event,
    )

    if try_select_visible_server(tasker, server_number):
        report(f"[选服] 已选择 {server_number} 区")
    else:
        report("[选服] 当前位于列表顶部，开始沿列表向下查找")
        swipe_plans = (
            ((360, 850, 360, 450), SERVER_LIST_MAX_SWIPES),
            ((360, 450, 360, 850), SERVER_LIST_MAX_SWIPES * 2),
            ((360, 850, 360, 450), SERVER_LIST_MAX_SWIPES * 2),
        )
        found = False
        for (x1, y1, x2, y2), count in swipe_plans:
            for _ in range(count):
                ensure_not_cancelled(cancel_event)
                wait_job(controller.post_swipe(x1, y1, x2, y2, 420), "滑动区服列表")
                time.sleep(0.25)
                if try_select_visible_server(tasker, server_number):
                    report(f"[选服] 已选择 {server_number} 区")
                    found = True
                    break
            if found:
                break
        if not found:
            raise RuntimeError(f"在区服列表中没有找到 {server_number} 区。")

    if not verify_selected_server(tasker, server_number):
        raise RuntimeError(f"选择后未能确认当前为 {server_number} 区。")


def handle_sign_in(
    tasker: Tasker,
    controller: AdbController,
    attempts: int,
    report: Reporter = print,
) -> int | None:
    if try_execute(tasker, "签到确认按钮", report):
        report("[弹窗] 点击签到确定")
        return MONTHLY_SIGN_IN_MAX_ATTEMPTS

    if not try_recognize(tasker, "每月签到弹窗", report=report):
        return None

    if attempts < MONTHLY_SIGN_IN_MAX_ATTEMPTS:
        next_attempt = attempts + 1
        report(f"[弹窗] 点击每月签到（{next_attempt}/{MONTHLY_SIGN_IN_MAX_ATTEMPTS}）")
        wait_job(
            controller.post_click(*MONTHLY_SIGN_IN_BUTTON),
            "点击每月签到",
        )
        return next_attempt

    report("[弹窗] 签到已完成，关闭签到页")
    wait_job(controller.post_click(680, 100), "关闭签到页")
    return MONTHLY_SIGN_IN_MAX_ATTEMPTS


def handle_do_not_remind_popup(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
) -> bool:
    if try_recognize(
        tasker,
        "今日不再提示弹窗",
        report=report,
        recover_interrupting_popup=False,
    ):
        report("[弹窗] 勾选今日不再提示并关闭")
        wait_job(
            controller.post_click(*DO_NOT_REMIND_CHECKBOX),
            "勾选今日不再提示",
        )
        report("[选项检查] 勾选点击已执行：今日不再提示")
        time.sleep(POPUP_POLL_INTERVAL_SECONDS)
        wait_job(
            controller.post_click(*DO_NOT_REMIND_CLOSE),
            "关闭今日不再提示弹窗",
        )
        return True

    if handle_interrupting_popups(tasker, report):
        return True

    return False


def handle_delayed_popups(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report(
        f"[执行] 等待离线收益弹窗（最多 {OFFLINE_REWARD_WAIT_SECONDS:g} 秒）"
    )
    offline_reward_wait_started = time.monotonic()
    offline_reward_handled = False
    sign_in_attempts = 0

    while True:
        ensure_not_cancelled(cancel_event)
        if time.monotonic() - offline_reward_wait_started >= OFFLINE_REWARD_WAIT_SECONDS:
            report(
                f"[弹窗] 连续 {OFFLINE_REWARD_WAIT_SECONDS:g} 秒未发现离线收益，"
                "按本次不出现继续"
            )
            break

        if handle_do_not_remind_popup(tasker, controller, report):
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            continue

        if try_recognize(
            tasker, "离线收益弹窗", report=report, cancel_event=cancel_event
        ):
            report("[弹窗] 点击离线收益确定")
            wait_job(controller.post_click(360, 915), "点击离线收益确定")
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            offline_reward_handled = True
            break

        sign_in_result = handle_sign_in(tasker, controller, sign_in_attempts, report)
        if sign_in_result is not None:
            sign_in_attempts = sign_in_result
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            continue

        if try_recognize(
            tasker, "幸运赠礼弹窗", report=report, cancel_event=cancel_event
        ):
            report("[弹窗] 点击幸运赠礼中心（继续等待离线收益）")
            wait_job(controller.post_click(360, 640), "点击幸运赠礼中心")

        time.sleep(POPUP_POLL_INTERVAL_SECONDS)

    if offline_reward_handled:
        report("[执行] 离线收益已处理，连续 5 秒无弹窗后完成")
    else:
        report("[执行] 本次未出现离线收益，继续确认连续 5 秒无弹窗")
    quiet_since = time.monotonic()

    while time.monotonic() - quiet_since < POPUP_QUIET_SECONDS:
        ensure_not_cancelled(cancel_event)
        if handle_do_not_remind_popup(tasker, controller, report):
            quiet_since = time.monotonic()
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            continue

        if try_recognize(
            tasker, "离线收益弹窗", report=report, cancel_event=cancel_event
        ):
            report("[弹窗] 点击离线收益确定")
            wait_job(controller.post_click(360, 915), "点击离线收益确定")
            quiet_since = time.monotonic()
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            continue

        sign_in_result = handle_sign_in(tasker, controller, sign_in_attempts, report)
        if sign_in_result is not None:
            sign_in_attempts = sign_in_result
            quiet_since = time.monotonic()
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            continue

        if try_recognize(
            tasker, "幸运赠礼弹窗", report=report, cancel_event=cancel_event
        ):
            report("[弹窗] 点击幸运赠礼中心")
            wait_job(controller.post_click(360, 640), "点击幸运赠礼中心")
            quiet_since = time.monotonic()
            time.sleep(POPUP_POLL_INTERVAL_SECONDS)
            continue

        time.sleep(POPUP_POLL_INTERVAL_SECONDS)


def drain_visible_daily_rewards(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> int:
    claimed = 0
    for _ in range(30):
        ensure_not_cancelled(cancel_event)
        if try_execute(tasker, "日常奖励确定", report, cancel_event):
            report("[日常] 点击奖励确定")
            time.sleep(0.2)
            continue
        if not try_execute(tasker, "日常领取按钮", report, cancel_event):
            break
        claimed += 1
        report(f"[日常] 已领取 {claimed} 项当前可见奖励")
        time.sleep(0.25)
    return claimed


def capture_screen(controller: AdbController) -> np.ndarray:
    job = controller.post_screencap()
    job.wait()
    if not job.succeeded:
        raise RuntimeError("日常列表截图失败。")
    return job.get()


def daily_list_change(before: np.ndarray, after: np.ndarray) -> float:
    before_roi = before[250:1120, 20:700].astype(np.int16)
    after_roi = after[250:1120, 20:700].astype(np.int16)
    if before_roi.shape != after_roi.shape or before_roi.size == 0:
        return float("inf")
    return float(np.abs(before_roi - after_roi).mean())


def claim_all_daily_rewards(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report("[执行] 扫描并领取全部日常奖励")
    total_claimed = drain_visible_daily_rewards(tasker, report, cancel_event)
    unchanged_swipes = 0

    for _ in range(DAILY_LIST_MAX_SWIPES):
        ensure_not_cancelled(cancel_event)
        before = capture_screen(controller)
        wait_job(controller.post_swipe(360, 980, 360, 430, 450), "滑动日常列表")
        time.sleep(0.35)
        after = capture_screen(controller)

        if daily_list_change(before, after) < 0.8:
            unchanged_swipes += 1
        else:
            unchanged_swipes = 0

        total_claimed += drain_visible_daily_rewards(tasker, report, cancel_event)
        if unchanged_swipes >= 2:
            break

    total_claimed += drain_visible_daily_rewards(tasker, report, cancel_event)
    report(f"[日常] 扫描完成，本次共领取 {total_claimed} 项奖励")


def rewind_daily_list(
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """将日常列表尽量回到顶部，避免上一次扫描停留在中段。"""
    for _ in range(DAILY_TASK_REWIND_SWIPES):
        ensure_not_cancelled(cancel_event)
        wait_job(controller.post_swipe(360, 430, 360, 980, 260), "回到日常列表顶部")
        time.sleep(0.12)


def _normalize_daily_ocr_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _daily_task_label_matches(ocr_text: str, task_label: str) -> bool:
    """兼容任务标题因 UI 换行而被 OCR 拆成多个文本框。"""
    normalized_text = _normalize_daily_ocr_text(ocr_text)
    candidates = (task_label, *DAILY_TASK_LABEL_ALIASES.get(task_label, ()))
    return any(
        _normalize_daily_ocr_text(candidate) in normalized_text
        for candidate in candidates
    )


def collect_daily_viewport_ocr(tasker: Tasker) -> list[DailyOcrText]:
    """读取当前日常视口的全部 OCR 文本及位置，供同行状态关联。"""
    entry = "日常列表OCR盘点"
    override = {
        entry: {
            "recognition": "OCR",
            "expected": ".+",
            "roi": [20, 180, 680, 1000],
            "action": "DoNothing",
            "next": [],
            "pre_delay": 0,
            "post_delay": 0,
            "timeout": 3000,
        }
    }
    job = tasker.post_task(entry, override)
    job.wait()
    if not job.succeeded:
        return []
    detail = job.get()
    if detail is None:
        return []

    texts: list[DailyOcrText] = []
    seen: set[tuple[str, tuple[int, int, int, int]]] = set()
    for node in detail.nodes:
        recognition = node.recognition
        if recognition is None:
            continue
        for result in recognition.all_results:
            text = getattr(result, "text", None)
            box = getattr(result, "box", None)
            if not text or box is None:
                continue
            normalized_box = tuple(int(value) for value in box)
            item = (_normalize_daily_ocr_text(str(text)), normalized_box)
            if not item[0] or item in seen:
                continue
            seen.add(item)
            texts.append(DailyOcrText(*item))
    return texts


def classify_daily_viewport(
    ocr_texts: list[DailyOcrText],
    specs: tuple[DailyTaskSpec, ...] = DAILY_TASK_SPECS,
) -> dict[str, str]:
    """按纵向中心点把任务标题与同行按钮状态关联。"""
    state_boxes: list[tuple[str, int]] = []
    for item in ocr_texts:
        x, y, width, height = item.box
        if x + width / 2 < 480:
            continue
        if "已领取" in item.text:
            state = DAILY_STATE_CLAIMED
        elif "领取" in item.text:
            state = DAILY_STATE_CLAIMABLE
        elif "前往" in item.text:
            state = DAILY_STATE_TODO
        else:
            continue
        state_boxes.append((state, y + height // 2))

    found: dict[str, str] = {}
    for spec in specs:
        title_boxes = [
            item
            for item in ocr_texts
            if _daily_task_label_matches(item.text, spec.label)
        ]
        best_match: tuple[int, str] | None = None
        for title in title_boxes:
            _, y, _, height = title.box
            title_center_y = y + height // 2
            for state, state_center_y in state_boxes:
                distance = abs(title_center_y - state_center_y)
                if distance > DAILY_TASK_ROW_Y_TOLERANCE:
                    continue
                if best_match is None or distance < best_match[0]:
                    best_match = (distance, state)
        if best_match is not None:
            found[spec.key] = best_match[1]
    return found


def daily_forward_button_center(
    ocr_texts: list[DailyOcrText],
    task_label: str,
) -> tuple[int, int] | None:
    """返回与目标任务标题纵向最接近的同行“前往”文本框中心。"""
    titles = [
        item for item in ocr_texts if _daily_task_label_matches(item.text, task_label)
    ]
    forwards = [
        item
        for item in ocr_texts
        if "前往" in item.text and item.box[0] + item.box[2] / 2 >= 480
    ]
    best_match: tuple[float, DailyOcrText] | None = None
    for title in titles:
        _, title_y, _, title_height = title.box
        title_center_y = title_y + title_height / 2
        for forward in forwards:
            _, forward_y, _, forward_height = forward.box
            forward_center_y = forward_y + forward_height / 2
            distance = abs(title_center_y - forward_center_y)
            if distance > DAILY_TASK_ROW_Y_TOLERANCE:
                continue
            if best_match is None or distance < best_match[0]:
                best_match = (distance, forward)

    if best_match is None:
        return None
    x, y, width, height = best_match[1].box
    return x + width // 2, y + height // 2


def daily_task_label_for_entry(entry: str) -> str | None:
    """根据日常“前往”节点名取得对应任务标题。"""
    for spec in DAILY_TASK_SPECS:
        if spec.forward_entry == entry:
            return spec.label
    return None


def inventory_daily_tasks(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> dict[str, str]:
    """首次进入日常后从顶部到底部盘点任务，并生成只读执行计划。"""
    report("[日常盘点] 开始首次全量盘点：先回到列表顶部，再滚动至底部")
    rewind_daily_list(controller, report, cancel_event)
    states: dict[str, str] = {}
    state_priority = {
        DAILY_STATE_TODO: 1,
        DAILY_STATE_CLAIMABLE: 2,
        DAILY_STATE_CLAIMED: 3,
    }
    unchanged_swipes = 0

    for viewport in range(1, DAILY_INVENTORY_MAX_SWIPES + 1):
        ensure_not_cancelled(cancel_event)
        ocr_texts = collect_daily_viewport_ocr(tasker)
        relevant = [
            item
            for item in ocr_texts
            if any(
                _daily_task_label_matches(item.text, spec.label)
                for spec in DAILY_TASK_SPECS
            )
            or "前往" in item.text
            or "领取" in item.text
        ]
        report(
            f"[日常盘点] 视口 {viewport} OCR："
            + (
                "；".join(f"{item.text}@{item.box}" for item in relevant)
                if relevant
                else "未识别到目标任务或状态文字"
            )
        )
        visible_states = classify_daily_viewport(ocr_texts)
        for spec in DAILY_TASK_SPECS:
            state = visible_states.get(spec.key)
            if state is None:
                continue
            previous = states.get(spec.key)
            if previous is None or state_priority[state] > state_priority[previous]:
                states[spec.key] = state
                report(
                    f"[日常盘点] 任务状态：{spec.label}={state}（视口 {viewport}）"
                )
        capture_debug_step(f"日常任务盘点视口 {viewport}")

        before = capture_screen(controller)
        wait_job(controller.post_swipe(360, 980, 360, 430, 420), "盘点日常任务")
        time.sleep(0.28)
        after = capture_screen(controller)
        if daily_list_change(before, after) < 0.8:
            unchanged_swipes += 1
            report(
                f"[日常盘点] 视口 {viewport} 下滑后画面基本未变化"
                f"（连续 {unchanged_swipes}/2）"
            )
        else:
            unchanged_swipes = 0
        if unchanged_swipes >= 2:
            report(f"[日常盘点] 已确认到达列表底部（视口 {viewport}）")
            break
    else:
        report(
            f"[日常盘点] 已达到最大 {DAILY_INVENTORY_MAX_SWIPES} 次扫描，"
            "按当前盘点结果继续"
        )

    report("[日常盘点] 从底部回到顶部，准备按计划执行")
    rewind_daily_list(controller, report, cancel_event)
    plan: dict[str, str] = {}
    for spec in DAILY_TASK_SPECS:
        state = states.get(spec.key, DAILY_STATE_UNKNOWN)
        plan[spec.key] = state
        decision = "执行" if state == DAILY_STATE_TODO else "跳过"
        report(
            f"[日常计划] {spec.label}：状态={state}，决策={decision}"
        )
    capture_debug_step("日常任务首次盘点完成")
    return plan


def seek_daily_task(
    tasker: Tasker,
    controller: AdbController,
    entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> bool:
    """在可滚动日常列表中寻找任务行；找到后保持该行可见。"""
    report(f"[日常扫描] 开始查找任务入口：{entry}")
    rewind_daily_list(controller, report, cancel_event)
    unchanged_swipes = 0
    for index in range(1, DAILY_TASK_SEEK_SWIPES + 1):
        ensure_not_cancelled(cancel_event)
        if try_recognize(
            tasker, entry, report=report, cancel_event=cancel_event
        ):
            report(f"[日常扫描] 已找到任务入口：{entry}（视口 {index}）")
            return True
        report(
            f"[日常扫描] 未找到任务入口：{entry}；"
            f"继续向下扫描（{index}/{DAILY_TASK_SEEK_SWIPES}）"
        )
        before = capture_screen(controller)
        wait_job(controller.post_swipe(360, 980, 360, 430, 420), "查找日常任务")
        time.sleep(0.28)
        after = capture_screen(controller)
        if daily_list_change(before, after) < 0.8:
            unchanged_swipes += 1
        else:
            unchanged_swipes = 0
        if unchanged_swipes >= 2:
            report(f"[日常扫描] 列表已到底，停止查找：{entry}")
            return False
    report(f"[日常扫描] 扫描结束，仍未找到任务入口：{entry}")
    return False


def run_daily_forward(
    tasker: Tasker,
    controller: AdbController,
    entry: str,
    destination_entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    if not seek_daily_task(tasker, controller, entry, report, cancel_event):
        raise RuntimeError(f"日常列表中未找到任务入口：{entry}")

    total_attempts = DAILY_ACTION_RETRIES + 1
    task_label = daily_task_label_for_entry(entry)
    for attempt in range(1, total_attempts + 1):
        ensure_not_cancelled(cancel_event)
        forward_center = None
        if task_label is not None:
            forward_center = daily_forward_button_center(
                collect_daily_viewport_ocr(tasker),
                task_label,
            )
        if forward_center is not None:
            report(
                f"[日常前往] 已定位同行“前往”文本框中心 {forward_center}；"
                f"点击 {attempt}/{total_attempts}"
            )
            wait_job(
                controller.post_click(*forward_center),
                f"点击{task_label}同行前往中心",
            )
            time.sleep(DAILY_FORWARD_POST_CLICK_SECONDS)
            capture_debug_step(f"完成：点击{task_label}同行前往中心")
        else:
            report(
                f"[日常前往] 本轮未取得{task_label or entry}同行“前往”中心；"
                "回退到原相对偏移点击"
            )
            run_task(tasker, entry, report, cancel_event)
        stayed_on_daily = False
        for transition_check in range(1, DAILY_TRANSITION_CHECKS + 1):
            time.sleep(0.5)
            if try_recognize(
                tasker,
                destination_entry,
                timeout_ms=DAILY_DESTINATION_TIMEOUT_MS,
                report=report,
                cancel_event=cancel_event,
                recover_interrupting_popup=False,
            ):
                report(
                    f"[日常前往] 已确认目标页面：{destination_entry}"
                    f"（点击 {attempt}/{total_attempts}，"
                    f"确认 {transition_check}/{DAILY_TRANSITION_CHECKS}）"
                )
                return

            stayed_on_daily = try_recognize(
                tasker,
                "日常界面已打开",
                timeout_ms=DAILY_SOURCE_PAGE_TIMEOUT_MS,
                report=report,
                cancel_event=cancel_event,
                recover_interrupting_popup=False,
            )
            if stayed_on_daily:
                if transition_check < DAILY_TRANSITION_CHECKS:
                    report(
                        "[日常前往] 点击后仍在日常页，等待页面响应"
                        f"（确认 {transition_check}/{DAILY_TRANSITION_CHECKS}）"
                    )
                    continue
                break

            if handle_interrupting_popups(tasker, report, cancel_event):
                report("[日常前往] 已清除中断弹窗，继续确认跳转结果")
                continue

            if transition_check < DAILY_TRANSITION_CHECKS:
                report(
                    "[日常前往] 暂未确认日常页或目标页，继续等待页面稳定"
                    f"（确认 {transition_check}/{DAILY_TRANSITION_CHECKS}）"
                )

        if stayed_on_daily and attempt < total_attempts:
            report(
                "[日常前往] 已明确仍停留在日常页，前往点击未生效；"
                f"准备重复点击（{attempt}/{total_attempts}）"
            )
            continue
        if not stayed_on_daily:
            raise RuntimeError(
                f"点击日常任务“{entry}”后，既未确认原日常页，"
                f"也未确认目标页面“{destination_entry}”。"
            )

    raise RuntimeError(
        f"日常任务“{entry}”连续点击 {total_attempts} 次后仍未跳转。"
    )


def click_bottom_commercial_street(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    if try_recognize(
        tasker,
        "点击商业街返回主页",
        timeout_ms=1500,
        report=report,
        cancel_event=cancel_event,
    ):
        action_entry = "点击商业街返回主页"
        report("[返回主页] OCR 已识别“商业街”，点击文字框中心")
    else:
        action_entry = "点击商业街返回主页固定位置"
        report("[返回主页] OCR 未识别“商业街”，使用固定坐标 (200, 1215) 兜底")
    run_confirmed_transition(
        tasker,
        action_entry,
        "主界面已到达",
        report,
        cancel_event,
    )


def seek_department_store_shop(
    tasker: Tasker,
    controller: AdbController,
    entry: str,
    shop_name: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """在可上下滚动的百货楼层中寻找并点击指定店铺。"""
    report(f"[百货扫描] 开始查找店铺：{shop_name}")

    # “前往”可能已经把目标店铺带入当前视口，先检查一次，避免无谓滚动。
    if try_recognize(
        tasker, entry, report=report, cancel_event=cancel_event
    ):
        report(f"[百货扫描] 当前视口已找到：{shop_name}")
        run_task(tasker, entry, report, cancel_event)
        return

    # 先回到百货楼层左上角，再以蛇形路径扫描二维场景，避免只做纵向
    # 滑动时漏掉位于当前画面左侧或右侧的店铺。
    report("[百货扫描] 当前视口未找到，先回到楼层左上角")
    for index in range(1, DEPARTMENT_STORE_VERTICAL_REWIND_SWIPES + 1):
        ensure_not_cancelled(cancel_event)
        wait_job(
            controller.post_swipe(360, 430, 360, 980, 320),
            "回到百货楼层顶部",
        )
        report(
            "[百货扫描] 向上复位楼层"
            f"（{index}/{DEPARTMENT_STORE_VERTICAL_REWIND_SWIPES}）"
        )
        time.sleep(0.18)

    for index in range(1, DEPARTMENT_STORE_HORIZONTAL_REWIND_SWIPES + 1):
        ensure_not_cancelled(cancel_event)
        wait_job(
            controller.post_swipe(200, 700, 520, 700, 320),
            "回到百货楼层左侧",
        )
        report(
            "[百货扫描] 向左复位楼层"
            f"（{index}/{DEPARTMENT_STORE_HORIZONTAL_REWIND_SWIPES}）"
        )
        time.sleep(0.18)

    scan_left_to_right = True
    for row in range(1, DEPARTMENT_STORE_VERTICAL_VIEWPORTS + 1):
        for column in range(1, DEPARTMENT_STORE_HORIZONTAL_VIEWPORTS + 1):
            ensure_not_cancelled(cancel_event)
            if try_recognize(
                tasker, entry, report=report, cancel_event=cancel_event
            ):
                report(
                    f"[百货扫描] 已找到店铺：{shop_name}"
                    f"（纵向 {row}，横向 {column}）"
                )
                run_task(tasker, entry, report, cancel_event)
                return

            if column == DEPARTMENT_STORE_HORIZONTAL_VIEWPORTS:
                continue
            direction = "向右" if scan_left_to_right else "向左"
            report(
                f"[百货扫描] 当前视口未找到：{shop_name}；"
                f"{direction}扫描（纵向 {row}/{DEPARTMENT_STORE_VERTICAL_VIEWPORTS}，"
                f"横向 {column}/{DEPARTMENT_STORE_HORIZONTAL_VIEWPORTS}）"
            )
            if scan_left_to_right:
                swipe = (520, 700, 200, 700)
            else:
                swipe = (200, 700, 520, 700)
            wait_job(controller.post_swipe(*swipe, 360), "横向查找百货店铺")
            time.sleep(0.25)

        if row == DEPARTMENT_STORE_VERTICAL_VIEWPORTS:
            break
        report(
            f"[百货扫描] 横向扫描完成，继续向下"
            f"（{row}/{DEPARTMENT_STORE_VERTICAL_VIEWPORTS}）"
        )
        wait_job(
            controller.post_swipe(360, 980, 360, 420, 420),
            "纵向查找百货店铺",
        )
        time.sleep(0.3)
        scan_left_to_right = not scan_left_to_right

    raise RuntimeError(
        f"已扫描百货楼层，仍未找到店铺：{shop_name}。"
        "请保持百货页可见后重试。"
    )


def enter_fresh_supermarket_from_daily(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """从生鲜进货日常进入百货楼层，再打开被定位的生鲜超市。"""
    report("[生鲜入口] 点击日常“前往”，目标应为百货楼层而非生鲜超市内部")
    run_daily_forward(
        tasker,
        controller,
        "生鲜超市进货任务前往",
        "百货界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "百货界面已打开", report, cancel_event)
    report("[生鲜入口] 已确认进入百货楼层，开始识别“生鲜超市”入口文字")

    if try_recognize(
        tasker,
        "点击生鲜超市入口",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[生鲜入口] OCR 已识别“生鲜超市”，按文字位置点击")
        action_entry = "点击生鲜超市入口"
    else:
        report(
            "[生鲜入口] OCR 未识别“生鲜超市”；可能被引导手指遮挡，"
            "改用日常“前往”定位后的入口区域点击"
        )
        capture_debug_step("生鲜超市入口文字未识别，使用引导页固定位置")
        action_entry = "点击日常定位的生鲜超市入口"

    run_confirmed_transition(
        tasker,
        action_entry,
        "生鲜超市界面已打开",
        report,
        cancel_event,
    )
    report(f"[生鲜入口] 已确认进入生鲜超市内部；入口方式={action_entry}")


def enter_lucky_draw_from_daily(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """从幸运扭蛋日常进入百货楼层，再打开被定位的幸运扭蛋。"""
    report("[扭蛋入口] 点击日常“前往”，目标应为百货楼层而非幸运扭蛋内部")
    run_daily_forward(
        tasker,
        controller,
        "幸运扭蛋任务前往",
        "百货界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "百货界面已打开", report, cancel_event)
    report("[扭蛋入口] 已确认进入百货楼层，开始识别“幸运扭蛋”入口文字")

    if try_recognize(
        tasker,
        "点击幸运扭蛋",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[扭蛋入口] OCR 已识别“幸运扭蛋”，按文字位置点击")
        action_entry = "点击幸运扭蛋"
    else:
        report(
            "[扭蛋入口] OCR 未识别“幸运扭蛋”；"
            "改用日常“前往”定位后的右上入口区域点击"
        )
        capture_debug_step("幸运扭蛋入口文字未识别，使用日常定位固定位置")
        action_entry = "点击日常定位的幸运扭蛋入口"

    run_confirmed_transition(
        tasker,
        action_entry,
        "幸运扭蛋界面已打开",
        report,
        cancel_event,
    )
    report(f"[扭蛋入口] 已确认进入幸运扭蛋内部；入口方式={action_entry}")


def enter_artist_from_daily(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """从艺人宣传日常进入影视城外层，再打开被定位的艺人入口。"""
    report("[艺人入口] 点击日常“前往”，先确认进入影视城外层")
    run_daily_forward(
        tasker,
        controller,
        "艺人宣传任务前往",
        "影视城界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "影视城界面已打开", report, cancel_event)
    report("[艺人入口] 已确认进入影视城外层，开始识别“艺人”入口文字")

    if try_recognize(
        tasker,
        "点击艺人",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[艺人入口] OCR 已识别“艺人”，按文字位置点击")
        action_entry = "点击艺人"
    else:
        report(
            "[艺人入口] OCR 未识别“艺人”；可能被引导手指遮挡，"
            "改用日常“前往”定位后的艺人标签左侧点击"
        )
        capture_debug_step("艺人入口文字未识别，使用日常定位固定位置")
        action_entry = "点击日常定位的艺人入口"

    run_confirmed_transition(
        tasker,
        action_entry,
        "艺人界面已打开",
        report,
        cancel_event,
    )
    report(f"[艺人入口] 已确认进入艺人内部；入口方式={action_entry}")


def return_to_daily(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    run_confirmed_transition(
        tasker,
        "点击日常",
        "日常界面已打开",
        report,
        cancel_event,
    )


def checkbox_is_selected(
    tasker: Tasker,
    entry: str,
    report: Reporter = print,
    cancel_event=None,
    timeout_ms: int = POPUP_POLL_TIMEOUT_MS,
) -> bool:
    return try_recognize(
        tasker,
        entry,
        timeout_ms=timeout_ms,
        report=report,
        cancel_event=cancel_event,
    )


def find_recognition_box(
    tasker: Tasker,
    entry: str,
    timeout_ms: int = 1500,
) -> tuple[int, int, int, int] | None:
    """执行一次只识别不点击的节点，并返回首个识别框。"""
    override = {
        entry: {
            "action": "DoNothing",
            "next": [],
            "pre_delay": 0,
            "post_delay": 0,
            "timeout": timeout_ms,
        }
    }
    job = tasker.post_task(entry, override)
    job.wait()
    if not job.succeeded:
        return None
    detail = job.get()
    if detail is None:
        return None
    for node in detail.nodes:
        recognition = node.recognition
        if recognition is None:
            continue
        for result in recognition.all_results:
            box = getattr(result, "box", None)
            if box is not None:
                return tuple(int(value) for value in box)
    return None


def factory_auto_research_selection(
    image: np.ndarray,
    text_box: tuple[int, int, int, int],
) -> tuple[bool, int, tuple[int, int]]:
    """根据“自动研发”左侧圆框中央是否存在绿色勾判断选中状态。"""
    x, y, _width, height = text_box
    center = (x - FACTORY_AUTO_RESEARCH_CHECK_OFFSET_X, y + height // 2)
    selected, green_count = factory_auto_research_selection_at_center(image, center)
    return selected, green_count, center


def factory_auto_research_selection_at_center(
    image: np.ndarray,
    center: tuple[int, int],
) -> tuple[bool, int]:
    """检测指定勾选框中心的小范围内是否存在绿色勾。"""
    center_x, center_y = center
    radius = FACTORY_AUTO_RESEARCH_INNER_RADIUS
    image_height, image_width = image.shape[:2]
    left = max(0, center_x - radius)
    right = min(image_width, center_x + radius + 1)
    top = max(0, center_y - radius)
    bottom = min(image_height, center_y + radius + 1)
    roi = image[top:bottom, left:right]
    if roi.size == 0 or roi.ndim < 3 or roi.shape[2] < 3:
        return False, 0

    channel_0 = roi[:, :, 0].astype(np.int16)
    green = roi[:, :, 1].astype(np.int16)
    channel_2 = roi[:, :, 2].astype(np.int16)
    green_pixels = (
        (green >= 130)
        & (green >= channel_0 + 20)
        & (green >= channel_2 + 20)
    )
    green_count = int(green_pixels.sum())
    return green_count >= FACTORY_AUTO_RESEARCH_GREEN_COUNT, green_count


def detect_factory_auto_research_selection(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
) -> tuple[bool, int, tuple[int, int], str]:
    """固定位置优先检测绿色勾，未命中时用文字定位结果兜底。"""
    image = capture_screen(controller)
    fixed_selected, fixed_count = factory_auto_research_selection_at_center(
        image,
        FACTORY_AUTO_RESEARCH_FIXED_CENTER,
    )
    report(
        "[关卡工厂选项] 固定勾选框检测="
        f"{'已选中' if fixed_selected else '未检测到绿色勾'}；"
        f"绿色中心像素={fixed_count}；"
        f"勾选框中心={FACTORY_AUTO_RESEARCH_FIXED_CENTER}"
    )
    if fixed_selected:
        return (
            True,
            fixed_count,
            FACTORY_AUTO_RESEARCH_FIXED_CENTER,
            "固定坐标",
        )

    text_box = find_recognition_box(tasker, "自动研发文字")
    if text_box is None:
        report(
            "[关卡工厂选项] OCR 兜底未定位“自动研发”；"
            "按固定勾选框未检测到绿色勾处理"
        )
        return (
            False,
            fixed_count,
            FACTORY_AUTO_RESEARCH_FIXED_CENTER,
            "固定坐标（OCR 未命中）",
        )

    selected, green_count, center = factory_auto_research_selection(image, text_box)
    report(
        "[关卡工厂选项] OCR 兜底勾选框检测="
        f"{'已选中' if selected else '未选中'}；"
        f"绿色中心像素={green_count}；勾选框中心={center}；"
        f"文字框={text_box}"
    )
    return selected, green_count, center, "OCR 文字定位"


def ensure_factory_auto_research_unselected(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """仅在绿色勾明确存在时取消自动研发，并复核为未选中。"""
    ensure_not_cancelled(cancel_event)
    selected, green_count, center, source = detect_factory_auto_research_selection(
        tasker,
        controller,
        report,
    )
    report(
        "[关卡工厂选项] 自动研发初始状态="
        f"{'已选中' if selected else '未选中'}；"
        f"绿色中心像素={green_count}；勾选框中心={center}；来源={source}"
    )
    if not selected:
        capture_debug_step("自动研发已确认未选中")
        return

    report(f"[关卡工厂选项] 点击勾选框 {center}，取消自动研发")
    wait_job(controller.post_click(*center), "取消勾选自动研发")
    time.sleep(CHECKBOX_CONFIRM_INTERVAL_SECONDS)
    ensure_not_cancelled(cancel_event)

    still_selected, refreshed_count, refreshed_center, refreshed_source = (
        detect_factory_auto_research_selection(tasker, controller, report)
    )
    report(
        "[关卡工厂选项] 取消后复核状态="
        f"{'仍为已选中' if still_selected else '已取消'}；"
        f"绿色中心像素={refreshed_count}；"
        f"勾选框中心={refreshed_center}；来源={refreshed_source}"
    )
    if still_selected:
        capture_debug_step("自动研发取消后仍为选中")
        raise RuntimeError("点击后仍检测到“自动研发”绿色勾，已停止研发操作。")
    capture_debug_step("自动研发已取消并复核")


def ensure_checkbox_selected(
    tasker: Tasker,
    checked_entry: str,
    click_entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report(
        f"[选项检查] 开始检查：{checked_entry}；"
        f"未选中时将执行：{click_entry}"
    )
    initially_selected = checkbox_is_selected(
        tasker,
        checked_entry,
        report,
        cancel_event,
    )
    if initially_selected:
        report(f"[选项检查] 初始状态=已选中，无需点击：{checked_entry}")
        capture_debug_step(f"选项初始已选中：{checked_entry}")
        return

    report(f"[选项检查] 初始状态=未选中，准备点击：{click_entry}")
    capture_debug_step(f"选项初始未选中：{checked_entry}")
    run_task(tasker, click_entry, report, cancel_event)
    report(
        f"[选项检查] 勾选点击已执行：{click_entry}；"
        f"开始复核：{checked_entry}"
    )
    deadline = time.monotonic() + CHECKBOX_CONFIRM_TIMEOUT_SECONDS
    confirm_attempt = 0
    while True:
        ensure_not_cancelled(cancel_event)
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break
        confirm_attempt += 1
        selected_after_click = checkbox_is_selected(
            tasker,
            checked_entry,
            report,
            cancel_event,
            timeout_ms=min(
                POPUP_POLL_TIMEOUT_MS,
                max(1, int(remaining_seconds * 1000)),
            ),
        )
        report(
            f"[选项检查] 点击后复核 {confirm_attempt}："
            f"状态={'已选中' if selected_after_click else '未选中'}；"
            f"目标={checked_entry}"
        )
        if selected_after_click:
            report(f"[选项检查] 最终确认=已选中：{checked_entry}")
            capture_debug_step(f"选项点击后已确认选中：{checked_entry}")
            return
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds > 0:
            time.sleep(min(CHECKBOX_CONFIRM_INTERVAL_SECONDS, remaining_seconds))

    report(
        f"[选项检查] 最终确认=失败：{checked_entry}；"
        f"共复核 {confirm_attempt} 次，停止后续消费动作"
    )
    capture_debug_step(f"选项点击后仍未选中：{checked_entry}")
    raise RuntimeError(
        f"等待 {CHECKBOX_CONFIRM_TIMEOUT_SECONDS:g} 秒后仍未能确认绿色勾，"
        f"已停止后续消费动作：{checked_entry}"
    )


def dismiss_result_overlay(
    tasker: Tasker,
    controller: AdbController,
    result_entry: str,
    report: Reporter = print,
    cancel_event=None,
    wait_timeout_seconds: float = TRANSITION_CONFIRM_TIMEOUT_SECONDS,
) -> None:
    started_at = time.monotonic()
    deadline = started_at + wait_timeout_seconds
    poll_count = 0
    report(
        f"[结果弹层] 开始等待：{result_entry}；"
        f"最长等待 {wait_timeout_seconds:g} 秒"
    )
    while True:
        ensure_not_cancelled(cancel_event)
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            capture_debug_step(f"等待结果弹层超时：{result_entry}")
            raise RuntimeError(
                f"等待 {wait_timeout_seconds:g} 秒后仍未识别到结果弹层："
                f"{result_entry}"
            )
        poll_count += 1
        if try_recognize(
            tasker,
            result_entry,
            timeout_ms=min(
                TRANSITION_CONFIRM_POLL_TIMEOUT_MS,
                max(1, int(remaining_seconds * 1000)),
            ),
            report=report,
            cancel_event=cancel_event,
            recover_interrupting_popup=False,
        ):
            elapsed_seconds = time.monotonic() - started_at
            report(
                f"[结果弹层] 已识别：{result_entry}；"
                f"轮询 {poll_count} 次，耗时 {elapsed_seconds:.1f} 秒"
            )
            capture_debug_step(f"已识别结果弹层：{result_entry}")
            break
        elapsed_seconds = time.monotonic() - started_at
        report(
            f"[结果弹层] 第 {poll_count} 次尚未识别：{result_entry}；"
            f"已等待 {elapsed_seconds:.1f} 秒，剩余最多 "
            f"{max(0.0, deadline - time.monotonic()):.1f} 秒"
        )
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds > 0:
            time.sleep(min(TRANSITION_CONFIRM_POLL_INTERVAL_SECONDS, remaining_seconds))
    ensure_not_cancelled(cancel_event)
    # 结果层明确提示“点击任意处关闭”；使用左上安全空白区，避开底部按钮。
    report(f"[结果弹层] 点击安全位置关闭：{result_entry}")
    wait_job(controller.post_click(80, 220), "关闭结果弹层")
    time.sleep(0.35)
    if try_recognize(
        tasker,
        result_entry,
        report=report,
        cancel_event=cancel_event,
        recover_interrupting_popup=False,
    ):
        capture_debug_step(f"结果弹层关闭失败：{result_entry}")
        raise RuntimeError(f"结果弹层未关闭：{result_entry}")
    report(f"[结果弹层] 已确认关闭：{result_entry}")
    capture_debug_step(f"结果弹层已关闭：{result_entry}")


def claim_daily_100_reward(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """领取最右侧 100 礼包；已领取时识别仍在日常页并直接跳过。"""
    run_task(tasker, "领取日常100活跃礼包", report, cancel_event)
    deadline = time.monotonic() + DAILY_100_REWARD_RESULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        ensure_not_cancelled(cancel_event)
        if try_recognize(
            tasker,
            "日常100活跃礼包结果弹层",
            timeout_ms=TRANSITION_CONFIRM_POLL_TIMEOUT_MS,
            report=report,
            cancel_event=cancel_event,
            recover_interrupting_popup=False,
        ):
            dismiss_result_overlay(
                tasker,
                controller,
                "日常100活跃礼包结果弹层",
                report,
                cancel_event,
            )
            report("[日常] 100 活跃礼包已领取并关闭结果层")
            return
        if try_recognize(
            tasker,
            "日常100活跃礼包重复领取弹窗",
            timeout_ms=TRANSITION_CONFIRM_POLL_TIMEOUT_MS,
            report=report,
            cancel_event=cancel_event,
            recover_interrupting_popup=False,
        ):
            run_task(
                tasker,
                "关闭日常100活跃礼包重复领取弹窗",
                report,
                cancel_event,
            )
            report("[日常] 检测到礼包已领取提示，已关闭提示；礼包已是领取状态，跳过重复领取")
            report("[账号队列] 当前账号收尾完成前不会继续下一个账号")
            return
        time.sleep(TRANSITION_CONFIRM_POLL_INTERVAL_SECONDS)

    if try_recognize(
        tasker,
        "日常界面已打开",
        timeout_ms=POPUP_POLL_TIMEOUT_MS,
        report=report,
        cancel_event=cancel_event,
        recover_interrupting_popup=False,
    ):
        report("[日常] 100 活跃礼包已是领取状态，跳过重复领取")
        report("[账号队列] 当前账号收尾完成前不会继续下一个账号")
        return
    raise RuntimeError("点击 100 活跃礼包后，既未出现结果层，也未确认仍在日常页。")


def complete_commercial_daily_group(
    tasker: Tasker,
    controller: AdbController,
    daily_plan: dict[str, str],
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """仅执行盘点为待完成的百货任务，并复用已进入的百货页面。"""
    pending = {
        key
        for key in ("store_upgrade", "fresh_stock", "lucky_draw", "club_exchange")
        if daily_plan.get(key) == DAILY_STATE_TODO
    }
    if not pending:
        report("[日常计划] 百货组没有待完成任务，整组跳过")
        return

    report(f"[日常计划] 百货组待完成：{', '.join(sorted(pending))}")
    at_department_store = False

    if "store_upgrade" in pending:
        run_daily_forward(
            tasker,
            controller,
            "任意店铺升级任务前往",
            "百货界面已打开",
            report,
            cancel_event,
        )
        run_task(tasker, "百货界面已打开", report, cancel_event)
        seek_department_store_shop(
            tasker,
            controller,
            "点击生鲜超市入口",
            "生鲜超市",
            report,
            cancel_event,
        )
        run_confirmed_transition(
            tasker,
            "点击生鲜超市入口",
            "生鲜超市界面已打开",
            report,
            cancel_event,
            action_already_performed=True,
        )
        ensure_checkbox_selected(
            tasker, "连升十级已勾选", "勾选连升十级", report, cancel_event
        )
        run_task(tasker, "生鲜超市升级", report, cancel_event)
        report("[日常计划] 已执行：任意店铺升级10次")
    elif "fresh_stock" in pending:
        enter_fresh_supermarket_from_daily(
            tasker, controller, report, cancel_event
        )

    if "store_upgrade" in pending or "fresh_stock" in pending:
        if "fresh_stock" in pending:
            run_confirmed_transition(
                tasker,
                "点击进货",
                "进货界面已打开",
                report,
                cancel_event,
            )
            report("[进货] 已确认进入进货页面，开始检查“一键进货”选项")
            ensure_checkbox_selected(
                tasker, "一键进货已勾选", "勾选一键进货", report, cancel_event
            )
            report("[进货] 已确认“一键进货”处于选中状态，准备开始进货")
            run_task(tasker, "开始进货", report, cancel_event)
            report("[进货] 已点击开始进货，等待进货成功结果")
            dismiss_result_overlay(
                tasker, controller, "进货成功弹层", report, cancel_event
            )
            run_confirmed_transition(
                tasker,
                "进货界面返回生鲜超市",
                "生鲜超市界面已打开",
                report,
                cancel_event,
            )
            report("[日常计划] 已执行：生鲜超市进货1次")
        run_confirmed_transition(
            tasker,
            "生鲜超市返回百货",
            "百货界面已打开",
            report,
            cancel_event,
        )
        at_department_store = True

    if "lucky_draw" in pending:
        if at_department_store:
            run_confirmed_transition(
                tasker,
                "点击幸运扭蛋",
                "幸运扭蛋界面已打开",
                report,
                cancel_event,
            )
        else:
            enter_lucky_draw_from_daily(
                tasker, controller, report, cancel_event
            )
        run_task(tasker, "抽一次", report, cancel_event)
        dismiss_result_overlay(
            tasker,
            controller,
            "幸运扭蛋结果弹层",
            report,
            cancel_event,
            wait_timeout_seconds=LUCKY_DRAW_RESULT_TIMEOUT_SECONDS,
        )
        run_confirmed_transition(
            tasker,
            "幸运扭蛋返回百货",
            "百货界面已打开",
            report,
            cancel_event,
        )
        at_department_store = True
        report("[日常计划] 已执行：幸运扭蛋抽奖1次")

    if "club_exchange" in pending:
        if at_department_store:
            click_bottom_commercial_street(tasker, report, cancel_event)
            at_department_store = False
        else:
            run_daily_forward(
                tasker,
                controller,
                "私人会馆兑换任务前往",
                "主界面已到达",
                report,
                cancel_event,
            )
        run_confirmed_transition(
            tasker,
            "点击主页私人会馆入口",
            "私人会馆界面已打开",
            report,
            cancel_event,
        )
        run_confirmed_transition(
            tasker, "点击兑换", "兑换商店界面已打开", report, cancel_event
        )
        run_confirmed_transition(
            tasker, "点击分钟卡价格", "分钟卡兑换界面已打开", report, cancel_event
        )
        run_task(tasker, "购买分钟卡", report, cancel_event)
        dismiss_result_overlay(
            tasker, controller, "分钟卡兑换结果弹层", report, cancel_event
        )
        run_confirmed_transition(
            tasker,
            "兑换商店返回私人会馆",
            "私人会馆界面已打开",
            report,
            cancel_event,
        )
        run_confirmed_transition(
            tasker,
            "私人会馆返回主页",
            "主界面已到达",
            report,
            cancel_event,
        )
        report("[日常计划] 已执行：私人会馆商店兑换1次商品")
        return_to_daily(tasker, report, cancel_event)

    if at_department_store:
        click_bottom_commercial_street(tasker, report, cancel_event)
        return_to_daily(tasker, report, cancel_event)


def complete_artist_daily_group(
    tasker: Tasker,
    controller: AdbController,
    daily_plan: dict[str, str],
    report: Reporter = print,
    cancel_event=None,
) -> None:
    if daily_plan.get("artist_promote") != DAILY_STATE_TODO:
        report(
            "[日常计划] 跳过艺人宣传3次："
            f"状态={daily_plan.get('artist_promote', DAILY_STATE_UNKNOWN)}"
        )
        return
    report("[日常计划] 执行艺人宣传3次")
    enter_artist_from_daily(tasker, controller, report, cancel_event)
    report("[艺人宣传] 已进入艺人列表，开始检查“一键宣传”选项")
    ensure_checkbox_selected(tasker, "一键宣传已勾选", "勾选一键宣传", report, cancel_event)
    report("[艺人宣传] 已确认“一键宣传”处于选中状态，准备点击宣传")
    run_task(tasker, "宣传", report, cancel_event)
    report("[艺人宣传] 已点击宣传，等待宣传结果")
    dismiss_result_overlay(
        tasker,
        controller,
        "一键宣传结果弹层",
        report,
        cancel_event,
        wait_timeout_seconds=ARTIST_PROMOTION_RESULT_TIMEOUT_SECONDS,
    )
    run_confirmed_transition(
        tasker,
        "艺人返回影视城",
        "影视城界面已打开",
        report,
        cancel_event,
    )
    click_bottom_commercial_street(tasker, report, cancel_event)
    return_to_daily(tasker, report, cancel_event)


def complete_partner_daily_group(
    tasker: Tasker,
    controller: AdbController,
    daily_plan: dict[str, str],
    report: Reporter = print,
    cancel_event=None,
) -> None:
    if daily_plan.get("partner_upgrade") != DAILY_STATE_TODO:
        report(
            "[日常计划] 跳过伙伴升级5次："
            f"状态={daily_plan.get('partner_upgrade', DAILY_STATE_UNKNOWN)}"
        )
        return
    report("[日常计划] 执行伙伴升级5次")
    run_daily_forward(
        tasker,
        controller,
        "伙伴升级任务前往",
        "伙伴列表界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "伙伴列表界面已打开", report, cancel_event)

    for attempt, entry in enumerate(PARTNER_CANDIDATE_ENTRIES, start=1):
        report(
            f"[伙伴] 尝试选择可升级伙伴：{entry}"
            f"（{attempt}/{len(PARTNER_CANDIDATE_ENTRIES)}）"
        )
        run_confirmed_transition(
            tasker,
            entry,
            "伙伴详情界面已打开",
            report,
            cancel_event,
        )

        if try_recognize(
            tasker,
            "伙伴可升级",
            timeout_ms=1500,
            report=report,
            cancel_event=cancel_event,
        ):
            report(f"[伙伴] 当前伙伴可执行升级：{entry}")
            break

        if try_recognize(
            tasker,
            "伙伴仅可晋升",
            timeout_ms=1500,
            report=report,
            cancel_event=cancel_event,
        ):
            report(f"[伙伴] 当前伙伴只有晋升，返回列表切换：{entry}")
        else:
            report(f"[伙伴] 当前伙伴未确认到升级按钮，返回列表切换：{entry}")

        run_confirmed_transition(
            tasker,
            "伙伴详情返回列表",
            "伙伴列表界面已打开",
            report,
            cancel_event,
        )
    else:
        raise RuntimeError(
            "已尝试多个固定位置的伙伴，仍未找到可执行升级的伙伴。"
        )

    ensure_checkbox_selected(tasker, "伙伴连升十级已勾选", "勾选伙伴连升十级", report, cancel_event)
    run_task(tasker, "伙伴升级", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "伙伴详情返回列表",
        "伙伴列表界面已打开",
        report,
        cancel_event,
    )
    click_bottom_commercial_street(tasker, report, cancel_event)
    return_to_daily(tasker, report, cancel_event)


def claim_daily_completion_and_exit(
    tasker: Tasker,
    controller: AdbController,
    device,
    report: Reporter = print,
    cancel_event=None,
) -> bool:
    """领取可领取任务和 100 活跃礼包；礼包领取后即为完全完成。"""
    claim_all_daily_rewards(tasker, controller, report, cancel_event)
    if not try_recognize(
        tasker,
        "日常活跃度达到100",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[日常] 活跃度未确认达到 100，保守停止，不退出游戏")
        return False
    claim_daily_100_reward(tasker, controller, report, cancel_event)
    report("[日常] 100 活跃礼包已领取")
    if not try_recognize(
        tasker,
        "日常界面已打开",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[退出] 奖励层关闭后未能确认日常页面，保守保留游戏运行")
        return False
    report("[日常] 已领取最右侧 100 活跃礼包并关闭奖励层，任务完全完成")
    if not close_game_application(device, report):
        report("[退出] 当前账号任务已完成，但游戏未能安全关闭；不会继续下一个账号")
        return False
    return True


def close_game_application(device, report: Reporter = print) -> bool:
    """按已确认包名停止游戏并复核进程，不操作模拟器窗口。"""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    package = os.environ.get("FASHION_MALL_PACKAGE", "").strip() or DEFAULT_GAME_PACKAGE
    if not __import__("re").fullmatch(r"[A-Za-z][\w.]+", package):
        report(f"[退出] 游戏包名格式无效：{package}，保留游戏运行")
        return False

    adb_prefix = [str(device.adb_path), "-s", device.address, "shell"]
    installed = subprocess.run(
        [*adb_prefix, "pm", "path", package],
        text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=20,
        check=False, creationflags=creation_flags,
    )
    if installed.returncode != 0 or f"package:" not in installed.stdout:
        report(f"[退出] 设备中未确认游戏包 {package}，保留游戏运行")
        return False

    stopped = subprocess.run(
        [*adb_prefix, "am", "force-stop", package],
        text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=20,
        check=False, creationflags=creation_flags,
    )
    if stopped.returncode != 0:
        report(f"[退出] force-stop 游戏包失败：{package}，保留游戏运行")
        return False

    for _ in range(5):
        running = subprocess.run(
            [*adb_prefix, "pidof", package],
            text=True, encoding="utf-8", errors="replace", capture_output=True,
            timeout=10, check=False, creationflags=creation_flags,
        )
        if running.returncode != 0 or not running.stdout.strip():
            break
        time.sleep(0.2)
    else:
        report(f"[退出] 游戏进程仍存在：{package}，保留游戏运行")
        return False

    report(
        f"[退出] 已关闭游戏应用（{package}）；"
        "未关闭模拟器，自动化客户端保持打开"
    )
    return True


def complete_factory_research_daily(
    tasker: Tasker,
    controller: AdbController,
    daily_plan: dict[str, str],
    report: Reporter = print,
    cancel_event=None,
) -> None:
    if daily_plan.get("factory_research") != DAILY_STATE_TODO:
        report(
            "[日常计划] 跳过关卡工厂研发5次："
            f"状态={daily_plan.get('factory_research', DAILY_STATE_UNKNOWN)}"
        )
        return
    report("[日常计划] 处理“关卡工厂研发5次”")
    run_daily_forward(
        tasker,
        controller,
        "关卡工厂研发任务前往",
        "关卡工厂界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "关卡工厂界面已打开", report, cancel_event)
    report(
        "[关卡工厂] 本次执行 7 次手动研发；"
        "自动研发必须保持未选中，建造和收购均不计入研发次数"
    )
    complete_factory_research_actions(tasker, controller, report, cancel_event)

    click_bottom_commercial_street(tasker, report, cancel_event)
    run_confirmed_transition(
        tasker,
        "点击日常",
        "日常界面已打开",
        report,
        cancel_event,
    )


def complete_factory_acquisition(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """完成收购谈判；战斗可能自动结束，因此“跳过”只作为可选动作。"""
    report("[关卡工厂-收购] 检测到“收购”，进入收购谈判流程")
    run_confirmed_transition(
        tasker,
        "点击收购按钮",
        "收购挑战准备界面已打开",
        report,
        cancel_event,
    )
    report("[关卡工厂-收购] 已确认挑战准备页，点击“开始挑战”")
    run_task(tasker, "点击开始收购挑战", report, cancel_event)

    deadline = time.monotonic() + FACTORY_ACQUISITION_TIMEOUT_SECONDS
    poll_count = 0
    skipped = False
    while time.monotonic() < deadline:
        ensure_not_cancelled(cancel_event)
        poll_count += 1
        if _try_recognize_once(
            tasker,
            "收购谈判成功结果",
            timeout_ms=POPUP_POLL_TIMEOUT_MS,
        ):
            report(
                "[关卡工厂-收购] 已识别谈判成功结果；"
                f"轮询={poll_count}，是否点击过跳过={'是' if skipped else '否'}"
            )
            capture_debug_step("识别到收购谈判成功结果")
            break

        if not skipped and _try_execute_once(
            tasker,
            "跳过收购谈判",
            POPUP_POLL_TIMEOUT_MS,
        ):
            skipped = True
            report("[关卡工厂-收购] 检测到“跳过”并已点击，等待谈判结果")
            continue
        time.sleep(FACTORY_ACQUISITION_POLL_SECONDS)
    else:
        capture_debug_step("等待收购谈判成功结果超时")
        raise RuntimeError(
            f"开始收购挑战后等待 {FACTORY_ACQUISITION_TIMEOUT_SECONDS:g} 秒，"
            "仍未识别到谈判成功结果。"
        )

    run_task(tasker, "关闭收购谈判成功结果", report, cancel_event)
    confirm_transition(
        tasker,
        "关闭收购谈判成功结果",
        "关卡工厂界面已打开",
        report,
        cancel_event,
    )
    report("[关卡工厂-收购] 已关闭结果并返回关卡工厂，重新判断建造/研发")


def reenter_factory_level_tab_for_acquisition(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """本关没有研发和建造时，重新进入关卡地图以触发下一处收购。"""
    report(
        "[关卡工厂] 等待后仍无“研发”和“建造”，"
        "判断本关建设已完成；重新点击底部“关卡”标签"
    )
    run_confirmed_transition(
        tasker,
        "点击底部关卡标签",
        "关卡地图收购已出现",
        report,
        cancel_event,
    )
    report("[关卡工厂] 重新进入关卡地图后已检测到“收购”")
    complete_factory_acquisition(tasker, report, cancel_event)


def complete_factory_research_actions(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """处理会在“收购”“建造”和“研发”之间切换且位置会移动的工厂按钮。"""
    research_count = 0
    transition_count = 0

    while research_count < FACTORY_RESEARCH_TARGET_COUNT:
        ensure_not_cancelled(cancel_event)
        transition_count += 1
        if transition_count > FACTORY_STATE_MAX_TRANSITIONS:
            raise RuntimeError(
                "关卡工厂状态切换次数过多："
                f"研发仅完成 {research_count}/{FACTORY_RESEARCH_TARGET_COUNT}，"
                "已停止后续操作。"
            )

        report(
            "[关卡工厂] 开始判断当前操作："
            f"研发进度 {research_count}/{FACTORY_RESEARCH_TARGET_COUNT}，"
            f"状态轮次 {transition_count}/{FACTORY_STATE_MAX_TRANSITIONS}"
        )
        if _try_recognize_once(
            tasker,
            "关卡工厂研发按钮已出现",
            timeout_ms=FACTORY_STATE_RECOGNITION_TIMEOUT_MS,
        ):
            report("[关卡工厂] 检测到“研发”；先确认自动研发处于未选中状态")
            ensure_factory_auto_research_unselected(
                tasker,
                controller,
                report,
                cancel_event,
            )
            if not _try_execute_once(
                tasker,
                "点击研发按钮",
                FACTORY_STATE_RECOGNITION_TIMEOUT_MS,
            ):
                report("[关卡工厂] 选项复核后“研发”按钮暂时消失，重新判断当前状态")
                time.sleep(FACTORY_STATE_SETTLE_SECONDS)
                continue
            research_count += 1
            report(
                "[关卡工厂] 检测到“研发”并已点击；"
                f"研发进度 {research_count}/{FACTORY_RESEARCH_TARGET_COUNT}"
            )
            time.sleep(FACTORY_STATE_SETTLE_SECONDS)
            continue

        report("[关卡工厂] 当前未检测到“研发”，继续检查“建造”或“收购”")
        if _try_execute_once(
            tasker,
            "点击建造按钮",
            FACTORY_STATE_RECOGNITION_TIMEOUT_MS,
        ):
            report(
                "[关卡工厂] 检测到“建造”并已点击；"
                "本次不计入研发次数，重新进入研发判断"
            )
            time.sleep(FACTORY_STATE_SETTLE_SECONDS)
            continue

        if _try_recognize_once(
            tasker,
            "点击收购按钮",
            timeout_ms=FACTORY_STATE_RECOGNITION_TIMEOUT_MS,
        ):
            complete_factory_acquisition(tasker, report, cancel_event)
            time.sleep(FACTORY_STATE_SETTLE_SECONDS)
            continue

        reenter_factory_level_tab_for_acquisition(tasker, report, cancel_event)
        time.sleep(FACTORY_STATE_SETTLE_SECONDS)


def validate_credential(value: str, label: str) -> None:
    if not value:
        raise RuntimeError(f"{label}不能为空。")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise RuntimeError(f"{label}包含非 ASCII 字符，当前安全输入方式暂不支持。")


def validate_server_number(value: int) -> None:
    if value < 1 or value > 999:
        raise RuntimeError("区号必须是 1 到 999 之间的整数。")


def run_adb_shell_from_stdin(device, command: str, label: str) -> None:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        [str(device.adb_path), "-s", device.address, "shell"],
        input=f"{command}\nexit\n",
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
        check=False,
        creationflags=creation_flags,
    )
    if process.returncode != 0:
        capture_debug_step(f"失败：通过 ADB {label}")
        raise RuntimeError(f"通过 ADB {label}失败。")
    capture_debug_step(f"完成：通过 ADB {label}")


def clear_focused_text(device, label: str) -> None:
    commands = ["input keyevent 123"]
    commands.extend("input keyevent 67" for _ in range(64))
    run_adb_shell_from_stdin(device, "\n".join(commands), f"清空{label}输入框")


def replace_focused_text(device, value: str, label: str) -> None:
    clear_focused_text(device, label)

    escaped_value = shlex.quote(value)
    run_adb_shell_from_stdin(device, f"input text {escaped_value}", f"输入{label}")


def run_automation(
    account: str,
    password: str,
    server_number: int = 1,
    device=None,
    report: Reporter = print,
    cancel_event=None,
    debug_screenshot_dir: Path | None = None,
) -> bool:
    global _ACTIVE_STEP_SCREENSHOT_RECORDER
    require_ocr_model()
    validate_credential(account, "账号")
    validate_credential(password, "密码")
    validate_server_number(server_number)
    ensure_not_cancelled(cancel_event)

    prepare_secure_runtime()
    Toolkit.init_option(str(RUNTIME_DIR))

    if device is None:
        devices = find_adb_devices()
        if not devices:
            raise RuntimeError("没有发现 ADB 设备，请先启动 MuMu 模拟器并开启 ADB。")
        device = devices[0]

    report(f"连接设备：{device.name} ({device.address})")
    controller = AdbController(
        adb_path=device.adb_path,
        address=device.address,
        screencap_methods=device.screencap_methods,
        input_methods=device.input_methods,
        config=device.config,
    )
    if not controller.set_screenshot_target_long_side(REFERENCE_SCREEN_HEIGHT):
        raise RuntimeError("无法配置 MaaFramework 截图缩放。")
    wait_job(controller.post_connection(), "连接模拟器")
    ensure_not_cancelled(cancel_event)

    if debug_screenshot_dir is not None:
        _ACTIVE_STEP_SCREENSHOT_RECORDER = StepScreenshotRecorder(
            controller,
            Path(debug_screenshot_dir),
            report,
        )
        report(f"[调试截图] 已启用：{debug_screenshot_dir}")
        capture_debug_step("完成：连接模拟器")

    try:
        resource = Resource()
        wait_job(resource.post_bundle(RESOURCE_DIR), "加载项目资源")
        ensure_not_cancelled(cancel_event)

        tasker = Tasker()
        tasker.bind(resource, controller)
        if not tasker.inited:
            capture_debug_step("失败：MaaFramework Tasker 初始化")
            raise RuntimeError("MaaFramework Tasker 初始化失败。")

        run_task(tasker, "打开游戏到登录页", report, cancel_event)
        validate_reference_canvas(controller, report)

        run_task(tasker, "聚焦账号输入框", report, cancel_event)
        replace_focused_text(device, account, "账号")
        run_task(tasker, "账号输入已完成", report, cancel_event)

        run_task(tasker, "聚焦密码输入框", report, cancel_event)
        replace_focused_text(device, password, "密码")
        run_task(tasker, "密码输入已完成", report, cancel_event)

        ensure_checkbox_selected(
            tasker,
            "用户协议已勾选",
            "勾选用户协议固定位置",
            report,
            cancel_event,
        )
        run_task(tasker, "点击登录按钮", report, cancel_event)
        select_server(tasker, controller, server_number, report, cancel_event)
        report(f"[选服] 已复核为 {server_number} 区，现在点击开始")
        run_task(tasker, "点击开始按钮", report, cancel_event)
        handle_delayed_popups(tasker, controller, report, cancel_event)
        wait_for_main_screen(tasker, report, cancel_event)
        run_confirmed_transition(
            tasker,
            "点击日常",
            "日常界面已打开",
            report,
            cancel_event,
        )
        daily_plan = inventory_daily_tasks(tasker, controller, report, cancel_event)
        complete_commercial_daily_group(
            tasker, controller, daily_plan, report, cancel_event
        )
        complete_artist_daily_group(
            tasker, controller, daily_plan, report, cancel_event
        )
        complete_partner_daily_group(
            tasker, controller, daily_plan, report, cancel_event
        )
        complete_factory_research_daily(
            tasker, controller, daily_plan, report, cancel_event
        )
        report("[日常计划] 名媛会培育、商战、环球差旅、伙伴培训按本轮要求暂不执行")
        if not claim_daily_completion_and_exit(tasker, controller, device, report, cancel_event):
            report("已完成当前可执行日常流程；100 活跃礼包领取条件未确认满足，尚未完全完成。")
            return False
        else:
            report(
                "已领取日常 100 活跃礼包，任务已完全完成；"
                "游戏关闭流程已执行，自动化客户端保持打开。"
            )
            return True
    finally:
        _ACTIVE_STEP_SCREENSHOT_RECORDER = None


def main() -> None:
    accounts = [item for item in load_account_configs() if item["active"]]
    if accounts:
        print(f"已从本地配置读取 {len(accounts)} 个启用账号。")
    else:
        print("首次运行，请输入账号密码；随后会明文保存在本地配置文件中。")
        account = input("游戏账号：").strip()
        password = getpass("游戏密码（输入时不会显示）：")
        server_number = int(input("目标区号：").strip())
        save_local_config(account, password, server_number)
        accounts = [
            {
                "account": account,
                "password": password,
                "server_number": server_number,
                "active": True,
            }
        ]
    device = choose_device()
    for index, account_config in enumerate(accounts, start=1):
        print(f"开始执行第 {index}/{len(accounts)} 个账号。")
        completed = run_automation(
            account_config["account"],
            account_config["password"],
            server_number=account_config["server_number"],
            device=device,
        )
        if not completed:
            print("当前账号未完全完成或游戏未安全关闭，停止后续账号。")
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, AutomationCancelled):
        print("\n用户取消。")
    except Exception as error:
        print(f"\n执行失败：{error}")
        raise SystemExit(1) from error
