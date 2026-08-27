"""便携版自检的轻量入口。

该模块故意不导入 ``runner``、Tkinter 或设备模块，使窗口程序在自检模式
下不会初始化 GUI、ADB 或自动化流程。
"""

from __future__ import annotations

import re
from pathlib import Path


def distribution_self_check(version_path: Path, ocr_dir: Path) -> None:
    """验证发布包中的版本、OCR 资源和 MaaFramework 运行库。"""

    version = version_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError("VERSION 必须使用 X.Y.Z 格式。")
    missing = [
        name for name in ("det.onnx", "rec.onnx", "keys.txt")
        if not (ocr_dir / name).is_file()
    ]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"缺少 OCR 模型文件：{names}\n"
            f"请将 MaaCommonAssets 的中文 OCR 模型放入：{ocr_dir}"
        )

    from maa.library import Library

    if not Library.version():
        raise RuntimeError("无法读取 MaaFramework 版本。")
