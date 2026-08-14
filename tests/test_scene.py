"""Tests for the Scene node (``Scene.py``)."""

import json
import math
import os
import re
import unittest

from _wildcard_core import WildcardResolver
from Character import Character as CharacterNode
from Character import _occasion_options
from Scene import (
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
    Scene,
    _scene_options,
    _time_options,
)

_WILDCARDS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "wildcards")


class TestSceneOptions(unittest.TestCase):
    def test_auto_location_first(self):
        schema = Scene.INPUT_TYPES()
        options = schema["required"]["Location"][0]
        self.assertEqual(options[0], "Auto")

    def test_known_scenes_included(self):
        options = _scene_options(_WILDCARDS_DIR)
        for name in (
            "beach",
            "studio",
            "ballroom",
            "rooftop",
            "library",
            "bedroom",
            "boudoir",
            "home",
            "convention_hall",
            "heritage_courtyard",
            "resort_villa",
            "street_fair",
            "city_day",
        ):
            self.assertIn(name, options)

    def test_no_duplicates(self):
        options = _scene_options(_WILDCARDS_DIR)
        self.assertEqual(len(options), len(set(options)))


class TestTimeOptions(unittest.TestCase):
    def test_all_entry_first(self):
        options = _time_options(_WILDCARDS_DIR)
        self.assertEqual(options[0], "All")

    def test_known_times_included(self):
        options = _time_options(_WILDCARDS_DIR)
        for value in ("golden hour", "night", "noon", "dusk", "dawn", "blue hour", "midnight"):
            self.assertIn(value, options)

    def test_no_duplicates(self):
        options = _time_options(_WILDCARDS_DIR)
        self.assertEqual(len(options), len(set(options)))


class TestInputTypes(unittest.TestCase):
    def test_required_inputs(self):
        schema = Scene.INPUT_TYPES()
        required = schema["required"]
        for name in ("Occasion", "Location", "Time of Day", "Use Film Look", "Seed", "Wildcard Mode"):
            self.assertIn(name, required)

    def test_removed_inputs_absent(self):
        schema = Scene.INPUT_TYPES()
        for name in ("Subject", "Use Atmosphere", "Use Lighting"):
            self.assertNotIn(name, schema["required"])
        self.assertNotIn("Camera", schema["optional"])

    def test_optional_objects(self):
        schema = Scene.INPUT_TYPES()
        optional = schema["optional"]
        self.assertEqual(optional["Character"][0], "CHARACTER")
        self.assertEqual(set(optional), {"Character"})

    def test_wildcard_modes(self):
        schema = Scene.INPUT_TYPES()
        modes = schema["required"]["Wildcard Mode"][0]
        self.assertEqual(modes, ["Deterministic (Seed)", "Random (No Repeat)"])
        self.assertEqual(schema["required"]["Wildcard Mode"][1]["default"], "Deterministic (Seed)")

    def test_film_toggle_default_on(self):
        schema = Scene.INPUT_TYPES()
        self.assertTrue(schema["required"]["Use Film Look"][1]["default"])

    def test_defaults(self):
        schema = Scene.INPUT_TYPES()
        self.assertEqual(schema["required"]["Location"][1]["default"], "Auto")
        self.assertEqual(schema["required"]["Time of Day"][1]["default"], "All")
        self.assertEqual(schema["required"]["Occasion"][0], "STRING")
        self.assertEqual(schema["required"]["Occasion"][1]["default"], "auto")

    def test_seed_controls_after_generate(self):
        schema = Scene.INPUT_TYPES()
        seed = schema["required"]["Seed"]
        self.assertEqual(seed[0], "INT")
        self.assertTrue(seed[1]["control_after_generate"])

    def test_outputs(self):
        self.assertEqual(Scene.RETURN_TYPES, ("SCENE", "STRING", "STRING", "STRING"))
        self.assertEqual(Scene.RETURN_NAMES, ("Scene", "Scene JSON", "Description", "Keywords"))


