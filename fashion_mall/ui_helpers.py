"""不依赖 Tkinter 的界面辅助函数。"""

from __future__ import annotations


def move_list_item(items: list, item, target_index: int) -> bool:
    """按对象身份移动列表项；返回顺序是否发生变化。"""

    current_index = next(
        (index for index, candidate in enumerate(items) if candidate is item),
        None,
    )
    if current_index is None or not items:
        return False
    target_index = max(0, min(int(target_index), len(items) - 1))
    if current_index == target_index:
        return False
    items.pop(current_index)
    items.insert(target_index, item)
    return True


def drag_insertion_index(pointer_y: int, other_row_centers: list[int]) -> int:
    """根据指针越过的其他行中心数，计算稳定的拖放插入位置。"""

    return sum(pointer_y > center for center in other_row_centers)


def calculate_ui_scale(screen_width: int, screen_height: int, dpi: float) -> float:
    """按屏幕分辨率和 DPI 计算 1.0～2.0 的窗口缩放比例。"""

    dpi_scale = max(dpi, 96.0) / 96.0
    resolution_scale = min(
        max(screen_width, 1) / 1920.0, max(screen_height, 1) / 1080.0
    )
    return max(1.0, min(2.0, max(dpi_scale, resolution_scale)))
