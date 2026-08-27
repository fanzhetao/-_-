"""日常任务盘点所需的纯规则、数据结构和几何计算。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable


@dataclass(frozen=True)
class DailyTaskSpec:
    key: str
    label: str
    forward_entry: str
    destination_entry: str
    group: str


@dataclass(frozen=True)
class DailyOcrText:
    text: str
    box: tuple[int, int, int, int]


def normalize_ocr_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def task_label_matches(
    ocr_text: str,
    task_label: str,
    aliases: dict[str, tuple[str, ...]],
) -> bool:
    """兼容任务标题因 UI 换行而被 OCR 拆成多个文本框。"""

    normalized_text = normalize_ocr_text(ocr_text)
    candidates = (task_label, *aliases.get(task_label, ()))
    return any(
        normalize_ocr_text(candidate) in normalized_text for candidate in candidates
    )


def classify_viewport(
    ocr_texts: Iterable[DailyOcrText],
    specs: Iterable[DailyTaskSpec],
    *,
    label_matches: Callable[[str, str], bool],
    todo_state: str,
    claimable_state: str,
    claimed_state: str,
    row_tolerance: int,
) -> dict[str, str]:
    """按纵向中心点把任务标题与同行按钮状态关联。"""

    texts = list(ocr_texts)
    state_boxes: list[tuple[str, int]] = []
    for item in texts:
        x, y, width, height = item.box
        if x + width / 2 < 480:
            continue
        if "已领取" in item.text:
            state = claimed_state
        elif "领取" in item.text:
            state = claimable_state
        elif "前往" in item.text:
            state = todo_state
        else:
            continue
        state_boxes.append((state, y + height // 2))

    found: dict[str, str] = {}
    for spec in specs:
        title_boxes = [
            item for item in texts if label_matches(item.text, spec.label)
        ]
        best_match: tuple[int, str] | None = None
        for title in title_boxes:
            _, y, _, height = title.box
            title_center_y = y + height // 2
            for state, state_center_y in state_boxes:
                distance = abs(title_center_y - state_center_y)
                if distance > row_tolerance:
                    continue
                if best_match is None or distance < best_match[0]:
                    best_match = (distance, state)
        if best_match is not None:
            found[spec.key] = best_match[1]
    return found


def forward_button_center(
    ocr_texts: Iterable[DailyOcrText],
    task_label: str,
    *,
    label_matches: Callable[[str, str], bool],
    row_tolerance: int,
) -> tuple[int, int] | None:
    """返回与目标任务标题纵向最接近的同行“前往”文本框中心。"""

    texts = list(ocr_texts)
    titles = [item for item in texts if label_matches(item.text, task_label)]
    forwards = [
        item
        for item in texts
        if "前往" in item.text and item.box[0] + item.box[2] / 2 >= 480
    ]
    best_match: tuple[float, DailyOcrText] | None = None
    for title in titles:
        _, title_y, _, title_height = title.box
        title_center_y = title_y + title_height / 2
        for forward in forwards:
            _, forward_y, _, forward_height = forward.box
            forward_center_y = forward_y + forward_height / 2
            distance = abs(title_center_y - forward_center_y)
            if distance > row_tolerance:
                continue
            if best_match is None or distance < best_match[0]:
                best_match = (distance, forward)

    if best_match is None:
        return None
    x, y, width, height = best_match[1].box
    return x + width // 2, y + height // 2


def task_label_for_entry(
    entry: str, specs: Iterable[DailyTaskSpec]
) -> str | None:
    for spec in specs:
        if spec.forward_entry == entry:
            return spec.label
    return None
