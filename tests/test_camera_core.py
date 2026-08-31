"""Tests for the pure camera-shot engine in ``_camera_core.py``."""

import json
import random
import unittest
from typing import Any

import _camera_core as core
from _camera_core import (
    DEFAULT_CONFIG_JSON,
    DETERMINISTIC_MODE,
    FULL_AUTO_MODE,
    NO_REPEAT_MODE,
    ShotBag,
    build_shot,
    face_visible,
    parse_config,
    visible_regions,
)


class TestFaceVisible(unittest.TestCase):
    def test_top_down_never_shows_face(self):
        for view in core.VIEWS:
            self.assertFalse(face_visible("Top Down", view))

    def test_back_views_never_show_face(self):
        for angle in core.ANGLES:
            self.assertFalse(face_visible(angle, "Back"))
            self.assertFalse(face_visible(angle, "3/4 Back"))

    def test_front_facing_angles_show_face(self):
        for angle in ("Eye Level", "Low Angle", "High Angle", "Worm's Eye"):
            for view in ("Front", "3/4 Front", "Profile"):
                self.assertTrue(face_visible(angle, view))

    def test_custom_elevation_90_hides_face_via_option_space(self):
        # A custom angle based on Eye Level but with elevation 90 must hide face
        # even when its hides set is empty — mirrors build_shot logic.
        space = core._builtin_space()
        # shallow copy is safe because _builtin_space now returns a deep copy
        space["angles"]["custom-overhead"] = {
            "name": "custom-overhead",
            "elevation": 90,
            "hides": frozenset(),
            "keyword": "Custom Overhead",
            "phrases": ("shot from directly overhead",),
            "shortcuts": frozenset(),
        }
        self.assertFalse(face_visible("custom-overhead", "Front", option_space=space))
        self.assertNotIn("face", visible_regions("Full", "custom-overhead", "Front", option_space=space))


class TestVisibleRegions(unittest.TestCase):
    def test_regions_are_subset_of_size_base(self):
        for size in core.SHOT_SIZES:
            base = core._REGIONS_BY_SIZE[size]
            for angle in core.ANGLES:
                for view in core.VIEWS:
                    regions = visible_regions(size, angle, view)
                    self.assertTrue(set(regions) <= set(base))
                    self.assertEqual(regions, sorted(regions, key=base.index))

    def test_face_region_matches_face_visibility(self):
        for size in core.SHOT_SIZES:
            for angle in core.ANGLES:
                for view in core.VIEWS:
                    regions = set(visible_regions(size, angle, view))
                    self.assertEqual("face" in regions, face_visible(angle, view))

    def test_back_view_strips_front_features(self):
        for size in core.SHOT_SIZES:
            for view in ("Back", "3/4 Back"):
                regions = set(visible_regions(size, "Eye Level", view))
                self.assertFalse(regions & {"face", "chest", "breasts", "navel", "skin"})

    def test_front_view_strips_back_features(self):
        for size in core.SHOT_SIZES:
            for view in ("Front", "3/4 Front"):
                regions = set(visible_regions(size, "Eye Level", view))
                self.assertFalse(regions & {"back", "buttocks"})

    def test_profile_strips_front_and_back(self):
        for size in core.SHOT_SIZES:
            regions = set(visible_regions(size, "Eye Level", "Profile"))
            self.assertFalse(regions & {"back", "buttocks", "chest", "breasts", "navel"})

    def test_top_down_hides_face_and_front(self):
        for view in core.VIEWS:
            regions = set(visible_regions("Full", "Top Down", view))
            self.assertFalse(regions & {"face", "neck", "chest", "breasts", "navel", "skin"})
            self.assertIn("hair", regions)

    def test_worm_eye_hides_hair(self):
        for view in core.VIEWS:
            regions = set(visible_regions("Full", "Worm's Eye", view))
            self.assertNotIn("hair", regions)

    def test_extreme_close_up_strips_body(self):
        regions = set(visible_regions("Extreme Close-Up", "Eye Level", "Front"))
        self.assertEqual(regions, {"face", "hair", "neck", "skin"})

    def test_back_close_up_is_hair_and_neck_only(self):
        regions = visible_regions("Extreme Close-Up", "Eye Level", "Back")
        self.assertEqual(regions, ["hair", "neck"])

    def test_environment_only_on_long_sizes(self):
        for size in ("Long", "Extreme Long"):
            self.assertIn("environment", visible_regions(size, "Eye Level", "Front"))
        self.assertNotIn("environment", visible_regions("Full", "Eye Level", "Front"))


