"""自动化错误诊断包的生成辅助。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _safe_filename_part(value: str) -> str:
    """将账号名转换为可用于 Windows ZIP 文件名的片段。"""

    safe_value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    safe_value = safe_value.rstrip(" .")[:80] or "未命名账号"
    if safe_value.upper() in _WINDOWS_RESERVED_NAMES:
        safe_value = f"账号_{safe_value}"
    return safe_value


def archive_recent_steps(
    session_log_path: Path,
    screenshot_dir: Path,
    archive_root: Path,
    *,
    account_name: str,
    account_index: int,
    error_message: str,
    step_count: int = 5,
    timestamp: str | None = None,
) -> Path:
    """将最近若干操作及其截图写入不会被会话清理的 ZIP。"""

    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive_root.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_filename_part(account_name)}_{stamp}"
    archive_path = archive_root / f"{filename}.zip"
    suffix = 1
    while archive_path.exists():
        archive_path = archive_root / f"{filename}_{suffix}.zip"
        suffix += 1

    screenshots = sorted(screenshot_dir.glob("step-*.png"))[-step_count:]

    try:
        log_lines = session_log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        log_lines = []

    # 不同账号的截图都会从 step-0001 开始，必须从日志尾部反查，避免把前一账号
    # 的同名步骤写进当前账号的诊断包。
    recent_lines = []
    for screenshot in screenshots:
        matching_lines = [line for line in log_lines if screenshot.name in line]
        if matching_lines:
            recent_lines.append(matching_lines[-1])
    diagnostic_lines = [
        "时尚百货城自动化客户端错误诊断包",
        f"账号：{account_name}",
        f"账号序号：{account_index}",
        f"错误摘要：{error_message}",
        f"已保存最近操作截图：{len(screenshots)} 张",
        "",
        *recent_lines,
    ]
    diagnostic_text = "\n".join(diagnostic_lines) + "\n"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("recent-steps.log", diagnostic_text)
        for screenshot in screenshots:
            archive.write(screenshot, arcname=screenshot.name)
    return archive_path
