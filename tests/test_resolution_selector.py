import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

from _utils import DEFAULT_MIN_DIMENSION
from Resolution_Selector import (
    _ALL_LABELS,
    _LANDSCAPE_LABELS,
    _PORTRAIT_LABELS,
    ResolutionSelector,
)


def _cfg(ratios=None, custom_ratio=1.0, custom_enabled=False):
    return json.dumps(
        {
            "ratios": ratios if ratios is not None else _ALL_LABELS,
            "custom_ratio": custom_ratio,
            "custom_enabled": custom_enabled,
        }
    )


class TestResolutionSelector(unittest.TestCase):
    def setUp(self):
        self.node = ResolutionSelector()

    # --- Max Side mode ---

    def test_max_side_square_produces_equal_dimensions(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertEqual(w, h)

    def test_max_side_portrait_2_3(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Portrait 2:3 (Classic)"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertAlmostEqual(w / h, 2 / 3, delta=0.02)
        self.assertLessEqual(w, h)

    def test_max_side_landscape_16_9(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Landscape 16:9 (HD)"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertAlmostEqual(w / h, 16 / 9, delta=0.02)
        self.assertGreaterEqual(w, h)

    # --- Min Side mode ---

    def test_min_side_square_produces_equal_dimensions(self):
        result = self.node.calculate(
            **{
                "Limit By": "Min Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertEqual(w, h)
        self.assertEqual(w, 1024)

    def test_min_side_landscape_min_is_height(self):
        result = self.node.calculate(
            **{
                "Limit By": "Min Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Landscape 16:9 (HD)"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertEqual(h, 1024)
        self.assertGreater(w, h)

    def test_min_side_portrait_min_is_width(self):
        result = self.node.calculate(
            **{
                "Limit By": "Min Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Portrait 2:3 (Classic)"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertEqual(w, 1024)
        self.assertGreater(h, w)

    # --- Multi-select ---

    def test_multi_select_picks_one_randomly(self):
        labels = ["Square 1:1", "Landscape 16:9 (HD)", "Portrait 2:3 (Classic)"]
        results = set()
        for s in range(50):
            result = self.node.calculate(
                **{
                    "Limit By": "Max Side",
                    "Pixels": 1024,
                    "Scale Factor": 1.0,
                    "Aspect Ratio Config": _cfg(labels),
                    "Custom W:H Ratio": 1.0,
                    "seed": s,
                }
            )
            w = result["result"][0]
            h = result["result"][1]
            kw = result["result"][5]
            # Each seed produces deterministic result
            results.add((w, h, kw))
        self.assertGreater(len(results), 1)

    def test_multi_select_with_portraits_only(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(_PORTRAIT_LABELS),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertLessEqual(w, h)

    def test_multi_select_with_landscapes_only(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(_LANDSCAPE_LABELS),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertGreaterEqual(w, h)

    # --- Custom W:H ratio ---

    def test_custom_ratio_is_used_when_enabled(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg([], custom_ratio=2.0, custom_enabled=True),
                "Custom W:H Ratio": 2.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertAlmostEqual(w / h, 2.0, delta=0.02)

    def test_custom_ratio_keyword_generated(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg([], custom_ratio=0.75, custom_enabled=True),
                "Custom W:H Ratio": 0.75,
                "seed": 0,
            }
        )
        kw = result["result"][5]
        self.assertIn("Custom 0.75", kw)

    def test_custom_ratio_disabled_not_used(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Square 1:1"], custom_ratio=99.0, custom_enabled=False),
                "Custom W:H Ratio": 99.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertEqual(w, h)

    # --- Scale Factor ---

    def test_scaled_dimensions_larger_than_base(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 2.0,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        base_w = result["result"][0]
        scaled_w = result["result"][2]
        self.assertGreater(scaled_w, base_w)

    def test_scaled_dimensions_rounded_to_8(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1000,
                "Scale Factor": 1.37,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        sw = result["result"][2]
        sh = result["result"][3]
        self.assertEqual(sw % 8, 0)
        self.assertEqual(sh % 8, 0)

    # --- Dimension clamping ---

    def test_dimensions_at_least_64(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1,
                "Scale Factor": 0.1,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertGreaterEqual(w, DEFAULT_MIN_DIMENSION)
        self.assertGreaterEqual(h, DEFAULT_MIN_DIMENSION)

    def test_dimensions_clamped_to_16384(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 99999,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertLessEqual(w, 16384)
        self.assertLessEqual(h, 16384)

    # --- Output fields ---

    def test_keywords_returned_for_known_ratio(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Square 1:1"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        self.assertIn("1:1", result["result"][5])

    def test_guide_size_is_min_of_dimensions(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Portrait 2:3 (Classic)"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        guide = result["result"][6]
        self.assertEqual(guide, min(w, h))

    def test_max_size_is_max_of_dimensions(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(["Landscape 16:9 (HD)"]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        max_val = result["result"][7]
        self.assertEqual(max_val, max(w, h))

    # --- JSON config edge cases ---

    def test_invalid_json_config_falls_back_to_all(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": "not valid json",
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_empty_config_string_falls_back(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": "",
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_empty_ratios_list_falls_back_to_all(self):
        result = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg([]),
                "Custom W:H Ratio": 1.0,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    # --- Determinism ---

    def test_same_seed_same_result(self):
        r1 = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(_ALL_LABELS),
                "Custom W:H Ratio": 1.0,
                "seed": 42,
            }
        )
        r2 = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(_ALL_LABELS),
                "Custom W:H Ratio": 1.0,
                "seed": 42,
            }
        )
        self.assertEqual(r1["result"], r2["result"])

    def test_different_seed_different_result(self):
        r1 = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(_ALL_LABELS),
                "Custom W:H Ratio": 1.0,
                "seed": 1,
            }
        )
        r2 = self.node.calculate(
            **{
                "Limit By": "Max Side",
                "Pixels": 1024,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg(_ALL_LABELS),
                "Custom W:H Ratio": 1.0,
                "seed": 9999,
            }
        )
        self.assertNotEqual(r1["result"], r2["result"])

    # --- Input types ---

    def test_input_types_returns_dict(self):
        result = ResolutionSelector.INPUT_TYPES()
        self.assertIn("required", result)
        self.assertIn("Limit By", result["required"])
        self.assertIn("Pixels", result["required"])
        self.assertIn("Scale Factor", result["required"])
        self.assertIn("Aspect Ratio Config", result["required"])
        self.assertIn("seed", result["required"])

    # --- Min Side with custom ratio ---

    def test_min_side_with_custom_ratio(self):
        result = self.node.calculate(
            **{
                "Limit By": "Min Side",
                "Pixels": 512,
                "Scale Factor": 1.0,
                "Aspect Ratio Config": _cfg([], custom_ratio=1.5, custom_enabled=True),
                "Custom W:H Ratio": 1.5,
                "seed": 0,
            }
        )
        w, h = result["result"][0], result["result"][1]
        self.assertAlmostEqual(w / h, 1.5, delta=0.02)

    def test_deterministic_with_single_ratio_multi_config(self):
        for s in range(10):
            result = self.node.calculate(
                **{
                    "Limit By": "Max Side",
                    "Pixels": 1024,
                    "Scale Factor": 1.5,
                    "Aspect Ratio Config": _cfg(["Square 1:1"]),
                    "Custom W:H Ratio": 1.0,
                    "seed": s,
                }
            )
            w, h = result["result"][0], result["result"][1]
            self.assertEqual(w, h)
            scaled_w = result["result"][2]
            self.assertEqual(scaled_w % 8, 0)


if __name__ == "__main__":
    unittest.main()