class TestParseConfig(unittest.TestCase):
    def test_full_default_config(self):
        parsed = parse_config(DEFAULT_CONFIG_JSON)
        self.assertEqual(parsed["sizes"], core.SHOT_SIZES)
        self.assertEqual(parsed["angles"], core.ANGLES)
        self.assertEqual(parsed["views"], core.VIEWS)
        self.assertEqual(parsed["movements"], core.MOVEMENTS)
        self.assertEqual(parsed["tilts"], core.TILTS)

    def test_restricted_config(self):
        parsed = parse_config(
            json.dumps(
                {
                    "sizes": ["Close-Up", "Full"],
                    "angles": ["Eye Level", "Bogus"],
                    "views": [],
                    "movements": "not-a-list",
                    "tilts": ["None"],
                }
            )
        )
        self.assertEqual(parsed["sizes"], ["Close-Up", "Full"])
        self.assertEqual(parsed["angles"], ["Eye Level"])
        self.assertEqual(parsed["views"], [])
        self.assertEqual(parsed["movements"], core.MOVEMENTS)
        self.assertEqual(parsed["tilts"], ["None"])

    def test_absent_axis_key_falls_back_to_full(self):
        parsed = parse_config("{}")
        self.assertEqual(parsed["sizes"], core.SHOT_SIZES)
        self.assertEqual(parsed["views"], core.VIEWS)

    def test_non_dict_json_falls_back_to_full(self):
        for config_json in ("[]", '"hello"', "42", ""):
            parsed = parse_config(config_json)
            self.assertEqual(parsed["sizes"], core.SHOT_SIZES)
            self.assertEqual(parsed["looks"], core.LOOKS)

    def test_malformed_json_falls_back_to_full(self):
        parsed = parse_config("{not valid json")
        self.assertEqual(parsed["sizes"], core.SHOT_SIZES)
        self.assertEqual(parsed["angles"], core.ANGLES)
        self.assertEqual(parsed["views"], core.VIEWS)
        self.assertEqual(parsed["movements"], core.MOVEMENTS)
        self.assertEqual(parsed["tilts"], core.TILTS)
        self.assertEqual(parsed["looks"], list(core.LOOKS))

    def test_none_falls_back_to_full(self):
        parsed = parse_config(None)
        self.assertEqual(parsed["sizes"], core.SHOT_SIZES)

    def test_non_string_items_dropped(self):
        parsed = parse_config(json.dumps({"sizes": ["Close-Up", 3, None]}))
        self.assertEqual(parsed["sizes"], ["Close-Up"])

    def test_options_order_preserved_without_duplicates(self):
        parsed = parse_config(json.dumps({"sizes": ["Full", "Close-Up", "Full"]}))
        self.assertEqual(parsed["sizes"], ["Full", "Close-Up"])

    def test_axis_product(self):
        config = parse_config(
            json.dumps(
                {
                    "sizes": ["Close-Up", "Full"],
                    "angles": ["Eye Level", "Low Angle"],
                    "views": ["Front", "Back"],
                    "movements": ["Static", "Tracking"],
                    "tilts": ["None", "Slight"],
                    "looks": ["Leica M6", "ARRI Alexa Mini"],
                }
            )
        )
        self.assertEqual(core.axis_product(config), 64)


