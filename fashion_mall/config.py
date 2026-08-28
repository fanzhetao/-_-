"""本地配置的读取、规范化和原子写入。

该模块不依赖 Tkinter、MaaFramework 或设备对象，因而可以在没有模拟器的
环境中独立测试。校验规则通过回调注入，保持客户端现有的安全边界和错误
消息由兼容入口统一决定。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable


Validator = Callable[[object], object]


def read_local_config(path: Path) -> dict:
    """读取 JSON 配置；文件不存在、损坏或根值不是对象时返回空字典。"""

    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_level(value: object, levels: Iterable[str], default: str) -> str:
    """将培育档位限制在受支持集合内。"""

    normalized = str(value or "").strip()
    return normalized if normalized in levels else default


def normalize_levels(
    value: object,
    levels: Iterable[str],
    default: Iterable[str],
) -> list[str]:
    """规范化多选培育档位，并按界面固定顺序去重。"""

    level_values = tuple(levels)
    if isinstance(value, str):
        requested = {value.strip()}
    elif isinstance(value, (list, tuple, set)):
        requested = {str(item).strip() for item in value}
    else:
        requested = set()
    normalized = [level for level in level_values if level in requested]
    if normalized:
        return normalized
    default_values = {str(item).strip() for item in default}
    return [level for level in level_values if level in default_values]


def load_accounts(
    config: dict,
    *,
    levels: Iterable[str],
    default_levels: Iterable[str],
) -> list[dict]:
    """读取多账号格式，并兼容旧版单账号格式。

    返回值始终是新的普通字典列表，调用方可以安全修改，不会反向改变
    JSON 解析结果。
    """

    level_values = tuple(levels)
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
                    "cultivation_levels": normalize_levels(
                        item.get("cultivation_levels", item.get("cultivation_level")),
                        level_values,
                        default_levels,
                    ),
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
                "cultivation_levels": normalize_levels(
                    config.get("cultivation_levels", config.get("cultivation_level")),
                    level_values,
                    default_levels,
                ),
                "active": True,
            }
        ]
    return []


def load_continue_on_process_error(config: dict) -> bool:
    """读取进程错误后关闭游戏并继续下一账号的全局模式。"""

    return bool(config.get("continue_on_process_error", False))


def load_package_error_diagnostics(config: dict) -> bool:
    """读取发生错误时是否生成最近五步 ZIP 诊断包。"""

    return bool(config.get("package_error_diagnostics", True))


def load_continue_on_task_error(config: dict) -> bool:
    """读取业务任务出错后视为完成并继续的运行模式。"""

    return bool(config.get("continue_on_task_error", False))


def normalize_accounts_for_save(
    accounts: Iterable[dict],
    *,
    default_levels: Iterable[str],
    validate_credential: Callable[[str, str], object],
    validate_server_number: Callable[[int], object],
    validate_levels: Callable[[object], list[str]],
) -> list[dict]:
    """校验并转换待保存的账号队列。"""

    normalized_accounts = []
    for item in accounts:
        account = str(item.get("account", "")).strip()
        password = str(item.get("password", ""))
        server_number = int(item.get("server_number", 1))
        validate_credential(account, "账号")
        validate_credential(password, "密码")
        validate_server_number(server_number)
        cultivation_levels = validate_levels(
            item.get(
                "cultivation_levels",
                item.get("cultivation_level", list(default_levels)),
            )
        )
        normalized_accounts.append(
            {
                "account": account,
                "password": password,
                "server_number": server_number,
                "cultivation_levels": cultivation_levels,
                "active": bool(item.get("active", True)),
            }
        )
    return normalized_accounts


def write_accounts(
    path: Path,
    accounts: Iterable[dict],
    *,
    default_levels: Iterable[str],
    validate_credential: Callable[[str, str], object],
    validate_server_number: Callable[[int], object],
    validate_levels: Callable[[object], list[str]],
    continue_on_process_error: bool = False,
    package_error_diagnostics: bool = True,
    continue_on_task_error: bool = False,
) -> None:
    """以临时文件替换方式写入账号配置，避免留下半截 JSON。"""

    normalized_accounts = normalize_accounts_for_save(
        accounts,
        default_levels=default_levels,
        validate_credential=validate_credential,
        validate_server_number=validate_server_number,
        validate_levels=validate_levels,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "accounts": normalized_accounts,
        "continue_on_process_error": bool(continue_on_process_error),
        "package_error_diagnostics": bool(package_error_diagnostics),
        "continue_on_task_error": bool(continue_on_task_error),
    }
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    temp_path.replace(path)


def clear_config(path: Path) -> None:
    """删除本地配置（不存在时保持幂等）。"""

    if path.is_file():
        path.unlink()
