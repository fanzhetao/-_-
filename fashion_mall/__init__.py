"""时尚百货城自动化客户端的可复用模块。

根目录的 :mod:`runner` 和 :mod:`client` 仍是兼容启动入口；新代码优先放在
此包中，便于按职责测试和复用，而不改变便携版的启动方式。
"""

__all__ = [
    "config",
    "daily_rules",
    "diagnostics",
    "devices",
    "maa_ops",
    "paths",
    "client_state",
    "retry",
    "self_check",
    "store_scan",
    "ui_helpers",
    "validation",
]