class TestShotBag(unittest.TestCase):
    def _small_config(self):
        return {
            "sizes": ["Close-Up", "Full"],
            "angles": ["Eye Level", "Low Angle"],
            "views": ["Front", "Back"],
            "movements": ["Static", "Tracking"],
            "tilts": ["None", "Slight"],
        }

    def test_draws_unique_until_exhaustion(self):
        bag = ShotBag(9001, self._small_config())
        drawn = {tuple(sorted(bag.draw().items())) for _ in range(32)}
        self.assertEqual(len(drawn), 32)

    def test_reshuffles_after_exhaustion(self):
        bag = ShotBag(9002, self._small_config())
        for _ in range(32):
            bag.draw()
        combo = bag.draw()
        self.assertEqual(set(combo), {"sizes", "angles", "views", "movements", "tilts"})

    def test_same_seed_same_deck_order(self):
        a = ShotBag(9003, self._small_config())
        b = ShotBag(9003, self._small_config())
        first_a = [a.draw() for _ in range(5)]
        first_b = [b.draw() for _ in range(5)]
        self.assertEqual(first_a, first_b)

    def test_different_seed_different_order(self):
        a = ShotBag(9004, self._small_config())
        b = ShotBag(9005, self._small_config())
        first_a = [a.draw() for _ in range(3)]
        first_b = [b.draw() for _ in range(3)]
        self.assertNotEqual(first_a, first_b)


class TestBuildShotDeterministic(unittest.TestCase):
    def test_same_seed_same_shot(self):
        a = build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 42, 768, 1024)
        b = build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 42, 768, 1024)
        self.assertEqual(a, b)

    def test_restricted_config_respected(self):
        config = json.dumps({"sizes": ["Close-Up"], "angles": ["Eye Level"], "views": ["Front"]})
        shot = build_shot(config, "Deterministic (Seed)", 1, 1024, 1024)
        self.assertEqual(shot["shot_size"], "Close-Up")
        self.assertEqual(shot["angle"], "Eye Level")
        self.assertEqual(shot["view"], "Front")

    def test_regions_consistent_with_geometry(self):
        for seed in range(20):
            shot = build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", seed, 1024, 1024)
            expected = visible_regions(shot["shot_size"], shot["angle"], shot["view"])
            self.assertEqual(shot["regions"], expected)
            self.assertEqual(shot["face_visible"], face_visible(shot["angle"], shot["view"]))

    def test_lens_and_depth_by_size(self):
        for size in core.SHOT_SIZES:
            shot = build_shot(json.dumps({"sizes": [size]}), "Deterministic (Seed)", 3, 1024, 1024)
            self.assertEqual(shot["lens"], core._LENS_BY_SIZE[size])
            self.assertEqual(shot["depth_of_field"], core._DEPTH_BY_SIZE[size])

    def test_orientation_from_dimensions(self):
        self.assertEqual(build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 5, 768, 1024)["orientation"], "portrait")
        self.assertEqual(build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 5, 1024, 768)["orientation"], "landscape")
        self.assertEqual(build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 5, 1024, 1024)["orientation"], "square")

    def test_side_only_for_angled_views(self):
        front = build_shot(json.dumps({"views": ["Front"]}), "Deterministic (Seed)", 9, 1024, 1024)
        self.assertEqual(front["side"], "")
        self.assertEqual(front["azimuth"], 0)
        three_quarter = build_shot(json.dumps({"views": ["3/4 Front"]}), "Deterministic (Seed)", 9, 1024, 1024)
        self.assertIn(three_quarter["side"], ("left", "right"))
        self.assertEqual(three_quarter["azimuth"], 45 * (-1 if three_quarter["side"] == "left" else 1))

    def test_gimbal_degrees(self):
        shot = build_shot(
            json.dumps({"angles": ["Top Down"], "views": ["Back"], "tilts": ["Strong"]}),
            "Deterministic (Seed)",
            4,
            1024,
            1024,
        )
        self.assertEqual(shot["elevation"], 90)
        self.assertEqual(shot["azimuth"], 180)
        self.assertEqual(shot["roll"], 20)

    def test_description_is_prose(self):
        shot = build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 11, 768, 1024)
        self.assertGreater(len(shot["description"]), 60)
        self.assertTrue(shot["description"].endswith("."))
        self.assertIn(shot["shot_size"].lower(), shot["description"].lower())

    def test_keywords_include_axis_values(self):
        shot = build_shot(
            json.dumps(
                {
                    "sizes": ["Close-Up"],
                    "angles": ["Low Angle"],
                    "views": ["3/4 Front"],
                    "movements": ["Tracking"],
                    "tilts": ["Slight"],
                }
            ),
            "Deterministic (Seed)",
            2,
            768,
            1024,
        )
        for part in ("Close-Up", "Low Angle", "Three-Quarter Front View", "Panning Shot", "Slight Dutch", "85mm portrait lens"):
            self.assertIn(part, shot["keywords"])

    def test_static_movement_omitted_from_keywords(self):
        shot = build_shot(
            json.dumps({"sizes": ["Full"], "movements": ["Static"], "tilts": ["None"]}),
            "Deterministic (Seed)",
            2,
            1024,
            1024,
        )
        self.assertNotIn("Static", shot["keywords"])

    def test_long_size_composition_mentions_small_subject(self):
        shot = build_shot(
            json.dumps({"sizes": ["Extreme Long"], "angles": ["Eye Level"]}),
            "Deterministic (Seed)",
            6,
            1024,
            768,
        )
        self.assertIn("small within the frame", shot["description"])


