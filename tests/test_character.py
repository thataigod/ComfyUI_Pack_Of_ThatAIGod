"""Tests for the Character node (``Character.py``)."""

import json
import math
import os
import tempfile
import unittest
from unittest import mock

import _character_core as core
from Camera import Camera as CameraNode
from Character import (
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
    Character,
    _occasion_options,
    _persona_options,
)


def _camera_object(regions: list[str] | None = None, view: str = "Front", face_visible: bool = True) -> dict:
    camera_node = CameraNode()
    if regions is None:
        return camera_node.shoot(Seed=3)["result"][2]
    return {
        "type": "camera",
        "regions": regions,
        "view": view,
        "face_visible": face_visible,
    }


class TestPersonaOptions(unittest.TestCase):
    def test_base_personas_always_present(self):
        options = _persona_options()
        self.assertIn("female", options)
        self.assertIn("male", options)

    def test_base_personas_lead(self):
        options = _persona_options()
        self.assertEqual(options[:2], ["female", "male"])

    def test_custom_personas_scanned(self):
        options = _persona_options()
        for persona in ("female", "male"):
            self.assertIn(persona, options)

    def test_no_duplicates(self):
        options = _persona_options()
        self.assertEqual(len(options), len(set(options)))


class TestOccasionOptions(unittest.TestCase):
    def test_unrestricted_entry_first(self):
        options = _occasion_options()
        self.assertEqual(options[0], "All (unrestricted)")

    def test_known_occasions_included(self):
        options = _occasion_options()
        for value in ("casual", "office", "beach", "formal", "intimate", "boudoir"):
            self.assertIn(value, options)

    def test_no_duplicates(self):
        options = _occasion_options()
        self.assertEqual(len(options), len(set(options)))

    def test_missing_occasions_file_falls_back(self):
        with mock.patch("Character._WILDCARDS_DIR", os.path.join(tempfile.gettempdir(), "no-such-pack-dir")):
            options = _occasion_options()
        self.assertIn("All (unrestricted)", options)

    def test_default_occasion_always_included(self):
        with mock.patch("Character._DEFAULT_OCCASION", "dojo"):
            options = _occasion_options()
        self.assertIn("dojo", options)


class TestInputTypes(unittest.TestCase):
    def test_required_inputs(self):
        schema = Character.INPUT_TYPES()
        required = schema["required"]
        self.assertIn("Persona", required)
        self.assertIn("Camera", required)
        self.assertIn("Character Config", required)
        self.assertIn("Use Common Wardrobe", required)
        self.assertIn("Use Shared Garment Modifiers", required)
        self.assertIn("Seed", required)
        self.assertIn("Wildcard Mode", required)

    def test_camera_is_typed_input(self):
        schema = Character.INPUT_TYPES()
        self.assertEqual(schema["required"]["Camera"][0], "CAMERA")

    def test_wildcard_modes(self):
        schema = Character.INPUT_TYPES()
        modes = schema["required"]["Wildcard Mode"][0]
        self.assertEqual(modes, ["Deterministic (Seed)", "Random (No Repeat)"])
        self.assertEqual(schema["required"]["Wildcard Mode"][1]["default"], "Deterministic (Seed)")

    def test_toggle_defaults(self):
        schema = Character.INPUT_TYPES()
        self.assertFalse(schema["required"]["Use Common Wardrobe"][1]["default"])
        self.assertTrue(schema["required"]["Use Shared Garment Modifiers"][1]["default"])

    def test_seed_controls_after_generate(self):
        schema = Character.INPUT_TYPES()
        seed = schema["required"]["Seed"]
        self.assertEqual(seed[0], "INT")
        self.assertTrue(seed[1]["control_after_generate"])

    def test_character_config_defaults_to_all(self):
        schema = Character.INPUT_TYPES()
        config = json.loads(schema["required"]["Character Config"][1]["default"])
        occasions = [value for value in _occasion_options() if value != "All (unrestricted)"]
        self.assertEqual(config["occasions"], occasions)
        self.assertEqual(config["states"], ["dressed", "revealing", "mishap", "slipping", "nude"])


