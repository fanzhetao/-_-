"""客户端账号队列的无界面状态辅助。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def active_accounts(accounts: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """按现有顺序返回启用账号，不复制账号内容。"""

    return [account for account in accounts if bool(account.get("active"))]


def require_active_accounts(accounts: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    selected = active_accounts(accounts)
    if not selected:
        raise RuntimeError("请至少启用一个账号。")
    return selected


def progress_message(index: int, total: int, server_number: object) -> str:
    return f"[账号队列] 第 {index}/{total} 个账号开始运行（目标区服：{server_number} 区）"


def incomplete_message(index: int, total: int) -> str:
    return (
        f"第 {index}/{total} 个账号未完全完成“领取 100 活跃礼包并关闭游戏”，"
        "账号队列已停止。"
    )