class TestUnrestrictedAxes(unittest.TestCase):
    """Empty per-axis selections leave that axis out of the shot entirely."""

    def _build(self, config: dict[str, Any], mode: str = "Deterministic (Seed)", seed: int = 1) -> dict[str, Any]:
        return build_shot(json.dumps(config), mode, seed, 1024, 1024)

    def test_empty_sizes_omit_framing_clauses(self):
        shot = self._build(
            {"sizes": [], "angles": ["Eye Level"], "views": ["Front"], "looks": ["Leica M6"], "movements": ["Static"], "tilts": ["None"]}
        )
        self.assertEqual(shot["shot_size"], "")
        self.assertEqual(shot["lens"], "")
        self.assertEqual(shot["depth_of_field"], "")
        self.assertNotIn("lens", shot["keywords"])
        self.assertNotIn("depth of field", shot["keywords"])
        self.assertIn("the subject", shot["description"])
        self.assertIn("Shot on a Leica M6", shot["description"])
        self.assertEqual(set(shot["regions"]), set(core._ALL_REGIONS) - {"back", "buttocks"})

    def test_empty_sizes_still_compose_orientation(self):
        shot = self._build({"sizes": [], "angles": []})
        self.assertEqual(shot["composition"], core._COMPOSITION_PHRASES["square"])

    def test_empty_views_keep_all_regions_and_face(self):
        shot = self._build({"views": [], "sizes": ["Full"], "angles": ["Eye Level"]})
        self.assertEqual(shot["view"], "")
        self.assertEqual(shot["side"], "")
        self.assertEqual(shot["azimuth"], 0)
        self.assertTrue(shot["face_visible"])
        self.assertEqual(shot["regions"], core._REGIONS_BY_SIZE["Full"])
        self.assertNotIn("Front View", shot["keywords"])

    def test_empty_angle_keeps_geometry_and_omits_clause(self):
        shot = self._build({"angles": [], "views": ["Back"], "sizes": ["Full"]})
        self.assertEqual(shot["angle"], "")
        self.assertEqual(shot["elevation"], 0)
        self.assertFalse(shot["face_visible"])
        self.assertNotIn("Eye Level Shot", shot["keywords"])
        self.assertIn("back", shot["description"].lower())

    def test_empty_looks_omit_look_sentence_and_keywords(self):
        shot = self._build({"looks": [], "sizes": ["Full"]})
        self.assertEqual(shot["look"], "")
        self.assertNotIn("Shot on", shot["description"])
        self.assertNotIn("Captured on", shot["description"])
        self.assertNotIn("Film Grain", shot["keywords"])
        self.assertIn("Full Body Shot", shot["keywords"])

    def test_empty_movement_and_tilt_omit_their_clauses(self):
        shot = self._build({"movements": [], "tilts": [], "sizes": ["Full"]})
        self.assertEqual(shot["movement"], "")
        self.assertEqual(shot["tilt"], "")
        self.assertEqual(shot["roll"], 0)
        self.assertNotIn("Motion Blur", shot["keywords"])
        self.assertNotIn("Dutch", shot["keywords"])

    def test_all_axes_empty_yields_empty_prose(self):
        config = {"sizes": [], "angles": [], "views": [], "movements": [], "tilts": [], "looks": []}
        shot = self._build(config)
        self.assertEqual(shot["description"], "")
        self.assertEqual(shot["keywords"], "")
        self.assertTrue(shot["face_visible"])
        self.assertEqual(set(shot["regions"]), set(core._ALL_REGIONS))

    def test_no_repeat_with_empty_axis_cycles(self):
        config = json.dumps({"movements": [], "views": ["Front", "Back"], "sizes": ["Full"], "tilts": ["None"], "looks": ["Leica M6"], "angles": ["Eye Level"]})
        seen: set[str] = set()
        for _ in range(8):
            shot = build_shot(config, NO_REPEAT_MODE, 3, 1024, 1024)
            self.assertEqual(shot["movement"], "")
            seen.add(shot["view"])
        self.assertEqual(seen, {"Front", "Back"})


