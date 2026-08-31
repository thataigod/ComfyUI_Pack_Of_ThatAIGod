"""Tests for the Camera node (``Camera.py``)."""

import json
import math
import unittest

from _camera_core import DEFAULT_CONFIG_JSON
from Camera import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, Camera


class TestInputTypes(unittest.TestCase):
    def test_required_inputs(self):
        schema = Camera.INPUT_TYPES()
        required = schema["required"]
        self.assertIn("Camera Config", required)
        self.assertIn("Width", required)
        self.assertIn("Height", required)
        self.assertIn("Seed", required)
        self.assertIn("Wildcard Mode", required)

    def test_width_height_limits(self):
        schema = Camera.INPUT_TYPES()
        width = schema["required"]["Width"]
        self.assertEqual(width[0], "INT")
        self.assertEqual(width[1]["default"], 1024)
        self.assertEqual(width[1]["min"], 64)
        self.assertEqual(width[1]["max"], 16384)
        self.assertEqual(width[1]["step"], 8)

    def test_seed_range(self):
        schema = Camera.INPUT_TYPES()
        seed = schema["required"]["Seed"]
        self.assertEqual(seed[1]["default"], 0)
        self.assertEqual(seed[1]["min"], 0)
        self.assertEqual(seed[1]["max"], 0xFFFFFFFFFFFFFFFF)
        self.assertTrue(seed[1]["control_after_generate"])

    def test_wildcard_modes(self):
        schema = Camera.INPUT_TYPES()
        modes = schema["required"]["Wildcard Mode"][0]
        self.assertEqual(
            modes,
            ["Deterministic (Seed)", "Full Auto", "Random (No Repeat)"],
        )
        self.assertEqual(schema["required"]["Wildcard Mode"][1]["default"], "Deterministic (Seed)")

    def test_default_config_is_valid(self):
        parsed = json.loads(DEFAULT_CONFIG_JSON)
        self.assertIn("sizes", parsed)
        self.assertIn("tilts", parsed)

    def test_camera_config_is_last_widget(self):
        schema = Camera.INPUT_TYPES()
        keys = list(schema["required"].keys())
        self.assertEqual(keys[-1], "Camera Config")
        self.assertNotEqual(keys[0], "Camera Config")


class TestIsChanged(unittest.TestCase):
    def test_no_repeat_forces_change(self):
        self.assertTrue(math.isnan(Camera.IS_CHANGED(**{"Wildcard Mode": "Random (No Repeat)"})))

    def test_deterministic_is_stable_tuple(self):
        changed = Camera.IS_CHANGED(**{"Seed": 5, "Wildcard Mode": "Deterministic (Seed)", "Camera Config": "{}"})
        self.assertEqual(changed, (5, "Deterministic (Seed)", "{}", 1024, 1024))

    def test_deterministic_includes_dimensions(self):
        base = Camera.IS_CHANGED(**{"Seed": 5, "Wildcard Mode": "Deterministic (Seed)", "Camera Config": "{}"})
        changed = Camera.IS_CHANGED(
            **{"Seed": 5, "Wildcard Mode": "Deterministic (Seed)", "Camera Config": "{}", "Width": 768, "Height": 1152}
        )
        self.assertNotEqual(base, changed)
        self.assertEqual(changed, (5, "Deterministic (Seed)", "{}", 768, 1152))

    def test_dimensions_clamped_in_is_changed(self):
        # Outside-range values are clamped to [64, 16384] just like shoot() does
        changed = Camera.IS_CHANGED(**{"Width": -5, "Height": 10_000_000})
        self.assertEqual(changed[3], 64)
        self.assertEqual(changed[4], 16384)

    def test_missing_mode_uses_default(self):
        changed = Camera.IS_CHANGED()
        self.assertIsInstance(changed, tuple)


class TestShoot(unittest.TestCase):
    def test_result_shape(self):
        node = Camera()
        out = node.shoot()
        self.assertEqual(len(out["result"]), 5)
        description, keywords, camera_obj, camera_json, regions = out["result"]
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 60)
        self.assertIsInstance(keywords, str)
        self.assertIsInstance(camera_obj, dict)
        self.assertEqual(json.loads(camera_json), camera_obj)
        self.assertIsInstance(regions, str)

    def test_ui_payload(self):
        node = Camera()
        out = node.shoot()
        ui = out["ui"]
        self.assertEqual(ui["text"][0].count("\n"), 5)
        self.assertEqual(len(ui["description"][0]), len(out["result"][0]))
        self.assertEqual(len(ui["keywords"][0]), len(out["result"][1]))
        self.assertEqual(len(ui["regions"][0]), len(out["result"][4]))
        self.assertEqual(ui["width"][0], 1024)
        self.assertEqual(ui["height"][0], 1024)

    def test_deterministic_same_inputs(self):
        node = Camera()
        kwargs = {
            "Camera Config": DEFAULT_CONFIG_JSON,
            "Width": 896,
            "Height": 1152,
            "Seed": 17,
            "Wildcard Mode": "Deterministic (Seed)",
        }
        self.assertEqual(node.shoot(**kwargs), node.shoot(**kwargs))

    def test_dimensions_clamped(self):
        node = Camera()
        out = node.shoot(Width=-5, Height=10_000_000)
        self.assertEqual(out["ui"]["width"][0], 64)
        self.assertEqual(out["ui"]["height"][0], 16384)

    def test_shot_region_list_matches_regions_output(self):
        node = Camera()
        out = node.shoot(Seed=3)
        self.assertEqual(out["result"][4], ", ".join(out["result"][2]["regions"]))

    def test_no_repeat_mode_runs(self):
        node = Camera()
        out = node.shoot(**{"Wildcard Mode": "Random (No Repeat)", "Seed": 6})
        self.assertEqual(len(out["result"]), 5)

    def test_full_auto_mode_runs(self):
        node = Camera()
        out = node.shoot(**{"Wildcard Mode": "Full Auto", "Seed": 6})
        self.assertGreater(len(out["result"][0]), 60)


class TestMappings(unittest.TestCase):
    def test_mappings_contain_camera(self):
        self.assertIs(NODE_CLASS_MAPPINGS["Camera"], Camera)
        self.assertEqual(NODE_DISPLAY_NAME_MAPPINGS["Camera"], "Camera")


if __name__ == "__main__":
    unittest.main()
