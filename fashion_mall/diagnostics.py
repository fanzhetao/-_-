"""自动化错误诊断包的生成辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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

ERROR_ARCHIVE_MAX_AGE_DAYS = 14
ERROR_ARCHIVE_MAX_PER_ACCOUNT = 10
ERROR_ARCHIVE_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
_ARCHIVE_ACCOUNT_PATTERN = re.compile(
    r"^(?P<account>.*)_\d{8}-\d{6}-\d{6}(?:_\d+)?$"
)


@dataclass(frozen=True)
class CleanupResult:
    scanned_count: int
    removed_count: int
    removed_bytes: int
    failed_count: int = 0


def _archive_account_key(path: Path) -> str:
    match = _ARCHIVE_ACCOUNT_PATTERN.fullmatch(path.stem)
    return match.group("account") if match else path.stem


def cleanup_error_archives(
    archive_root: Path,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    protected_paths: tuple[Path, ...] = (),
) -> CleanupResult:
    """按时间、每账号数量和总容量清理诊断 ZIP，并保护全局最新包。"""

    if not archive_root.is_dir():
        return CleanupResult(0, 0, 0)

    archives = []
    for path in archive_root.glob("*.zip"):
        try:
            if path.is_file():
                stat = path.stat()
                archives.append((path, stat.st_mtime, stat.st_size))
        except OSError:
            continue
    archives.sort(key=lambda item: (item[1], item[0].name), reverse=True)
    if not archives:
        return CleanupResult(0, 0, 0)

    protected = {path.resolve() for path in protected_paths}
    protected.add(archives[0][0].resolve())
    selected: set[Path] = set()
    current_time = now or datetime.now()
    cutoff_timestamp = (current_time - timedelta(days=ERROR_ARCHIVE_MAX_AGE_DAYS)).timestamp()

    for path, modified_time, _size in archives:
        if path.resolve() not in protected and modified_time < cutoff_timestamp:
            selected.add(path)

    by_account: dict[str, list[tuple[Path, float, int]]] = {}
    for item in archives:
        by_account.setdefault(_archive_account_key(item[0]), []).append(item)
    for account_archives in by_account.values():
        for path, _modified_time, _size in account_archives[
            ERROR_ARCHIVE_MAX_PER_ACCOUNT:
        ]:
            if path.resolve() not in protected:
                selected.add(path)

    remaining_size = sum(
        size for path, _modified_time, size in archives if path not in selected
    )
    if remaining_size > ERROR_ARCHIVE_MAX_TOTAL_BYTES:
        for path, _modified_time, size in reversed(archives):
            if remaining_size <= ERROR_ARCHIVE_MAX_TOTAL_BYTES:
                break
            if path in selected or path.resolve() in protected:
                continue
            selected.add(path)
            remaining_size -= size

    selected_info = [item for item in archives if item[0] in selected]
    if dry_run:
        return CleanupResult(
            len(archives),
            len(selected_info),
            sum(item[2] for item in selected_info),
        )

    removed_count = 0
    removed_bytes = 0
    failed_count = 0
    for path, _modified_time, size in selected_info:
        try:
            path.unlink()
        except OSError:
            failed_count += 1
        else:
            removed_count += 1
            removed_bytes += size
    return CleanupResult(
        len(archives), removed_count, removed_bytes, failed_count
    )


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
