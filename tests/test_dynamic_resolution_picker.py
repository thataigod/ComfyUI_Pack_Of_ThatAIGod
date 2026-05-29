import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
import random
from Dynamic_Resolution_Picker import DynamicResolution


class TestDynamicResolution(unittest.TestCase):
    def setUp(self):
        self.node = DynamicResolution()

    def test_square_1_1_ratio(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 1.5,
            "seed": 0,
        })
        self.assertEqual(result["result"][0], 1024)
        self.assertEqual(result["result"][1], 1024)

    def test_portrait_2_3_ratio(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Portrait 2:3 (Classic)",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        w, h = result["result"][0], result["result"][1]
        self.assertAlmostEqual(w / h, 2 / 3, delta=0.02)

    def test_landscape_16_9_ratio(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Landscape 16:9 (HD)",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        w, h = result["result"][0], result["result"][1]
        self.assertAlmostEqual(w / h, 16 / 9, delta=0.02)

    def test_scaled_dimensions_larger_than_base(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 2.0,
            "seed": 0,
        })
        scaled_w = result["result"][2]
        self.assertGreater(scaled_w, 1024)

    def test_min_dimension_at_least_64(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 64,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 0.1,
            "seed": 0,
        })
        w, h = result["result"][0], result["result"][1]
        self.assertGreaterEqual(w, 64)
        self.assertGreaterEqual(h, 64)

    def test_dimensions_rounded_to_8(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1000,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        w, h = result["result"][0], result["result"][1]
        self.assertEqual(w % 8, 0)
        self.assertEqual(h % 8, 0)

    def test_keywords_returned_for_known_ratio(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        self.assertIn("1:1", result["result"][5])

    def test_random_portrait_returns_portrait(self):
        for _ in range(20):
            result = self.node.calculate(**{
                "Max Side Pixels": 1024,
                "Aspect Ratio": "Random (Portrait)",
                "Scale Factor": 1.0,
                "seed": 42,
            })
            w, h = result["result"][0], result["result"][1]
            self.assertLessEqual(w, h)

    def test_random_landscape_returns_landscape(self):
        for _ in range(20):
            result = self.node.calculate(**{
                "Max Side Pixels": 1024,
                "Aspect Ratio": "Random (Landscape)",
                "Scale Factor": 1.0,
                "seed": 99,
            })
            w, h = result["result"][0], result["result"][1]
            self.assertGreaterEqual(w, h)

    def test_guide_size_is_min_of_dimensions(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Portrait 2:3 (Classic)",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        width = result["result"][0]
        height = result["result"][1]
        guide = result["result"][6]
        self.assertEqual(guide, min(width, height))

    def test_max_size_is_max_of_dimensions(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1024,
            "Aspect Ratio": "Landscape 16:9 (HD)",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        width = result["result"][0]
        height = result["result"][1]
        max_val = result["result"][7]
        self.assertEqual(max_val, max(width, height))

    def test_max_side_clamped_to_16384(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 99999,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        w, h = result["result"][0], result["result"][1]
        self.assertLessEqual(w, 16384)
        self.assertLessEqual(h, 16384)

    def test_max_side_clamped_to_64(self):
        result = self.node.calculate(**{
            "Max Side Pixels": 1,
            "Aspect Ratio": "Square 1:1",
            "Scale Factor": 1.0,
            "seed": 0,
        })
        w, h = result["result"][0], result["result"][1]
        self.assertGreaterEqual(w, 64)
        self.assertGreaterEqual(h, 64)

    def test_resolve_ratio_returns_known_label(self):
        rng = random.Random(0)
        label, ratio = self.node._resolve_ratio("Square 1:1", rng)
        self.assertEqual(label, "Square 1:1")
        self.assertEqual(ratio, 1.0)

    def test_input_types_returns_dict(self):
        result = DynamicResolution.INPUT_TYPES()
        self.assertIn("required", result)
        self.assertIn("Aspect Ratio", result["required"])

    def test_random_any_ratio(self):
        for _ in range(20):
            result = self.node.calculate(**{
                "Max Side Pixels": 1024,
                "Aspect Ratio": "Random (Any)",
                "Scale Factor": 1.0,
                "seed": 42,
            })
            w, h = result["result"][0], result["result"][1]
            self.assertGreaterEqual(w, 64)
            self.assertGreaterEqual(h, 64)

    def test_resolve_ratio_fallback_for_unknown(self):
        rng = random.Random(0)
        label, ratio = self.node._resolve_ratio("Unknown Ratio", rng)
        self.assertEqual(label, "Square 1:1")
        self.assertEqual(ratio, 1.0)


if __name__ == "__main__":
    unittest.main()
