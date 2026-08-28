"""百货店铺标签识别、等级配对和候选选择规则。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import numpy as np


UPGRADEABLE_STORE_NAMES = (
    "潮玩店",
    "电玩城",
    "服装店",
    "生鲜超市",
    "快餐店",
    "写真拍照馆",
    "占卜店",
    "美发沙龙",
    "家居店",
    "儿童乐园",
)
STORE_LEVEL_PATTERN = re.compile(r"(?<!\d)(\d{1,8})级")
GREEN_LABEL_MIN_PIXELS = 40


@dataclass(frozen=True)
class StoreCandidate:
    name: str
    level: int
    box: tuple[int, int, int, int]
    path: tuple[str, ...]
    discovery_order: int = 0

    @property
    def center(self) -> tuple[int, int]:
        x, y, width, height = self.box
        return x + width // 2, y + height // 2


def normalize_store_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def store_name_from_text(value: object) -> str | None:
    normalized = normalize_store_text(value)
    return next((name for name in UPGRADEABLE_STORE_NAMES if name in normalized), None)


def store_level_from_text(value: object) -> int | None:
    match = STORE_LEVEL_PATTERN.search(normalize_store_text(value))
    return int(match.group(1)) if match else None


def green_store_label_pixel_count(
    image: np.ndarray,
    box: tuple[int, int, int, int],
) -> int:
    """统计店名周围浅绿色已开业标签像素；控制器截图为 BGR。"""

    if image is None or image.ndim != 3 or image.shape[2] != 3:
        return 0
    x, y, width, height = box
    left = max(0, x - 75)
    top = max(0, y - 18)
    right = min(image.shape[1], x + width + 75)
    bottom = min(image.shape[0], y + height + 18)
    roi = image[top:bottom, left:right]
    if roi.size == 0:
        return 0
    blue = roi[:, :, 0].astype(np.int16)
    green = roi[:, :, 1].astype(np.int16)
    red = roi[:, :, 2].astype(np.int16)
    pixels = (
        (green >= 170)
        & (green >= blue + 20)
        & (green >= red + 8)
    )
    return int(pixels.sum())


def collect_store_candidates(
    ocr_texts: Iterable[object],
    image: np.ndarray,
    *,
    path: tuple[str, ...] = (),
) -> list[StoreCandidate]:
    """把店名与其正下方等级配对，只返回绿色已开业店铺。"""

    texts = list(ocr_texts)
    name_items: list[tuple[str, tuple[int, int, int, int]]] = []
    level_items: list[tuple[int, tuple[int, int, int, int]]] = []
    for item in texts:
        box = tuple(int(value) for value in getattr(item, "box"))
        name = store_name_from_text(getattr(item, "text", ""))
        if name is not None:
            name_items.append((name, box))
        level = store_level_from_text(getattr(item, "text", ""))
        if level is not None:
            level_items.append((level, box))

    candidates: list[StoreCandidate] = []
    for name, name_box in sorted(name_items, key=lambda item: (item[1][1], item[1][0])):
        if green_store_label_pixel_count(image, name_box) < GREEN_LABEL_MIN_PIXELS:
            continue
        name_x, name_y, name_width, name_height = name_box
        name_center_x = name_x + name_width / 2
        name_bottom = name_y + name_height
        matches: list[tuple[float, int]] = []
        for level, level_box in level_items:
            level_x, level_y, level_width, _level_height = level_box
            level_center_x = level_x + level_width / 2
            vertical_gap = level_y - name_bottom
            if -15 <= vertical_gap <= 130 and abs(level_center_x - name_center_x) <= 170:
                score = abs(level_center_x - name_center_x) + max(vertical_gap, 0) * 0.5
                matches.append((score, level))
        if not matches:
            continue
        level = min(matches)[1]
        candidates.append(StoreCandidate(name, level, name_box, path))
    return candidates


def append_unique_candidates(
    existing: list[StoreCandidate],
    discovered: Iterable[StoreCandidate],
    *,
    limit: int = 3,
) -> None:
    known_names = {candidate.name for candidate in existing}
    for candidate in discovered:
        if candidate.name in known_names:
            continue
        existing.append(
            StoreCandidate(
                candidate.name,
                candidate.level,
                candidate.box,
                candidate.path,
                len(existing),
            )
        )
        known_names.add(candidate.name)
        if len(existing) >= limit:
            return


def choose_lowest_store(candidates: Iterable[StoreCandidate]) -> StoreCandidate:
    values = list(candidates)
    if not values:
        raise RuntimeError("没有识别到可升级的绿色店铺及其等级。")
    return min(values, key=lambda item: (item.level, item.discovery_order))
