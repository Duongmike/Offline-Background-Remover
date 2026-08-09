from __future__ import annotations

import unittest

from image_tool.app_modern import APP_NAME, PRIMARY_ACTION_TEXT, _color_sample_hex, _uses_color_controls
from image_tool.color_key_config import ColorSample


class UiStateTests(unittest.TestCase):
    def test_product_name_and_primary_action_are_descriptive(self) -> None:
        self.assertEqual("Xóa Nền AI Offline", APP_NAME)
        self.assertEqual("BẮT ĐẦU XỬ LÝ", PRIMARY_ACTION_TEXT)

    def test_color_controls_are_only_used_by_color_modes(self) -> None:
        self.assertFalse(_uses_color_controls(True, "ai"))
        self.assertTrue(_uses_color_controls(True, "color_key"))
        self.assertTrue(_uses_color_controls(True, "hybrid"))
        self.assertFalse(_uses_color_controls(False, "color_key"))
        self.assertFalse(_uses_color_controls(False, "hybrid"))

    def test_color_sample_hex_is_zero_padded_and_uppercase(self) -> None:
        self.assertEqual("#000FFF", _color_sample_hex(ColorSample((0, 15, 255))))


if __name__ == "__main__":
    unittest.main()