class TestBuildShotModes(unittest.TestCase):
    def test_full_auto_uses_full_space_ignoring_config(self):
        config = json.dumps({"sizes": ["Close-Up"]})
        shot = build_shot(config, "Full Auto", 21, 1024, 1024)
        rng = random.Random(21)
        expected_size = rng.choice(core.SHOT_SIZES)
        self.assertEqual(shot["shot_size"], expected_size)

    def test_full_auto_is_seeded(self):
        a = build_shot(DEFAULT_CONFIG_JSON, "Full Auto", 22, 1024, 1024)
        b = build_shot(DEFAULT_CONFIG_JSON, "Full Auto", 22, 1024, 1024)
        self.assertEqual(a, b)

    def test_no_repeat_draws_unique(self):
        config = json.dumps(
            {
                "sizes": ["Close-Up", "Full"],
                "angles": ["Eye Level", "Low Angle"],
                "views": ["Front", "Back"],
                "movements": ["Static", "Tracking"],
                "tilts": ["None", "Slight"],
                "looks": ["Leica M6"],
            }
        )
        seen = set()
        for _ in range(32):
            shot = build_shot(config, NO_REPEAT_MODE, 77, 1024, 1024)
            key = (shot["shot_size"], shot["angle"], shot["view"], shot["movement"], shot["tilt"])
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_no_repeat_respects_free_axes_only(self):
        config = json.dumps({"sizes": ["Close-Up"], "tilts": ["None", "Slight"]})
        seen = set()
        for _ in range(4):
            shot = build_shot(config, NO_REPEAT_MODE, 88, 1024, 1024)
            self.assertEqual(shot["shot_size"], "Close-Up")
            self.assertIn(shot["tilt"], ("None", "Slight"))
            seen.add((shot["angle"], shot["view"], shot["movement"], shot["tilt"]))
        self.assertEqual(len(seen), 4)

    def test_variant_rng_is_deterministic(self):
        combo = ("Close-Up", "Eye Level", "Front", "Static", "None")
        rng_a = core._variant_rng(5, combo)
        rng_b = core._variant_rng(5, combo)
        self.assertEqual(
            rng_a.choice(core._SHOT_PHRASES["Close-Up"]),
            rng_b.choice(core._SHOT_PHRASES["Close-Up"]),
        )

    def test_bag_is_shared_per_seed_and_config(self):
        config = json.dumps({"sizes": ["Close-Up", "Full"]})
        parsed = parse_config(config)
        bag_a = core._get_bag(123, parsed)
        bag_b = core._get_bag(123, parsed)
        bag_c = core._get_bag(456, parsed)
        self.assertIs(bag_a, bag_b)
        self.assertIsNot(bag_a, bag_c)

    def test_bag_lru_evicts_oldest_after_max(self):
        # _MAX_BAGS is 64 — creating 65 distinct bags must evict the oldest
        core._BAGS.clear()
        base_cfg = {
            "sizes": ["Close-Up"],
            "angles": ["Eye Level"],
            "views": ["Front"],
            "movements": ["Static"],
            "tilts": ["None"],
            "looks": ["Leica M6"],
        }
        for seed in range(core._MAX_BAGS + 5):
            core._get_bag(seed, base_cfg)
        self.assertEqual(len(core._BAGS), core._MAX_BAGS)
        oldest_key = (0, json.dumps(base_cfg, sort_keys=True))
        newest_key = (core._MAX_BAGS + 4, json.dumps(base_cfg, sort_keys=True))
        self.assertNotIn(oldest_key, core._BAGS)
        self.assertIn(newest_key, core._BAGS)
        core._BAGS.clear()

    def test_shot_shape(self):
        shot = build_shot(DEFAULT_CONFIG_JSON, "Deterministic (Seed)", 8, 1024, 1024)
        for key in (
            "type",
            "shot_size",
            "angle",
            "view",
            "movement",
            "tilt",
            "look",
            "side",
            "lens",
            "depth_of_field",
            "orientation",
            "azimuth",
            "elevation",
            "roll",
            "face_visible",
            "regions",
            "composition",
            "description",
            "keywords",
            "width",
            "height",
        ):
            self.assertIn(key, shot)
        self.assertEqual(shot["type"], "camera")
        self.assertEqual(shot["width"], 1024)
        self.assertEqual(shot["height"], 1024)


