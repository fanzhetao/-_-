"""ADB/MuMu 设备发现。

设备发现只负责把可用设备转换为 MaaFramework 的 ``AdbDevice`` 描述，不负责
连接、截图或业务流程。依赖通过参数注入，方便在没有模拟器的机器上测试。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Iterable


def find_mumu_devices(
    manager_candidates: Iterable[Path],
    *,
    adb_device_factory: Callable[..., object],
    screencap_methods: int,
    input_methods: int,
) -> list:
    """通过 MuMuManager 查询正在运行的实例。"""

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for manager_path in manager_candidates:
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
        devices = []
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
                adb_device_factory(
                    name="MuMu安卓设备-MuMuPlayer v5+",
                    adb_path=adb_path,
                    address=f"{host}:{port}",
                    screencap_methods=screencap_methods,
                    input_methods=input_methods,
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


def find_adb_devices(
    *,
    toolkit,
    mumu_finder: Callable[[], list],
    local_candidates: Iterable[Path],
) -> list:
    """按 Maa 已发现设备、MuMu 专用通道、系统 ADB 的优先级查找设备。"""

    devices = toolkit.find_adb_devices()
    special_devices = [device for device in devices if device.config.get("extras")]
    if special_devices:
        return special_devices

    mumu_devices = mumu_finder()
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
    candidates.extend(local_candidates)
    for adb_path in candidates:
        if adb_path.is_file():
            devices = toolkit.find_adb_devices(adb_path)
            if devices:
                return devices
    return []
