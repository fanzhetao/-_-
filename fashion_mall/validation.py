"""与 Maa/设备无关的输入校验规则。"""

from __future__ import annotations

import re


def server_pattern(server_number: int) -> str:
    """生成选服 OCR 的严格区号匹配表达式。"""

    return rf"^{server_number}(?:区|服)(?:-+.*)?$"


def validate_credential(value: str, label: str) -> None:
    if not value:
        raise RuntimeError(f"{label}不能为空。")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise RuntimeError(f"{label}包含非 ASCII 字符，当前安全输入方式暂不支持。")


def validate_server_number(value: int) -> None:
    if value < 1 or value > 999:
        raise RuntimeError("区号必须是 1 到 999 之间的整数。")
