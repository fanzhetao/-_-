"""可注入依赖的有限重试/恢复控制流。"""

from __future__ import annotations

from collections.abc import Callable


def retry_with_recovery(
    attempt: Callable[[], bool],
    recover: Callable[[], bool],
    *,
    max_recoveries: int,
    ensure_not_cancelled: Callable[[], None],
    should_recover: Callable[[int], bool],
    on_retry: Callable[[], None],
) -> bool:
    """尝试动作，失败后按策略恢复并有限重试。

    ``recovery`` 从 0 开始，最多执行 ``max_recoveries`` 次恢复；恢复失败或
    策略禁止恢复时立即返回 False。取消检查由调用方注入，取消异常会原样传播。
    """

    for recovery in range(max_recoveries + 1):
        ensure_not_cancelled()
        if attempt():
            return True
        if recovery >= max_recoveries or not should_recover(recovery):
            return False
        if not recover():
            return False
        on_retry()
    return False