class TestIsChanged(unittest.TestCase):
    def test_no_repeat_forces_change(self):
        self.assertTrue(math.isnan(Scene.IS_CHANGED(**{"Wildcard Mode": "Random (No Repeat)"})))

    def test_deterministic_is_stable_tuple(self):
        character = {
            "type": "character",
            "outfit_category": "formal",
            "description": "the subject",
            "occasion": "formal",
            "state": "dressed",
        }
        changed = Scene.IS_CHANGED(
            **{
                "Seed": 5,
                "Occasion": "formal",
                "Location": "Auto",
                "Time of Day": "night",
                "Use Film Look": True,
                "Character": character,
            }
        )
        self.assertEqual(changed, (5, "formal", "formal", "Auto", "night", True, "formal", "dressed"))

    def test_character_occasion_change_updates_fingerprint(self):
        base = {"Seed": 1, "Location": "Auto", "Time of Day": "All"}
        a = Scene.IS_CHANGED(**{**base, "Character": {"occasion": "beach"}})
        b = Scene.IS_CHANGED(**{**base, "Character": {"occasion": "formal"}})
        self.assertNotEqual(a, b)

    def test_occasion_field_change_updates_fingerprint(self):
        base = {"Seed": 1, "Location": "Auto", "Time of Day": "All"}
        a = Scene.IS_CHANGED(**{**base, "Occasion": "auto"})
        b = Scene.IS_CHANGED(**{**base, "Occasion": "travel"})
        self.assertNotEqual(a, b)

    def test_character_state_change_updates_fingerprint(self):
        base = {"Seed": 1, "Occasion": "casual", "Location": "Auto", "Time of Day": "All"}
        a = Scene.IS_CHANGED(**{**base, "Character": {"state": "dressed"}})
        b = Scene.IS_CHANGED(**{**base, "Character": {"state": "nude"}})
        self.assertNotEqual(a, b)

    def test_character_outfit_change_updates_fingerprint(self):
        base = {"Seed": 1, "Occasion": "casual", "Location": "Auto", "Time of Day": "All"}
        a = Scene.IS_CHANGED(**{**base, "Character": {"outfit_category": "formal"}})
        b = Scene.IS_CHANGED(**{**base, "Character": {"outfit_category": "swimwear"}})
        self.assertNotEqual(a, b)

    def test_none_objects_tolerated(self):
        changed = Scene.IS_CHANGED(**{"Seed": 1})
        self.assertEqual(changed[5], True)
        self.assertEqual(changed[6], "")
        self.assertEqual(changed[7], "")


