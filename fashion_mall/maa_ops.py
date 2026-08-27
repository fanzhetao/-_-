"""通用 MaaFramework 作业封装。

业务模块只需要提供截图记录回调；等待、作业成功判断和临时节点覆盖逻辑
集中在这里，避免不同流程出现细微不一致。
"""

from __future__ import annotations

from typing import Callable


def wait_job(job, label: str, capture: Callable[[str], None] | None = None):
    job.wait()
    if not job.succeeded:
        if capture is not None:
            capture(f"失败：{label}")
        raise RuntimeError(f"{label}失败。请检查模拟器当前页面后重试。")
    if capture is not None:
        capture(f"完成：{label}")
    return job


def task_succeeded(job) -> bool:
    job.wait()
    if not job.succeeded:
        return False
    detail = job.get()
    return detail is not None and detail.status.succeeded


def recognize_once(
    tasker,
    entry: str,
    timeout_ms: int,
    *,
    task_succeeded_fn: Callable[[object], bool],
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
    return task_succeeded_fn(tasker.post_task(entry, override))


def execute_once(
    tasker,
    entry: str,
    timeout_ms: int,
    *,
    task_succeeded_fn: Callable[[object], bool],
    capture: Callable[[str], None] | None = None,
) -> bool:
    override = {
        entry: {
            "next": [],
            "pre_delay": 0,
            "post_delay": 0,
            "timeout": timeout_ms,
        }
    }
    succeeded = task_succeeded_fn(tasker.post_task(entry, override))
    if succeeded and capture is not None:
        capture(f"完成可选动作：{entry}")
    return succeeded
