"""统一的用户文案和运行日志表达。

流程节点名和 OCR 目标文本属于自动化协议，不在这里改写；本模块只处理
客户端、运行日志、诊断包和命令行会展示给用户的文字。
"""

from __future__ import annotations


APP_NAME = "时尚百货城自动化客户端"
ACCOUNT_QUEUE = "账号队列"
TARGET_SERVER = "目标区服"
CULTIVATION_LEVEL = "培育档位"
ERROR_ARCHIVE = "错误诊断包"


_LOG_PREFIX_REPLACEMENTS = (
    ("[弹窗恢复]", "[弹窗处理]"),
    ("[选项检查]", "[状态确认]"),
    ("[主界面识别]", "[页面确认]"),
    ("[未知弹窗兜底]", "[弹窗兜底]"),
    ("[执行]", "[任务执行]"),
    ("[进服检查]", "[页面确认]"),
    ("[登录失败]", "[登录]"),
    ("[进程错误恢复]", "[任务恢复]"),
    ("[任务错误继续]", "[任务恢复]"),
    ("[日常]", "[日常任务]"),
    ("[退出]", "[游戏退出]"),
    ("[调试截图]", "[调试截图]"),
)

_LOG_TEXT_REPLACEMENTS = (
    ("报错诊断", ERROR_ARCHIVE),
    ("诊断 ZIP", ERROR_ARCHIVE),
    ("进程错误", "运行错误"),
    ("业务任务错误", "任务错误"),
    ("业务任务出错", "任务出错"),
)


def normalize_log_message(message: str) -> str:
    """将历史日志调用统一为稳定的模块标签和用户术语。"""

    normalized = str(message)
    for old, new in _LOG_PREFIX_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    for old, new in _LOG_TEXT_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    return normalized