class TestCompose(unittest.TestCase):
    def test_result_shape(self):
        node = Scene()
        out = node.compose(Occasion="casual")
        self.assertEqual(len(out["result"]), 4)
        scene, scene_json, description, keywords = out["result"]
        self.assertEqual(scene["type"], "scene")
        self.assertEqual(json.loads(scene_json), scene)
        self.assertEqual(description, scene["description"])
        self.assertEqual(keywords, scene["keywords"])

    def test_occasion_explicit(self):
        node = Scene()
        out = node.compose(Occasion="  BEACH ")
        scene = out["result"][0]
        self.assertEqual(scene["occasion"], "beach")
        self.assertEqual(scene["occasion_source"], "explicit")

    def test_occasion_unrestricted(self):
        node = Scene()
        for value in ("", "All (unrestricted)"):
            scene = node.compose(Occasion=value)["result"][0]
            self.assertEqual(scene["occasion"], "")
            self.assertEqual(scene["occasion_source"], "unrestricted")

    def test_occasion_auto_uses_character(self):
        node = Scene()
        character = CharacterNode().build(Persona="female", Occasion="travel")["result"][0]
        scene = node.compose(Occasion="auto", Character=character)["result"][0]
        self.assertEqual(scene["occasion"], "travel")
        self.assertEqual(scene["occasion_source"], "character")

    def test_occasion_auto_without_character_picks_seeded_random(self):
        node = Scene()
        out = node.compose(Occasion="auto", Seed=7)
        scene = out["result"][0]
        self.assertEqual(scene["occasion_source"], "random")
        self.assertIn(scene["occasion"], _occasion_options()[1:])

    def test_occasion_info_text_shows_source(self):
        node = Scene()
        out = node.compose(Occasion="travel")
        self.assertIn("Occasion: travel", out["ui"]["text"][0])
        character = CharacterNode().build(Persona="female", Occasion="travel")["result"][0]
        out = node.compose(Occasion="auto", Character=character)
        self.assertIn("Occasion: travel (from Character)", out["ui"]["text"][0])
        out = node.compose(Occasion="")
        self.assertIn("Occasion: unrestricted", out["ui"]["text"][0])

    def test_non_dict_character_tolerated(self):
        node = Scene()
        out = node.compose(Occasion="casual", Character="nope")
        scene = out["result"][0]
        self.assertEqual(scene["state"], "")
        self.assertNotIn("nope", scene["description"])

    def test_deterministic_same_inputs(self):
        node = Scene()
        kwargs = {"Occasion": "formal", **{"Time of Day": "night"}, "Seed": 42}
        self.assertEqual(node.compose(**kwargs), node.compose(**kwargs))

    def test_no_repeat_mode_runs(self):
        node = Scene()
        out = node.compose(Occasion="casual", **{"Wildcard Mode": "Random (No Repeat)"})
        self.assertEqual(out["result"][0]["type"], "scene")

    def test_film_look_disabled(self):
        node = Scene()
        out = node.compose(Occasion="casual", **{"Use Film Look": False})
        scene = out["result"][0]
        self.assertEqual(scene["film_look"], "")
        self.assertNotIn("Style and tones", scene["description"])
        self.assertIn("Film Look: (off)", out["ui"]["text"][0])

    def test_missing_explicit_location_info_text(self):
        node = Scene()
        out = node.compose(Occasion="casual", Location="nope", **{"Time of Day": "All"})
        self.assertIn("Location: (none)", out["ui"]["text"][0])
        self.assertIn("State: (none)", out["ui"]["text"][0])
        self.assertIn("Mode: Deterministic (Seed)", out["ui"]["text"][0])

    def test_no_time_phrase_shows_none(self):
        node = Scene()
        with unittest.mock.patch("_scene_core._pick_time", return_value=""):
            out = node.compose(Occasion="casual", Location="studio", **{"Time of Day": "All"})
        self.assertIn("Time: (none)", out["ui"]["text"][0])

    def test_state_gating_with_character(self):
        character_node = CharacterNode()
        config = json.dumps({"occasions": ["intimate"], "states": ["nude"]})
        character = character_node.build(Persona="female", **{"Character Config": config})["result"][0]
        self.assertEqual(character["state"], "nude")
        node = Scene()
        out = node.compose(Occasion="auto", Character=character, Seed=3)
        scene = out["result"][0]
        self.assertEqual(scene["state"], "nude")
        self.assertIn(scene["location_key"], ("bedroom", "boudoir"))
        self.assertIn("State: nude", out["ui"]["text"][0])

    def test_dressed_character_public_scene(self):
        character_node = CharacterNode()
        config = json.dumps({"occasions": ["beach"], "states": ["dressed"]})
        character = character_node.build(Persona="female", **{"Character Config": config})["result"][0]
        node = Scene()
        scene = node.compose(Occasion="auto", Character=character, Seed=3)["result"][0]
        self.assertEqual(scene["state"], "dressed")
        self.assertEqual(scene["location_key"], "beach")

    def test_ui_payload(self):
        node = Scene()
        out = node.compose(Occasion="casual")
        ui = out["ui"]
        self.assertEqual(ui["description"][0], out["result"][2])
        self.assertEqual(ui["keywords"][0], out["result"][3])
        self.assertIn("Occasion:", ui["text"][0])
        self.assertIn("Location:", ui["text"][0])
        self.assertIn("State:", ui["text"][0])

    def test_scene_object_has_no_legacy_keys(self):
        node = Scene()
        scene = node.compose(Occasion="casual")["result"][0]
        for dropped in ("subject", "full_prompt", "atmosphere", "lighting", "camera_description"):
            self.assertNotIn(dropped, scene)
        for key in ("type", "occasion", "occasion_source", "location", "location_key", "setting", "time_of_day", "film_look", "state", "description", "keywords", "mode", "seed"):
            self.assertIn(key, scene)

    def test_mappings_registered(self):
        self.assertIn("Scene", NODE_CLASS_MAPPINGS)
        self.assertIn("Scene", NODE_DISPLAY_NAME_MAPPINGS)


