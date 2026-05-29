import sys
import os
import types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock comfy module before any real imports — it's not available outside ComfyUI
comfy_mock = types.ModuleType('comfy')
comfy_mock.utils = types.ModuleType('comfy.utils')
comfy_mock.utils.common_upscale = None  # will be set in setUp
sys.modules['comfy'] = comfy_mock
sys.modules['comfy.utils'] = comfy_mock.utils

import unittest
import torch


class TestUpscaleByMaxSide(unittest.TestCase):
    def setUp(self):
        import comfy.utils
        self.original_upscale = comfy.utils.common_upscale
        comfy.utils.common_upscale = lambda samples, w, h, method, crop: torch.nn.functional.interpolate(samples, size=(h, w), mode="bilinear")
        from Upscale_By_Max_Side import UpscaleByMaxSide
        self.node = UpscaleByMaxSide()

    def tearDown(self):
        import comfy.utils
        comfy.utils.common_upscale = self.original_upscale

    def _make_image(self, h, w):
        return torch.zeros((1, h, w, 3))

    def test_upscale_landscape(self):
        img = self._make_image(512, 1024)
        result = self.node.upscale(**{"Image": img, "Max Side": 1024, "Divisibility": 8, "Method": "bilinear"})
        _, w, h = result[0].shape[1], result[1], result[2]
        self.assertLessEqual(w, 1024)
        self.assertLessEqual(h, 1024)

    def test_upscale_portrait(self):
        img = self._make_image(1024, 512)
        result = self.node.upscale(**{"Image": img, "Max Side": 1024, "Divisibility": 8, "Method": "bilinear"})
        _, w, h = result[0].shape[1], result[1], result[2]
        self.assertLessEqual(w, 1024)
        self.assertLessEqual(h, 1024)

    def test_dimensions_divisible_by_8(self):
        img = self._make_image(600, 800)
        result = self.node.upscale(**{"Image": img, "Max Side": 1024, "Divisibility": 8, "Method": "bilinear"})
        w, h = result[1], result[2]
        self.assertEqual(w % 8, 0)
        self.assertEqual(h % 8, 0)

    def test_min_dimension_not_zero(self):
        img = self._make_image(10, 2000)
        result = self.node.upscale(**{"Image": img, "Max Side": 64, "Divisibility": 8, "Method": "bilinear"})
        w, h = result[1], result[2]
        self.assertGreaterEqual(w, 8)
        self.assertGreaterEqual(h, 8)

    def test_aspect_ratio_preserved(self):
        img = self._make_image(400, 800)
        result = self.node.upscale(**{"Image": img, "Max Side": 1024, "Divisibility": 1, "Method": "bilinear"})
        _, w, h = result[0].shape[1], result[1], result[2]
        input_ratio = 800 / 400
        output_ratio = w / h
        self.assertAlmostEqual(input_ratio, output_ratio, delta=0.05)

    def test_batch_dimension_preserved(self):
        img = torch.zeros((4, 256, 512, 3))
        result = self.node.upscale(**{"Image": img, "Max Side": 512, "Divisibility": 8, "Method": "bilinear"})
        self.assertEqual(result[0].shape[0], 4)

    def test_channel_count_preserved(self):
        img = self._make_image(256, 512)
        result = self.node.upscale(**{"Image": img, "Max Side": 512, "Divisibility": 8, "Method": "bilinear"})
        self.assertEqual(result[0].shape[3], 3)


if __name__ == "__main__":
    unittest.main()
