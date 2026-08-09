from __future__ import annotations

import unittest

import numpy as np
from PIL import Image

from image_tool.color_key import (
    color_probability,
    connected_background,
    hsv_hue_circular_distance,
    preview_to_original,
    remove_by_advanced_color_key,
    suppress_green_spill,
)
from image_tool.color_key_config import ColorKeyConfig, ColorSample
from image_tool.manual_mask import ManualMaskEditor, MaskStroke, apply_manual_strokes


class ColorKeyTests(unittest.TestCase):
    def test_hue_wrap_around_is_small(self) -> None:
        self.assertLess(hsv_hue_circular_distance(359, 1), 0.02)

    def test_multiple_colour_samples_match_gradient_endpoints(self) -> None:
        pixels = np.array([[[20, 120, 30], [40, 170, 55], [220, 20, 20]]], dtype=np.uint8)
        probability = color_probability(pixels, (ColorSample((20, 120, 30)), ColorSample((40, 170, 55))), ColorKeyConfig())
        self.assertGreater(probability[0, 0], 0.9)
        self.assertGreater(probability[0, 1], 0.9)
        self.assertLess(probability[0, 2], 0.1)

    def test_gradient_background_has_soft_alpha(self) -> None:
        gradient = np.zeros((32, 32, 3), dtype=np.uint8)
        gradient[:, :, 1] = np.linspace(90, 170, 32, dtype=np.uint8)[None, :]
        gradient[:, :, 0] = 25
        gradient[:, :, 2] = 35
        image = Image.fromarray(gradient, "RGB")
        result, _ = remove_by_advanced_color_key(image, (ColorSample((25, 90, 35)), ColorSample((25, 170, 35))), ColorKeyConfig(edge_softness=1.0))
        try:
            alpha = np.asarray(result.getchannel("A"), dtype=np.uint8)
            self.assertTrue(np.all((alpha >= 0) & (alpha <= 255)))
            self.assertLess(int(alpha.mean()), 100)
        finally:
            image.close()
            result.close()

    def test_isolated_green_component_is_not_connected_background(self) -> None:
        probability = np.ones((7, 7), dtype=np.float32)
        edges = np.zeros((7, 7), dtype=bool)
        edges[2:5, 2] = True
        edges[2:5, 4] = True
        edges[2, 2:5] = True
        edges[4, 2:5] = True
        connected = connected_background(probability, edges, (), ColorKeyConfig())
        self.assertFalse(connected[3, 3])
        self.assertTrue(connected[0, 0])

    def test_connected_fill_does_not_cross_edge_barrier(self) -> None:
        probability = np.ones((9, 9), dtype=np.float32)
        edges = np.zeros((9, 9), dtype=bool)
        edges[:, 4] = True
        connected = connected_background(probability, edges, (), ColorKeyConfig())
        self.assertFalse(connected[4, 4])
        self.assertTrue(connected[4, 0])

    def test_spill_suppression_keeps_opaque_foreground_colour(self) -> None:
        rgb = np.array([[[20, 220, 30], [20, 220, 30]]], dtype=np.uint8)
        alpha = np.array([[255, 100]], dtype=np.uint8)
        output = suppress_green_spill(rgb, alpha, 1.0)
        self.assertTrue(np.array_equal(output[0, 0], rgb[0, 0]))
        self.assertLess(output[0, 1, 1], rgb[0, 1, 1])

    def test_preview_mapping_is_clamped_and_correct(self) -> None:
        self.assertEqual((500, 250), preview_to_original((100, 50), (200, 100), (1000, 500)))
        self.assertEqual((999, 499), preview_to_original((999, 999), (200, 100), (1000, 500)))


class ManualMaskTests(unittest.TestCase):
    def test_keep_remove_and_undo_redo_are_compact_commands(self) -> None:
        editor = ManualMaskEditor(max_history=20)
        editor.add_stroke(MaskStroke(((5, 5),), 2, "remove"))
        editor.add_stroke(MaskStroke(((10, 10),), 2, "keep"))
        alpha = apply_manual_strokes(np.full((16, 16), 128, dtype=np.uint8), editor.strokes)
        self.assertEqual(0, alpha[5, 5])
        self.assertEqual(255, alpha[10, 10])
        self.assertTrue(editor.undo())
        alpha = apply_manual_strokes(np.full((16, 16), 128, dtype=np.uint8), editor.strokes)
        self.assertEqual(128, alpha[10, 10])
        self.assertTrue(editor.redo())
        self.assertEqual(2, len(editor.strokes))


if __name__ == "__main__":
    unittest.main()