class TestSceneData(unittest.TestCase):
    _BANNED_PATTERN = re.compile(
        r"\b(?:sun|sky|stars|afternoon|noon|morning|night|dawn|dusk|midnight|evening|twilight|sunrise|sunset|daylight|nightfall|sunlit|dappled)\b|golden hour|blue hour"
    )

    def test_no_light_or_time_words_in_prose(self):
        scenes_dir = os.path.join(_WILDCARDS_DIR, "scenes")
        for name in sorted(os.listdir(scenes_dir)):
            if not name.endswith(".txt"):
                continue
            with open(os.path.join(scenes_dir, name), encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    match = self._BANNED_PATTERN.search(stripped)
                    self.assertIsNone(match, f"{name}: banned word in {stripped!r}")

    def test_every_scene_has_fallback_block_and_known_times(self):
        directive = re.compile(r"^#@\s*([a-z_]+)\s*:\s*(.+?)\s*$")
        known_times = set(_time_options(_WILDCARDS_DIR)[1:])
        scenes_dir = os.path.join(_WILDCARDS_DIR, "scenes")
        for name in sorted(os.listdir(scenes_dir)):
            if not name.endswith(".txt"):
                continue
            block_has_time = False
            declared_times: set[str] = set()
            fallback = False
            with open(os.path.join(scenes_dir, name), encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    match = directive.match(stripped)
                    if match is not None:
                        if match.group(1) == "time":
                            block_has_time = True
                            declared_times.update(v.strip().lower() for v in match.group(2).split(","))
                        continue
                    if stripped.startswith("#"):
                        continue
                    if block_has_time:
                        block_has_time = False
                    else:
                        fallback = True
            if not declared_times:
                continue
            self.assertTrue(fallback, f"{name}: no time-neutral fallback block")
            self.assertLessEqual(declared_times, known_times, f"{name}: unknown time values")

    def test_no_duplicated_time_values_in_description(self):
        node = Scene()
        # The noon phrase reads "harsh midday sun"; the others carry the token.
        for location, time, token in (
            ("beach", "night", "night"),
            ("park", "afternoon", "afternoon"),
            ("city_day", "midnight", "midnight"),
            ("pool", "noon", "midday"),
        ):
            scene = node.compose(Occasion="casual", Location=location, **{"Time of Day": time}, Seed=1)["result"][0]
            self.assertIn(time, scene["keywords"])
            kw_tokens = [kw.strip() for kw in scene["keywords"].split(",") if kw.strip()]
            self.assertEqual(len(kw_tokens), len(set(kw_tokens)))
            self.assertEqual(scene["description"].lower().count(token), 1)

    def test_unexpected_explicit_time_uses_time_neutral_fallback(self):
        node = Scene()
        # bedroom/boudoir/home declare only evening blocks; a noon request on
        # the Auto path must resolve to their time-neutral fallbacks, never the
        # studio or a public scene.
        seen: set[str] = set()
        for seed in range(10):
            scene = node.compose(Occasion="intimate", Location="Auto", **{"Time of Day": "noon"}, Seed=seed)["result"][0]
            self.assertIn(scene["location_key"], ("bedroom", "boudoir", "home"))
            self.assertNotIn("velvet curtains", scene["location"])
            self.assertNotIn("duvet", scene["location"])
            seen.add(scene["location_key"])
        self.assertNotIn("studio", seen)


class TestFilmLookData(unittest.TestCase):
    _FAMILY_FILES = [
        "analog-processes.txt",
        "commercial-stocks.txt",
        "ddr-stocks.txt",
        "digital-looks.txt",
        "era-looks.txt",
        "quality.txt",
        "soviet-stocks.txt",
        "tonality-grades.txt",
    ]

    def test_deck_resolves_to_style_line(self):
        resolver = WildcardResolver(_WILDCARDS_DIR)
        line = resolver.pick_line("styles/film-look", None)
        tags = [f"__styles/film-look/{name[:-4]}__" for name in self._FAMILY_FILES]
        self.assertIn(line, tags)
        resolved = resolver.resolve(line)
        self.assertTrue(resolved.startswith("Style and tones:"))
        self.assertTrue(resolved[len("Style and tones:"):].strip())

    def test_family_files_non_empty_and_deduplicated(self):
        family_dir = os.path.join(_WILDCARDS_DIR, "styles", "film-look")
        names = sorted(f for f in os.listdir(family_dir) if f.endswith(".txt"))
        self.assertEqual(names, self._FAMILY_FILES)
        seen: set[str] = set()
        for name in names:
            with open(os.path.join(family_dir, name), encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            self.assertTrue(lines, f"{name}: empty family file")
            for line in lines:
                self.assertTrue(line.startswith("Style and tones:"), f"{name}: {line!r}")
                self.assertNotIn(line, seen, f"{name}: duplicate line")
                seen.add(line)


if __name__ == "__main__":
    unittest.main()
