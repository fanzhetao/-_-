"""进程错误诊断现场的归档辅助。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


def archive_recent_steps(
    session_log_path: Path,
    screenshot_dir: Path,
    archive_root: Path,
    *,
    account_index: int,
    error_message: str,
    step_count: int = 5,
    timestamp: str | None = None,
) -> Path:
    """将最近若干步骤的日志和截图复制到不会被会话清理的独立目录。"""

    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive_dir = archive_root / f"error-{stamp}-account-{account_index}"
    suffix = 1
    while archive_dir.exists():
        archive_dir = archive_root / f"error-{stamp}-account-{account_index}-{suffix}"
        suffix += 1
    archive_dir.mkdir(parents=True)

    screenshots = sorted(screenshot_dir.glob("step-*.png"))[-step_count:]
    for screenshot in screenshots:
        shutil.copy2(screenshot, archive_dir / screenshot.name)

    try:
        log_lines = session_log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        log_lines = []

    selected_names = {path.name for path in screenshots}
    start_index = None
    if selected_names:
        for index, line in enumerate(log_lines):
            if any(name in line for name in selected_names):
                start_index = index
                break
    recent_lines = log_lines[start_index:] if start_index is not None else log_lines[-step_count:]
    diagnostic_lines = [
        "进程错误恢复模式诊断现场",
        f"账号序号：{account_index}",
        f"错误：{error_message}",
        f"已归档截图：{len(screenshots)} 张",
        "",
        *recent_lines,
    ]
    (archive_dir / "recent-steps.log").write_text(
        "\n".join(diagnostic_lines) + "\n", encoding="utf-8"
    )
    return archive_dir
