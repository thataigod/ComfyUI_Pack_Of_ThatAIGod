import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _utils import (
    clamp_dimension,
    compute_aspect_ratio_dimensions,
    get_logger,
    round_down_to_multiple,
    round_to_multiple,
    safe_import,
)


class TestUtils(unittest.TestCase):
    def test_get_logger_returns_named_logger(self):
        logger = get_logger()
        self.assertEqual(logger.name, "ThatAIGod")

    def test_clamp_dimension_within_range(self):
        self.assertEqual(clamp_dimension(512, 64, 16384), 512)

    def test_clamp_dimension_below_min(self):
        self.assertEqual(clamp_dimension(32, 64, 16384), 64)

    def test_clamp_dimension_above_max(self):
        self.assertEqual(clamp_dimension(20000, 64, 16384), 16384)

    def test_round_to_multiple_even(self):
        # Python 3 round uses bankers' rounding: 12.5 -> 12
        self.assertEqual(round_to_multiple(100, 8), 96)

    def test_round_to_multiple_exact(self):
        self.assertEqual(round_to_multiple(104, 8), 104)

    def test_round_to_multiple_odd(self):
        self.assertEqual(round_to_multiple(7, 8), 8)

    def test_compute_aspect_ratio_landscape(self):
        w, h = compute_aspect_ratio_dimensions(1024, 16 / 9)
        self.assertAlmostEqual(w / h, 16 / 9, delta=0.02)
        self.assertGreaterEqual(w, 64)
        self.assertGreaterEqual(h, 64)

    def test_compute_aspect_ratio_portrait(self):
        w, h = compute_aspect_ratio_dimensions(1024, 2 / 3)
        self.assertAlmostEqual(w / h, 2 / 3, delta=0.02)
        self.assertLessEqual(w, h)

    def test_compute_aspect_ratio_square(self):
        w, h = compute_aspect_ratio_dimensions(1024, 1.0)
        self.assertEqual(w, h)

    def test_compute_aspect_ratio_min_dimension(self):
        w, h = compute_aspect_ratio_dimensions(1, 1.0)
        self.assertGreaterEqual(w, 64)
        self.assertGreaterEqual(h, 64)

    def test_safe_import_nonexistent_module(self):
        result = safe_import("nonexistent_module_xyz")
        self.assertIsNone(result)

    def test_safe_import_existing_module(self):
        with patch("importlib.import_module", return_value=unittest.mock.MagicMock()):
            result = safe_import("utils")
            self.assertIsNotNone(result)

    def test_round_down_to_multiple_within_range(self):
        self.assertEqual(round_down_to_multiple(100, 8), 96)

    def test_round_down_to_multiple_exact(self):
        self.assertEqual(round_down_to_multiple(104, 8), 104)

    def test_round_down_to_multiple_below_multiple(self):
        self.assertEqual(round_down_to_multiple(5, 8), 0)

    def test_round_down_to_multiple_custom_multiple(self):
        self.assertEqual(round_down_to_multiple(50, 16), 48)

    def test_round_down_to_multiple_zero_value(self):
        self.assertEqual(round_down_to_multiple(0, 8), 0)


if __name__ == "__main__":
    unittest.main()