class TestLookAxis(unittest.TestCase):
    def test_default_config_has_all_looks(self):
        config = parse_config(DEFAULT_CONFIG_JSON)
        self.assertEqual(config["looks"], list(core.LOOKS))

    def test_look_in_all_modes(self):
        for mode in (DETERMINISTIC_MODE, FULL_AUTO_MODE, NO_REPEAT_MODE):
            shot = build_shot(DEFAULT_CONFIG_JSON, mode, 42, 1024, 1024)
            self.assertIn(shot["look"], core.LOOKS)

    def test_description_mentions_chosen_look(self):
        shot = build_shot(DEFAULT_CONFIG_JSON, DETERMINISTIC_MODE, 7, 1024, 1024)
        self.assertTrue(
            "Shot on" in shot["description"] or "Captured on" in shot["description"],
            shot["description"],
        )
        self.assertTrue(shot["description"].endswith("."))

    def test_keywords_include_look_keywords(self):
        shot = build_shot(DEFAULT_CONFIG_JSON, DETERMINISTIC_MODE, 7, 1024, 1024)
        look_keywords = core._LOOK_KEYWORDS[shot["look"]]
        for kw in look_keywords.split(", "):
            self.assertIn(kw, shot["keywords"])

    def test_look_is_seeded_deterministic(self):
        a = build_shot(DEFAULT_CONFIG_JSON, DETERMINISTIC_MODE, 99, 1024, 1024)
        b = build_shot(DEFAULT_CONFIG_JSON, DETERMINISTIC_MODE, 99, 1024, 1024)
        self.assertEqual(a["look"], b["look"])
        self.assertEqual(a["description"], b["description"])

    def test_every_look_has_phrase_and_keywords(self):
        for look in core.LOOKS:
            self.assertIn(look, core._LOOK_PHRASES)
            self.assertGreaterEqual(len(core._LOOK_PHRASES[look]), 2)
            self.assertIn(look, core._LOOK_KEYWORDS)
            self.assertTrue(core._LOOK_KEYWORDS[look])

    def test_look_families_cover_all_looks(self):
        covered: set[str] = set()
        for family, members in core._LOOK_FAMILIES.items():
            for member in members:
                self.assertIn(member, core.LOOKS)
                covered.add(member)
        self.assertEqual(covered, set(core.LOOKS))

    def test_restricted_looks_respected(self):
        config = json.dumps({"looks": ["Leica M6"]})
        shot = build_shot(config, DETERMINISTIC_MODE, 3, 1024, 1024)
        self.assertEqual(shot["look"], "Leica M6")


if __name__ == "__main__":
    unittest.main()
