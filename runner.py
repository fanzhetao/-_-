from __future__ import annotations

from getpass import getpass
import json
import os
from pathlib import Path
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
DEPARTMENT_STORE_VERTICAL_VIEWPORTS = 8
DEPARTMENT_STORE_HORIZONTAL_VIEWPORTS = 3
DEPARTMENT_STORE_VERTICAL_REWIND_SWIPES = 6
DEPARTMENT_STORE_HORIZONTAL_REWIND_SWIPES = 3
DAILY_ACTION_RETRIES = 3
DAILY_TRANSITION_CHECKS = 3
DAILY_DESTINATION_TIMEOUT_MS = 2000
DAILY_SOURCE_PAGE_TIMEOUT_MS = 1000
TRANSITION_CONFIRM_TIMEOUT_SECONDS = 3.0
TRANSITION_CONFIRM_POLL_TIMEOUT_MS = 500
TRANSITION_CONFIRM_POLL_INTERVAL_SECONDS = 0.1
TRANSITION_ACTION_RETRIES = 3
PARTNER_CANDIDATE_ENTRIES = (
    "点击第五个伙伴",
    "点击第六个伙伴",
    "点击第四个伙伴",
)
Reporter = Callable[[str], None]


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


def save_local_config(account: str, password: str, server_number: int) -> None:
    validate_credential(account, "账号")
    validate_credential(password, "密码")
    validate_server_number(server_number)
    CLIENT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "account": account,
        "password": password,
        "server_number": server_number,
    }
    temp_path = CLIENT_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(CLIENT_CONFIG_PATH)


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


