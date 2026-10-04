import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

comfy_mock = types.ModuleType("comfy")
comfy_mock.utils = types.ModuleType("comfy.utils")
comfy_mock.utils.common_upscale = None
sys.modules["comfy"] = comfy_mock
sys.modules["comfy.utils"] = comfy_mock.utils

import unittest

import torch

from Upscale_By_Max_Side import (
    MAX_MAX_SIDE,
    MAX_TOTAL_PIXELS,
    MIN_MAX_SIDE,
    MIN_TOTAL_PIXELS,
    _scale_dimensions,
)


class TestUpscaleByMaxSide(unittest.TestCase):
    def setUp(self):
        import comfy.utils

        self.original_upscale = comfy.utils.common_upscale
        comfy.utils.common_upscale = lambda samples, w, h, method, crop: torch.nn.functional.interpolate(
            samples, size=(h, w), mode="bilinear"
        )
        from Upscale_By_Max_Side import UpscaleByMaxSide

        self.node = UpscaleByMaxSide()

    def tearDown(self):
        import comfy.utils

        comfy.utils.common_upscale = self.original_upscale

    def _make_image(self, h, w):
        return torch.zeros((1, h, w, 3))

    def test_upscale_landscape(self):
        img = self._make_image(512, 1024)
        result = self.node.upscale(**{"Image": img, "Target": 1024, "Divisibility": 8, "Method": "bilinear"})
        _, w, h = result[0].shape[1], result[1], result[2]
        self.assertLessEqual(w, 1024)
        self.assertLessEqual(h, 1024)

    def test_upscale_portrait(self):
        img = self._make_image(1024, 512)
        result = self.node.upscale(**{"Image": img, "Target": 1024, "Divisibility": 8, "Method": "bilinear"})
        _, w, h = result[0].shape[1], result[1], result[2]
        self.assertLessEqual(w, 1024)
        self.assertLessEqual(h, 1024)

    def test_dimensions_divisible_by_8(self):
        img = self._make_image(600, 800)
        result = self.node.upscale(**{"Image": img, "Target": 1024, "Divisibility": 8, "Method": "bilinear"})
        w, h = result[1], result[2]
        self.assertEqual(w % 8, 0)
        self.assertEqual(h % 8, 0)

    def test_min_dimension_not_zero(self):
        img = self._make_image(10, 2000)
        result = self.node.upscale(**{"Image": img, "Target": 64, "Divisibility": 8, "Method": "bilinear"})
        w, h = result[1], result[2]
        self.assertGreaterEqual(w, 8)
        self.assertGreaterEqual(h, 8)

    def test_aspect_ratio_preserved(self):
        img = self._make_image(400, 800)
        result = self.node.upscale(**{"Image": img, "Target": 1024, "Divisibility": 1, "Method": "bilinear"})
        _, w, h = result[0].shape[1], result[1], result[2]
        input_ratio = 800 / 400
        output_ratio = w / h
        self.assertAlmostEqual(input_ratio, output_ratio, delta=0.05)

    def test_batch_dimension_preserved(self):
        img = torch.zeros((4, 256, 512, 3))
        result = self.node.upscale(**{"Image": img, "Target": 512, "Divisibility": 8, "Method": "bilinear"})
        self.assertEqual(result[0].shape[0], 4)

    def test_channel_count_preserved(self):
        img = self._make_image(256, 512)
        result = self.node.upscale(**{"Image": img, "Target": 512, "Divisibility": 8, "Method": "bilinear"})
        self.assertEqual(result[0].shape[3], 3)

    def test_missing_image_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.node.upscale(**{"Target": 1024, "Divisibility": 8, "Method": "bilinear"})

    def test_input_types_returns_dict(self):
        from Upscale_By_Max_Side import UpscaleByMaxSide

        result = UpscaleByMaxSide.INPUT_TYPES()
        self.assertIn("required", result)
        self.assertIn("Image", result["required"])

    def test_has_description(self):
        from Upscale_By_Max_Side import UpscaleByMaxSide

        self.assertTrue(hasattr(UpscaleByMaxSide, "DESCRIPTION"))
        self.assertIsInstance(UpscaleByMaxSide.DESCRIPTION, str)

    def test_mappings_exported(self):
        from Upscale_By_Max_Side import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

        self.assertIn("UpscaleByMaxSide", NODE_CLASS_MAPPINGS)
        self.assertIn("UpscaleByMaxSide", NODE_DISPLAY_NAME_MAPPINGS)

    def test_center_cropping_divisibility_adjusts_dimensions(self):
        img = torch.zeros((1, 500, 700, 3))
        result = self.node.upscale(**{"Image": img, "Target": 1024, "Divisibility": 64, "Method": "bilinear"})
        w, h = result[1], result[2]
        self.assertEqual(w % 64, 0)
        self.assertEqual(h % 64, 0)

    # --- Limit By modes (integration through upscale) ---

    def test_min_side_landscape(self):
        img = self._make_image(512, 1024)  # ratio 2
        result = self.node.upscale(
            **{"Image": img, "Limit By": "Min Side", "Target": 1024, "Divisibility": 8, "Method": "bilinear"}
        )
        w, h = result[1], result[2]
        self.assertEqual(h, 1024)
        self.assertAlmostEqual(w / h, 2.0, delta=0.05)

    def test_min_side_portrait(self):
        img = self._make_image(1024, 512)  # ratio 0.5
        result = self.node.upscale(
            **{"Image": img, "Limit By": "Min Side", "Target": 512, "Divisibility": 8, "Method": "bilinear"}
        )
        w, h = result[1], result[2]
        self.assertEqual(w, 512)
        self.assertEqual(h, 1024)

    def test_total_pixels_square(self):
        img = self._make_image(512, 512)
        result = self.node.upscale(
            **{"Image": img, "Limit By": "Total Pixels", "Target": 1_000_000, "Divisibility": 8, "Method": "bilinear"}
        )
        w, h = result[1], result[2]
        self.assertEqual(w, h)
        self.assertAlmostEqual(w * h, 1_000_000, delta=30_000)

    # --- _scale_dimensions unit tests ---

    def test_scale_dimensions_max_side_landscape(self):
        self.assertEqual(_scale_dimensions("Max Side", 1024, 2.0), (1024, 512))

    def test_scale_dimensions_max_side_portrait(self):
        self.assertEqual(_scale_dimensions("Max Side", 1024, 0.5), (512, 1024))

    def test_scale_dimensions_min_side_landscape(self):
        self.assertEqual(_scale_dimensions("Min Side", 1000, 2.0), (2000, 1000))

    def test_scale_dimensions_min_side_portrait(self):
        self.assertEqual(_scale_dimensions("Min Side", 1000, 0.5), (1000, 2000))

    def test_scale_dimensions_total_pixels(self):
        w, h = _scale_dimensions("Total Pixels", 1_000_000, 1.0)
        self.assertEqual((w, h), (1000, 1000))

    def test_scale_dimensions_total_pixels_clamps_low(self):
        w, h = _scale_dimensions("Total Pixels", 1, 1.0)
        self.assertEqual((w, h), (MIN_MAX_SIDE, MIN_MAX_SIDE))

    def test_scale_dimensions_total_pixels_clamps_high(self):
        w, h = _scale_dimensions("Total Pixels", 10**15, 1.0)
        self.assertEqual((w, h), (MAX_MAX_SIDE, MAX_MAX_SIDE))

    def test_scale_dimensions_side_clamps(self):
        self.assertEqual(_scale_dimensions("Max Side", 1, 1.0), (MIN_MAX_SIDE, MIN_MAX_SIDE))
        self.assertEqual(_scale_dimensions("Max Side", 10**9, 1.0), (MAX_MAX_SIDE, MAX_MAX_SIDE))

    # --- Schema / config ---

    def test_input_types_offer_limit_by_and_size_config(self):
        from Upscale_By_Max_Side import UpscaleByMaxSide

        schema = UpscaleByMaxSide.INPUT_TYPES()["required"]
        self.assertEqual(list(schema["Limit By"][0]), ["Max Side", "Min Side", "Total Pixels"])
        self.assertIn("Size Config", schema)
        self.assertIn("Target", schema)

    def test_default_size_config_json(self):
        import json

        from Upscale_By_Max_Side import _DEFAULT_SIZE_CONFIG_JSON

        cfg = json.loads(_DEFAULT_SIZE_CONFIG_JSON)
        self.assertEqual(cfg["size_max"], 1024)
        self.assertEqual(cfg["size_min"], 1024)
        self.assertEqual(cfg["size_total"], 1_000_000)

    def test_total_pixel_constants(self):
        self.assertEqual(MIN_TOTAL_PIXELS, MIN_MAX_SIDE * MIN_MAX_SIDE)
        self.assertEqual(MAX_TOTAL_PIXELS, MAX_MAX_SIDE * MAX_MAX_SIDE)


if __name__ == "__main__":
    unittest.main()
