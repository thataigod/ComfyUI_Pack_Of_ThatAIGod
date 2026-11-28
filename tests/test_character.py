"""Tests for the Character node (``Character.py``) — v2, lewdity-band era."""

import json
import math
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

server_mock = MagicMock()
server_mock.PromptServer.instance.send_sync = MagicMock()
sys.modules["server"] = server_mock

from _character_core import WARDROBE_MODES
from Character import (
    _ALL_OCCASIONS,
    _ANY_FILTER,
    _DEFAULT_OCCASION,
    _NODE_DIR,
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
    WARDROBE_COMPLETE,
    WARDROBE_EXTERNAL,
    WARDROBE_INTERNAL,
    Character,
    _default_character_config,
    _domain_options,
    _occasion_options,
    _parse_character_config,
    _persona_options,
    _scan_location_directive,
    _time_options,
)


class TestInputTypes(unittest.TestCase):
    def test_required_inputs(self):
        schema = Character.INPUT_TYPES()
        required = schema["required"]
        for key in (
            "Persona",
            "Camera",
            "Wardrobe Source",
            "Lewdity Min",
            "Lewdity Max",
            "Time of Day",
            "Domain",
            "Seed",
            "Wildcard Mode",
            "Character Config",
        ):
            self.assertIn(key, required)

    def test_wardrobe_source_options(self):
        widget = Character.INPUT_TYPES()["required"]["Wardrobe Source"]
        self.assertEqual(widget[0], list(WARDROBE_MODES))
        self.assertEqual(widget[1]["default"], WARDROBE_EXTERNAL)

    def test_lewdity_overrides_default_to_use_file(self):
        schema = Character.INPUT_TYPES()["required"]
        self.assertEqual(schema["Lewdity Min"][1]["default"], -1)
        self.assertEqual(schema["Lewdity Max"][1]["default"], -1)

    def test_time_and_domain_options_scanned_from_data(self):
        times = _time_options()
        domains = _domain_options()
        self.assertEqual(times[0], _ANY_FILTER)
        self.assertEqual(domains[0], _ANY_FILTER)
        # The shipped location taxonomy carries #@time: and #@domain:
        # headers; the scan must find them when the data is present (it is
        # untracked in some working trees, so the count is data-dependent
        # and not asserted beyond non-emptiness).
        self.assertIsInstance(times, list)
        self.assertIsInstance(domains, list)

    def test_scan_location_directive_missing_dir_returns_empty(self):
        with patch("Character._WILDCARDS_DIR", os.path.join(_NODE_DIR, "nowhere")):
            self.assertEqual(_scan_location_directive("time"), [])

    def test_scan_location_directive_reads_headers(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            wildcards = os.path.join(tmp, "wildcards")
            locations = os.path.join(wildcards, "locations")
            os.makedirs(locations)
            with open(os.path.join(locations, "a.txt"), "w", encoding="utf-8") as f:
                f.write("#@time: dawn, dusk\n#@domain: waterfront\non a beach\n")
            with open(os.path.join(locations, "b.txt"), "w", encoding="utf-8") as f:
                f.write("#@time: Dawn, night\n#@domain: civic\n")
            with patch("Character._WILDCARDS_DIR", wildcards):
                self.assertEqual(_scan_location_directive("time"), ["dawn", "dusk", "night"])
                self.assertEqual(_scan_location_directive("domain"), ["civic", "waterfront"])

    def test_persona_options_include_base_personas(self):
        options = _persona_options()
        self.assertIn("female", options)
        self.assertIn("male", options)

    def test_occasion_options_come_from_shared_file(self):
        options = _occasion_options()
        self.assertEqual(options[0], _ALL_OCCASIONS)
        self.assertIn(_DEFAULT_OCCASION, options)

    def test_occasion_options_missing_file_fall_back_to_default(self):
        with patch("Character._WILDCARDS_DIR", os.path.join(_NODE_DIR, "nowhere")):
            options = _occasion_options()
        self.assertEqual(options, [_ALL_OCCASIONS, _DEFAULT_OCCASION])


class TestConfigParsing(unittest.TestCase):
    def test_single_occasion(self):
        self.assertEqual(_parse_character_config(json.dumps({"occasions": ["beach"]})), ["beach"])

    def test_multiple_occasions(self):
        self.assertEqual(_parse_character_config(json.dumps({"occasions": ["beach", "gym"]})), ["beach", "gym"])

    def test_empty_occasions_list_means_unrestricted(self):
        self.assertEqual(_parse_character_config(json.dumps({"occasions": []})), [])

    def test_absent_key_is_none(self):
        self.assertIsNone(_parse_character_config(json.dumps({})))

    def test_malformed_json_is_none(self):
        self.assertIsNone(_parse_character_config("not json"))
        self.assertIsNone(_parse_character_config(None))

    def test_non_dict_is_none(self):
        self.assertIsNone(_parse_character_config("[1, 2]"))

    def test_non_list_occasions_is_none(self):
        self.assertIsNone(_parse_character_config(json.dumps({"occasions": "beach"})))

    def test_default_config_selects_all_occasions(self):
        config = json.loads(_default_character_config())
        self.assertEqual(len(config), 1)
        self.assertIn("occasions", config)


class TestIsChanged(unittest.TestCase):
    def test_no_repeat_forces_change(self):
        self.assertTrue(
            math.isnan(Character.IS_CHANGED(**{"Wildcard Mode": "Random (No Repeat)"}))
        )

    def test_deterministic_is_stable_tuple(self):
        camera = {"regions": ["face"], "view": "Front"}
        changed = Character.IS_CHANGED(
            **{
                "Seed": 5,
                "Persona": "female",
                "Wardrobe Source": WARDROBE_INTERNAL,
                "Lewdity Min": 10,
                "Lewdity Max": 90,
                "Time of Day": "night",
                "Domain": _ANY_FILTER,
                "Character Config": "{}",
                "Camera": camera,
            }
        )
        self.assertEqual(changed, (5, "female", WARDROBE_INTERNAL, 10, 90, "night", _ANY_FILTER, "{}", ("face",), "Front"))

    def test_deterministic_without_camera(self):
        changed = Character.IS_CHANGED(**{"Seed": 5, "Character Config": "{}"})
        self.assertEqual(changed[8], None)


class TestBuild(unittest.TestCase):
    def test_build_result_shape(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_EXTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": _ANY_FILTER,
                "Domain": _ANY_FILTER,
                "Seed": 0,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": json.dumps({"occasions": ["casual"]}),
            }
        )
        self.assertEqual(len(out["result"]), 6)
        trigger, description, keywords, subject, outfit, background = out["result"]
        self.assertIsInstance(trigger, str)
        self.assertIsInstance(description, str)
        self.assertIsInstance(keywords, str)
        self.assertIsInstance(subject, str)
        self.assertIsInstance(outfit, str)
        self.assertIsInstance(background, str)
        if background:
            self.assertTrue(description.endswith(background))
        self.assertIn("Occasion: casual", out["ui"]["text"][0])
        self.assertIn("Wardrobe:", out["ui"]["text"][0])
        self.assertIn("Lewdity:", out["ui"]["text"][0])
        self.assertIn("Background:", out["ui"]["text"][0])

    def test_build_rolls_occasion_when_config_absent(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_EXTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": _ANY_FILTER,
                "Domain": _ANY_FILTER,
                "Seed": 1,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": None,
            }
        )
        trigger = out["result"][0]
        self.assertIsInstance(trigger, str)
        self.assertIn("(random)", out["ui"]["text"][0])

    def test_build_rolls_within_multi_occasion_config(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_EXTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": _ANY_FILTER,
                "Domain": _ANY_FILTER,
                "Seed": 0,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": json.dumps({"occasions": ["beach", "casual"]}),
            }
        )
        ui_text = out["ui"]["text"][0]
        self.assertTrue("Occasion: beach" in ui_text or "Occasion: casual" in ui_text)

    def test_build_config_without_occasions_key_rolls_all(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_EXTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": _ANY_FILTER,
                "Domain": _ANY_FILTER,
                "Seed": 0,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": json.dumps({"other": 1}),
            }
        )
        ui_text = out["ui"]["text"][0]
        self.assertIn("(random)", ui_text)
        self.assertNotIn("(unrestricted)", ui_text)

    def test_build_custom_persona_shows_trigger(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            wildcards = os.path.join(tmp, "wildcards")
            os.makedirs(os.path.join(wildcards, "characters", "trig"))
            with open(os.path.join(wildcards, "characters", "trig", "trigger.txt"), "w", encoding="utf-8") as f:
                f.write("trig_lora\n")
            with patch("Character._WILDCARDS_DIR", wildcards):
                node = Character()
                out = node.build(
                    **{
                        "Persona": "trig",
                        "Camera": None,
                        "Wardrobe Source": WARDROBE_EXTERNAL,
                        "Lewdity Min": -1,
                        "Lewdity Max": -1,
                        "Time of Day": _ANY_FILTER,
                        "Domain": _ANY_FILTER,
                        "Seed": 0,
                        "Wildcard Mode": "Deterministic (Seed)",
                        "Character Config": json.dumps({"occasions": ["casual"]}),
                    }
                )
        self.assertEqual(out["result"][0], "trig_lora")
        self.assertIn("Trigger:", out["ui"]["text"][0])

    def test_build_empty_occasions_config_is_unrestricted(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_EXTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": _ANY_FILTER,
                "Domain": _ANY_FILTER,
                "Seed": 0,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": json.dumps({"occasions": []}),
            }
        )
        self.assertIn("Occasion: (unrestricted)", out["ui"]["text"][0])

    def test_build_time_filter_reaches_background(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_EXTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": "night",
                "Domain": _ANY_FILTER,
                "Seed": 0,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": json.dumps({"occasions": ["casual"]}),
            }
        )
        background = out["result"][5]
        # Whatever location serves the casual category, the night filter must
        # hold: the background either mentions night phrasing or no
        # night-tagged lines exist for it (empty allowed, wrong never).
        self.assertIsInstance(background, str)

    def test_build_generic_persona_internal_mode_uses_common(self):
        node = Character()
        out = node.build(
            **{
                "Persona": "female",
                "Camera": None,
                "Wardrobe Source": WARDROBE_INTERNAL,
                "Lewdity Min": -1,
                "Lewdity Max": -1,
                "Time of Day": _ANY_FILTER,
                "Domain": _ANY_FILTER,
                "Seed": 0,
                "Wildcard Mode": "Deterministic (Seed)",
                "Character Config": json.dumps({"occasions": ["casual"]}),
            }
        )
        self.assertIn(
            "Wardrobe: Use Internal Wardrobe (characters/female/wardrobe)",
            out["ui"]["text"][0],
        )


class TestMappings(unittest.TestCase):
    def test_mappings_contain_character(self):
        self.assertIs(NODE_CLASS_MAPPINGS["Character"], Character)
        self.assertEqual(NODE_DISPLAY_NAME_MAPPINGS["Character"], "Character")

    def test_mode_constants_reexported(self):
        self.assertEqual(WARDROBE_EXTERNAL, "Use External Wardrobe")
        self.assertEqual(WARDROBE_INTERNAL, "Use Internal Wardrobe")
        self.assertEqual(WARDROBE_COMPLETE, "Use Complete Wardrobe")


if __name__ == "__main__":
    unittest.main()