def run_task(
    tasker: Tasker,
    entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report(f"[执行] {entry}")
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
            or entry in {"本次登录不再提示弹窗", "任意活动稍后再去弹窗"}
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
        if try_recognize(
            tasker,
            destination_entry,
            timeout_ms=timeout_ms,
            report=report,
            cancel_event=cancel_event,
            recover_interrupting_popup=False,
        ):
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
    for attempt in range(1, total_attempts + 1):
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


def click_bottom_department_store(
    tasker: Tasker,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    run_confirmed_transition(
        tasker,
        "点击百货返回主页",
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


def ensure_checkbox_selected(
    tasker: Tasker,
    checked_entry: str,
    click_entry: str,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    if checkbox_is_selected(tasker, checked_entry, report, cancel_event):
        report(f"[选项] 已确认勾选：{checked_entry}")
        return

    report(f"[选项] 当前未勾选，准备点击：{checked_entry}")
    run_task(tasker, click_entry, report, cancel_event)
    deadline = time.monotonic() + CHECKBOX_CONFIRM_TIMEOUT_SECONDS
    while True:
        ensure_not_cancelled(cancel_event)
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break
        if checkbox_is_selected(
            tasker,
            checked_entry,
            report,
            cancel_event,
            timeout_ms=min(
                POPUP_POLL_TIMEOUT_MS,
                max(1, int(remaining_seconds * 1000)),
            ),
        ):
            report(f"[选项] 点击后已确认绿色勾：{checked_entry}")
            return
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds > 0:
            time.sleep(min(CHECKBOX_CONFIRM_INTERVAL_SECONDS, remaining_seconds))

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
) -> None:
    deadline = time.monotonic() + TRANSITION_CONFIRM_TIMEOUT_SECONDS
    while True:
        ensure_not_cancelled(cancel_event)
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise RuntimeError(
                f"等待 {TRANSITION_CONFIRM_TIMEOUT_SECONDS:g} 秒后仍未识别到结果弹层："
                f"{result_entry}"
            )
        if try_recognize(
            tasker,
            result_entry,
            timeout_ms=min(
                TRANSITION_CONFIRM_POLL_TIMEOUT_MS,
                max(1, int(remaining_seconds * 1000)),
            ),
            report=report,
            cancel_event=cancel_event,
        ):
            report(f"[跳转确认] 已确认结果弹层：{result_entry}")
            break
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds > 0:
            time.sleep(min(TRANSITION_CONFIRM_POLL_INTERVAL_SECONDS, remaining_seconds))
    ensure_not_cancelled(cancel_event)
    # 结果层明确提示“点击任意处关闭”；使用左上安全空白区，避开底部按钮。
    wait_job(controller.post_click(80, 220), "关闭结果弹层")
    time.sleep(0.35)
    if try_recognize(
        tasker, result_entry, report=report, cancel_event=cancel_event
    ):
        raise RuntimeError(f"结果弹层未关闭：{result_entry}")


def complete_commercial_daily_group(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    """百货组只从日常前往一次，后续任务复用百货底部 Tab。"""
    report("[日常计划] 批量处理百货组")
    report("[日常计划] 直接从“任意店铺升级10次”前往百货，不预判完成状态")
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
    ensure_checkbox_selected(tasker, "连升十级已勾选", "勾选连升十级", report, cancel_event)
    run_task(tasker, "生鲜超市升级", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "点击进货",
        "进货界面已打开",
        report,
        cancel_event,
    )
    ensure_checkbox_selected(tasker, "一键进货已勾选", "勾选一键进货", report, cancel_event)
    run_task(tasker, "开始进货", report, cancel_event)
    dismiss_result_overlay(tasker, controller, "进货成功弹层", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "进货界面返回生鲜超市",
        "生鲜超市界面已打开",
        report,
        cancel_event,
    )
    run_confirmed_transition(
        tasker,
        "生鲜超市返回百货",
        "百货界面已打开",
        report,
        cancel_event,
    )

    run_confirmed_transition(
        tasker,
        "点击幸运扭蛋",
        "幸运扭蛋界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "抽一次", report, cancel_event)
    dismiss_result_overlay(tasker, controller, "幸运扭蛋结果弹层", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "幸运扭蛋返回百货",
        "百货界面已打开",
        report,
        cancel_event,
    )

    run_confirmed_transition(
        tasker,
        "点击私人会馆",
        "私人会馆界面已打开",
        report,
        cancel_event,
    )
    run_confirmed_transition(
        tasker,
        "点击兑换",
        "兑换商店界面已打开",
        report,
        cancel_event,
    )
    run_confirmed_transition(
        tasker,
        "点击分钟卡价格",
        "分钟卡兑换界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "购买分钟卡", report, cancel_event)
    dismiss_result_overlay(tasker, controller, "分钟卡兑换结果弹层", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "兑换商店返回私人会馆",
        "私人会馆界面已打开",
        report,
        cancel_event,
    )
    run_confirmed_transition(
        tasker,
        "私人会馆返回百货",
        "百货界面已打开",
        report,
        cancel_event,
    )

    click_bottom_department_store(tasker, report, cancel_event)
    return_to_daily(tasker, report, cancel_event)


def complete_artist_daily_group(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report("[日常计划] 直接执行艺人宣传，不预判完成状态")
    run_daily_forward(
        tasker,
        controller,
        "艺人宣传任务前往",
        "影视城界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "影视城界面已打开", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "点击艺人",
        "艺人界面已打开",
        report,
        cancel_event,
    )
    ensure_checkbox_selected(tasker, "一键宣传已勾选", "勾选一键宣传", report, cancel_event)
    run_task(tasker, "宣传", report, cancel_event)
    dismiss_result_overlay(tasker, controller, "一键宣传结果弹层", report, cancel_event)
    run_confirmed_transition(
        tasker,
        "艺人返回影视城",
        "影视城界面已打开",
        report,
        cancel_event,
    )
    click_bottom_department_store(tasker, report, cancel_event)
    return_to_daily(tasker, report, cancel_event)


def complete_partner_daily_group(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report("[日常计划] 直接执行伙伴升级，不预判完成状态")
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
    click_bottom_department_store(tasker, report, cancel_event)
    return_to_daily(tasker, report, cancel_event)


def claim_daily_completion_and_exit(
    tasker: Tasker,
    controller: AdbController,
    device,
    report: Reporter = print,
    cancel_event=None,
) -> bool:
    """领取可领取任务和 100 活跃礼包；活跃度不足时绝不退出。"""
    claim_all_daily_rewards(tasker, controller, report, cancel_event)
    if not try_recognize(
        tasker,
        "日常活跃度达到100",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[日常] 活跃度未确认达到 100，保守停止，不退出游戏")
        return False
    run_task(tasker, "领取日常100活跃礼包", report, cancel_event)
    dismiss_result_overlay(tasker, controller, "日常100活跃礼包结果弹层", report, cancel_event)
    report("[日常] 100 活跃礼包已领取")
    if not try_recognize(
        tasker,
        "日常界面已打开",
        report=report,
        cancel_event=cancel_event,
    ):
        report("[退出] 奖励层关闭后未能确认日常页面，保守保留游戏运行")
        return False
    return close_game_application(device, report)


def close_game_application(device, report: Reporter = print) -> bool:
    """仅停止当前前台游戏包，不操作模拟器窗口；无法确认时保守跳过。"""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        [str(device.adb_path), "-s", device.address, "shell", "dumpsys", "window", "windows"],
        text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=20,
        check=False, creationflags=creation_flags,
    )
    if process.returncode != 0:
        report("[退出] 无法确认前台应用，保留游戏运行")
        return False
    package = None
    for line in process.stdout.splitlines():
        if "mCurrentFocus" not in line and "mFocusedApp" not in line:
            continue
        match = __import__("re").search(r"(?:u\d+_)?([A-Za-z][\w.]+)/", line)
        if match:
            package = match.group(1)
            break
    configured_package = os.environ.get("FASHION_MALL_PACKAGE", "").strip()
    if configured_package and package != configured_package:
        report(f"[退出] 前台包名 {package} 与 FASHION_MALL_PACKAGE 不一致，保留游戏运行")
        return False
    if not package or package.startswith(("com.android.", "com.google.android.", "android")):
        report("[退出] 未确认游戏包名，保留游戏运行")
        return False
    run_adb_shell_from_stdin(device, f"am force-stop {package}", "关闭游戏应用")
    report(f"[退出] 已关闭游戏应用（{package}），未关闭模拟器")
    return True


def complete_factory_research_daily(
    tasker: Tasker,
    controller: AdbController,
    report: Reporter = print,
    cancel_event=None,
) -> None:
    report("[日常计划] 处理“关卡工厂研发5次”")
    report("[日常计划] 直接执行关卡工厂研发，不预判完成状态")
    run_daily_forward(
        tasker,
        controller,
        "关卡工厂研发任务前往",
        "关卡工厂界面已打开",
        report,
        cancel_event,
    )
    run_task(tasker, "关卡工厂界面已打开", report, cancel_event)
    for index in range(1, 6):
        run_task(tasker, "点击研发按钮", report, cancel_event)
        report(f"[日常计划] 已执行研发 {index}/5")

    click_bottom_department_store(tasker, report, cancel_event)
    run_confirmed_transition(
        tasker,
        "点击日常",
        "日常界面已打开",
        report,
        cancel_event,
    )


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
) -> None:
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
    validate_reference_canvas(controller, report)

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

        run_task(tasker, "聚焦账号输入框", report, cancel_event)
        replace_focused_text(device, account, "账号")
        run_task(tasker, "账号输入已完成", report, cancel_event)

        run_task(tasker, "聚焦密码输入框", report, cancel_event)
        replace_focused_text(device, password, "密码")
        run_task(tasker, "密码输入已完成", report, cancel_event)

        run_task(tasker, "勾选协议并登录", report, cancel_event)
        select_server(tasker, controller, server_number, report, cancel_event)
        report(f"[选服] 已复核为 {server_number} 区，现在点击开始")
        run_task(tasker, "点击开始按钮", report, cancel_event)
        handle_delayed_popups(tasker, controller, report, cancel_event)
        run_task(tasker, "主界面已到达", report, cancel_event)
        run_confirmed_transition(
            tasker,
            "点击日常",
            "日常界面已打开",
            report,
            cancel_event,
        )
        complete_commercial_daily_group(tasker, controller, report, cancel_event)
        complete_artist_daily_group(tasker, controller, report, cancel_event)
        complete_partner_daily_group(tasker, controller, report, cancel_event)
        complete_factory_research_daily(tasker, controller, report, cancel_event)
        report("[日常计划] 名媛会培育、商战、环球差旅、伙伴培训按本轮要求暂不执行")
        if not claim_daily_completion_and_exit(tasker, controller, device, report, cancel_event):
            report("已完成当前可执行日常流程；最终完成条件或退出确认未满足，游戏保持运行。")
        else:
            report("已完成日常奖励扫描、100 活跃礼包领取并退出游戏。")
    finally:
        _ACTIVE_STEP_SCREENSHOT_RECORDER = None


def main() -> None:
    config = load_local_config()
    account = str(config.get("account", "")).strip()
    password = str(config.get("password", ""))
    try:
        server_number = int(config.get("server_number", 1))
    except (TypeError, ValueError):
        server_number = 1

    if account and password:
        print(f"已从本地配置读取账号、密码和目标区号（{server_number} 区）。")
    else:
        print("首次运行，请输入账号密码；随后会明文保存在本地配置文件中。")
        account = input("游戏账号：").strip()
        password = getpass("游戏密码（输入时不会显示）：")
        server_number = int(input("目标区号：").strip())
        save_local_config(account, password, server_number)
    device = choose_device()
    run_automation(account, password, server_number=server_number, device=device)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, AutomationCancelled):
        print("\n用户取消。")
    except Exception as error:
        print(f"\n执行失败：{error}")
        raise SystemExit(1) from error