class TestIsChanged(unittest.TestCase):
    def test_no_repeat_forces_change(self):
        self.assertTrue(math.isnan(Character.IS_CHANGED(**{"Wildcard Mode": "Random (No Repeat)"})))

    def test_deterministic_is_stable_tuple(self):
        camera = _camera_object(regions=["face", "hair"], view="Front")
        changed = Character.IS_CHANGED(
            **{
                "Seed": 5,
                "Persona": "female",
                "Occasion": "casual",
                "Wildcard Mode": "Deterministic (Seed)",
                "Use Common Wardrobe": True,
                "Use Shared Garment Modifiers": True,
                "Camera": camera,
            }
        )
        self.assertEqual(changed, (5, "female", "", "casual", True, True, ("face", "hair"), "Front"))

    def test_seed_change_updates_fingerprint(self):
        camera = _camera_object(regions=["face"])
        a = Character.IS_CHANGED(**{"Seed": 1, "Camera": camera})
        b = Character.IS_CHANGED(**{"Seed": 2, "Camera": camera})
        self.assertNotEqual(a, b)

    def test_camera_none_tolerated(self):
        changed = Character.IS_CHANGED(**{"Seed": 1})
        self.assertEqual(changed[6], None)
        self.assertEqual(changed[7], None)


class TestBuild(unittest.TestCase):
    def test_result_shape(self):
        node = Character()
        camera = _camera_object()
        out = node.build(Persona="female", Camera=camera, Occasion="casual")
        self.assertEqual(len(out["result"]), 6)
        character, character_json, description, keywords, occasion, trigger = out["result"]
        self.assertIsInstance(character, dict)
        self.assertEqual(json.loads(character_json), character)
        self.assertEqual(description, character["description"])
        self.assertEqual(keywords, character["keywords"])
        self.assertEqual(occasion, "casual")
        self.assertEqual(character["occasion"], "casual")
        self.assertEqual(trigger, character["trigger"])
        self.assertEqual(trigger, "")

    def test_trigger_pin_returns_persona_trigger(self):
        node = Character()
        camera = _camera_object()
        with tempfile.TemporaryDirectory() as tmp:
            chars = os.path.join(tmp, "characters", "tester")
            os.makedirs(chars)
            with open(os.path.join(chars, "subject_intro.txt"), "w", encoding="utf-8") as f:
                f.write("a fictional subject")
            with open(os.path.join(chars, "gender.txt"), "w", encoding="utf-8") as f:
                f.write("female")
            with open(os.path.join(chars, "trigger.txt"), "w", encoding="utf-8") as f:
                f.write("cha:pak:trigger\nan alternate trigger")
            with mock.patch("Character._WILDCARDS_DIR", tmp):
                out = node.build(Persona="tester", Camera=camera, Occasion="casual", Seed=4)
        trigger = out["result"][5]
        self.assertIn(trigger, ("cha:pak:trigger", "an alternate trigger"))
        self.assertNotIn(trigger, out["result"][2])
        self.assertNotIn(trigger, out["result"][3])
        self.assertIn(f"Trigger: {trigger}", out["ui"]["text"][0])

    def test_occasion_all_rolls_covered_random(self):
        node = Character()
        camera = _camera_object()
        options = [value for value in _occasion_options() if value != "All (unrestricted)"]
        out = node.build(Persona="female", Camera=camera, Occasion="All (unrestricted)", Seed=0)
        occasion = out["result"][4]
        self.assertIn(occasion, options)
        self.assertNotEqual(occasion, "")
        self.assertEqual(out["result"][0]["occasion"], occasion)
        self.assertIn(f"Occasion: {occasion} (random)", out["ui"]["text"][0])

    def test_camera_strips_visible_regions(self):
        node = Character()
        camera = _camera_object(regions=["face", "hair", "neck", "shoulders"], view="Front")
        character = node.build(Persona="female", Camera=camera, Occasion="casual")["result"][0]
        self.assertEqual(character["regions"], ["face", "hair", "neck", "shoulders"])
        self.assertEqual(character["attributes"]["legs"], "")
        self.assertNotEqual(character["attributes"]["face"], "")

    def test_full_length_camera_includes_legs(self):
        node = Character()
        camera = _camera_object(
            regions=["face", "hair", "neck", "shoulders", "chest", "arms", "waist", "hips", "legs", "feet"]
        )
        character = node.build(Persona="female", Camera=camera, Occasion="casual")["result"][0]
        self.assertIn("legs", character["regions"])
        self.assertNotEqual(character["attributes"]["legs"], "")

    def test_occasion_all_deterministic_same_seed(self):
        node = Character()
        camera = _camera_object()
        a = node.build(Persona="female", Camera=camera, Occasion="All (unrestricted)", Seed=3)["result"][4]
        b = node.build(Persona="female", Camera=camera, Occasion="All (unrestricted)", Seed=3)["result"][4]
        self.assertEqual(a, b)
        self.assertNotEqual(a, "")

    def test_occasion_lowercased(self):
        node = Character()
        camera = _camera_object()
        out = node.build(Persona="female", Camera=camera, Occasion="  OFFICE ")
        self.assertIsInstance(out["result"][0], dict)

    def test_camera_not_a_dict_tolerated(self):
        node = Character()
        out = node.build(Persona="female", Camera="not a camera", Occasion="casual")
        character = out["result"][0]
        self.assertEqual(character["regions"], list(core._ALL_CAMERA_REGIONS))

    def test_deterministic_same_inputs(self):
        node = Character()
        camera = _camera_object()
        kwargs = {"Persona": "female", "Camera": camera, "Occasion": "casual", "Seed": 42}
        self.assertEqual(node.build(**kwargs), node.build(**kwargs))

    def test_no_repeat_mode_runs(self):
        node = Character()
        camera = _camera_object()
        out = node.build(Persona="female", Camera=camera, Occasion="casual", **{"Wildcard Mode": "Random (No Repeat)"})
        self.assertEqual(out["result"][0]["type"], "character")

    def test_named_persona_resolves(self):
        node = Character()
        camera = _camera_object(regions=["face", "hair"], view="Front")
        out = node.build(Persona="female", Camera=camera, Occasion="casual")
        character = out["result"][0]
        self.assertEqual(character["persona"], "female")
        self.assertNotEqual(character["attributes"]["face"], "")

    def test_ui_payload(self):
        node = Character()
        camera = _camera_object()
        out = node.build(Persona="female", Camera=camera, Occasion="casual")
        ui = out["ui"]
        self.assertEqual(ui["description"][0], out["result"][2])
        self.assertEqual(ui["keywords"][0], out["result"][3])
        self.assertIn("Persona:", ui["text"][0])

    def test_mappings_registered(self):
        self.assertIn("Character", NODE_CLASS_MAPPINGS)
        self.assertIn("Character", NODE_DISPLAY_NAME_MAPPINGS)


    def test_character_config_single_occasion_fixed(self):
        node = Character()
        camera = _camera_object()
        config = json.dumps({"occasions": ["office"], "states": ["dressed"]})
        out = node.build(Persona="female", Camera=camera, **{"Character Config": config}, Seed=3)
        self.assertEqual(out["result"][4], "office")
        self.assertEqual(out["result"][0]["state"], "dressed")

    def test_character_config_subset_rolls_within(self):
        node = Character()
        camera = _camera_object()
        config = json.dumps({"occasions": ["office", "formal"], "states": ["dressed", "mishap"]})
        seen: set[str] = set()
        for seed in range(24):
            occasion = node.build(Persona="female", Camera=camera, **{"Character Config": config}, Seed=seed)["result"][4]
            self.assertIn(occasion, ("office", "formal"))
            seen.add(occasion)
        self.assertEqual(seen, {"office", "formal"})

    def test_character_config_empty_occasions_unrestricted(self):
        node = Character()
        camera = _camera_object()
        config = json.dumps({"occasions": [], "states": ["dressed"]})
        out = node.build(Persona="female", Camera=camera, **{"Character Config": config}, Seed=3)
        self.assertEqual(out["result"][4], "")

    def test_character_config_malformed_or_non_dict(self):
        node = Character()
        camera = _camera_object()
        options = [value for value in _occasion_options() if value != "All (unrestricted)"]
        for config in ("{not json", "[]", '"hello"'):
            out = node.build(Persona="female", Camera=camera, **{"Character Config": config}, Seed=3)
            self.assertIn(out["result"][4], options)

    def test_character_config_absent_occasions_rolls_covered(self):
        node = Character()
        camera = _camera_object()
        config = json.dumps({"states": ["dressed"]})
        out = node.build(Persona="female", Camera=camera, **{"Character Config": config}, Seed=3)
        self.assertNotEqual(out["result"][4], "")
        self.assertEqual(out["result"][0]["state"], "dressed")

    def test_character_config_non_list_values_default(self):
        node = Character()
        camera = _camera_object()
        config = json.dumps({"occasions": "office", "states": 3})
        out = node.build(Persona="female", Camera=camera, **{"Character Config": config}, Seed=3)
        self.assertNotEqual(out["result"][4], "")

    def test_legacy_occasion_value_still_accepted(self):
        node = Character()
        camera = _camera_object()
        out = node.build(Persona="female", Camera=camera, Occasion="  OFFICE ")
        self.assertEqual(out["result"][4], "office")


if __name__ == "__main__":
    unittest.main()
