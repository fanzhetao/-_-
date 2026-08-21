from __future__ import annotations

import unittest

import numpy as np

from client import calculate_ui_scale
from runner import validate_reference_canvas


class CompletedScreenshotJob:
    succeeded = True

    def __init__(self, image: np.ndarray) -> None:
        self.image = image

    def wait(self) -> None:
        return None

    def get(self) -> np.ndarray:
        return self.image


class FakeController:
    def __init__(self, width: int, height: int, raw_resolution: tuple[int, int]) -> None:
        self.image = np.zeros((height, width, 3), dtype=np.uint8)
        self.resolution = raw_resolution

    def post_screencap(self) -> CompletedScreenshotJob:
        return CompletedScreenshotJob(self.image)


class DisplayAdaptationTests(unittest.TestCase):
    def test_desktop_scale_profiles(self) -> None:
        self.assertEqual(calculate_ui_scale(1920, 1080, 96), 1.0)
        self.assertAlmostEqual(calculate_ui_scale(2560, 1440, 120), 4 / 3)
        self.assertEqual(calculate_ui_scale(3840, 2160, 192), 2.0)

    def test_accepts_normalized_portrait_canvas(self) -> None:
        controller = FakeController(720, 1280, (2160, 3840))
        reports: list[str] = []
        validate_reference_canvas(controller, reports.append)
        self.assertIn("2160×3840", reports[0])
        self.assertIn("720×1280", reports[0])

    def test_rejects_landscape_canvas(self) -> None:
        controller = FakeController(1280, 720, (3840, 2160))
        with self.assertRaisesRegex(RuntimeError, "9:16"):
            validate_reference_canvas(controller)


if __name__ == "__main__":
    unittest.main()
