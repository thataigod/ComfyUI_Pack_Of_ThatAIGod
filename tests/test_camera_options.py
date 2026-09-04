"""Tests for the wildcard-driven camera option space in ``_camera_core.py``."""

import json
import os
import tempfile
import unittest

import _camera_core as core

_PACK_WILDCARDS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "wildcards")


class TmpWildcards:
    """A temporary wildcards root with a write helper."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.wildcards = os.path.join(self.dir, "wildcards")

    def write(self, rel_path: str, content: str) -> None:
        path = os.path.join(self.wildcards, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "TmpWildcards":
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()


class TestLoadOptionSpace(unittest.TestCase):
    def test_missing_camera_tree_returns_none(self):
        with TmpWildcards() as tmp:
            self.assertIsNone(core.load_option_space(tmp.wildcards))

    def test_shipped_pack_space_matches_builtins(self):
        space = core.load_option_space(_PACK_WILDCARDS)
        self.assertIsNotNone(space)
        builtin = core._builtin_space()
        for axis in core._AXIS_DIRS:
            self.assertEqual(set(space[axis]), set(builtin[axis]), axis)
            for name, record in space[axis].items():
                self.assertEqual(record, builtin[axis][name], (axis, name))

    def test_missing_axis_folder_falls_back_to_builtins(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/front.txt", "Front View\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(set(space["sizes"]), set(core._builtin_space()["sizes"]))

    def test_empty_axis_folder_falls_back_to_builtins(self):
        with TmpWildcards() as tmp:
            os.makedirs(os.path.join(tmp.wildcards, "camera", "tilts"))
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(set(space["tilts"]), set(core._builtin_space()["tilts"]))

    def test_dot_and_underscore_files_skipped(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/_notes.txt", "ignored")
            tmp.write("camera/views/.hidden.txt", "ignored")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(set(space["views"]), set(core._builtin_space()["views"]))

    def test_option_without_base_is_skipped(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/mystery.txt", "a phrase line\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertNotIn("mystery", space["views"])

    def test_duplicate_name_keeps_first_file(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/Front.txt", "the first phrase\n")
            tmp.write("camera/views/alias.txt", "#@name: Front\nthe second phrase\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(space["views"]["Front"]["phrases"], ("the first phrase",))


class TestCustomOptions(unittest.TestCase):
    def test_custom_view_inherits_geometry_and_joins_group(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/views/over-the-shoulder-front.txt",
                "#@based_on: Front\n"
                "#@keyword: Over-the-Shoulder Front View\n"
                "the subject caught over the shoulder from the {side}\n",
            )
            space = core.load_option_space(tmp.wildcards)
            record = space["views"]["over-the-shoulder-front"]
            self.assertEqual(record["azimuth"], 0)
            self.assertEqual(record["hides"], frozenset({"back", "buttocks"}))
            self.assertIn("Facing", record["shortcuts"])
            self.assertEqual(record["keyword"], "Over-the-Shoulder Front View")
            groups = dict(core.option_shortcuts(space, "views"))
            self.assertIn("over-the-shoulder-front", groups["Facing"])

    def test_custom_view_filters_like_front(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/views/over-the-shoulder-front.txt",
                "#@based_on: Front\n"
                "#@keyword: Over-the-Shoulder Front View\n"
                "the subject caught over the shoulder from the {side}\n",
            )
            shot = core.build_shot(
                json.dumps({"views": ["over-the-shoulder-front"], "sizes": ["Full"], "angles": ["Eye Level"]}),
                "Deterministic (Seed)",
                1,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertTrue(shot["face_visible"])
            self.assertEqual(shot["regions"], core.visible_regions("Full", "Eye Level", "Front"))
            self.assertEqual(shot["azimuth"], 0)
            self.assertIn("Over-the-Shoulder Front View", shot["keywords"])
            self.assertIn("caught over the shoulder", shot["description"])

    def test_custom_angle_elevation_90_gets_overhead_treatment(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/angles/straight-above.txt",
                "#@based_on: High Angle\n"
                "#@elevation: 90\n"
                "#@keyword: Straight Above Shot\n"
                "shot from directly overhead\n",
            )
            shot = core.build_shot(
                json.dumps({"angles": ["straight-above"]}),
                "Deterministic (Seed)",
                2,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertEqual(shot["elevation"], 90)
            self.assertFalse(shot["face_visible"])
            self.assertIn("directly overhead", shot["description"])
            self.assertIn("looking directly down onto the subject", shot["description"])
            self.assertIn("Straight Above Shot", shot["keywords"])

    def test_custom_hides_override_geometry(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/views/hooded.txt",
                "#@based_on: Front\n"
                "#@hides: face, back, buttocks\n"
                "the subject in a hood\n",
            )
            shot = core.build_shot(
                json.dumps({"views": ["hooded"]}),
                "Deterministic (Seed)",
                3,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertFalse(shot["face_visible"])
            self.assertNotIn("face", shot["regions"])

    def test_custom_movement_close_wide_sections(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/movements/drift.txt",
                "#@based_on: Pan\n"
                "#@keyword: Slow Shutter, Motion Blur\n"
                "#@close\n"
                "a close drift of the frame\n"
                "#@wide\n"
                "a wide drift of the scene\n",
            )
            close_shot = core.build_shot(
                json.dumps({"movements": ["drift"], "sizes": ["Close-Up"]}),
                "Deterministic (Seed)",
                4,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            wide_shot = core.build_shot(
                json.dumps({"movements": ["drift"], "sizes": ["Full"]}),
                "Deterministic (Seed)",
                4,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertIn("close drift", close_shot["description"])
            self.assertIn("wide drift", wide_shot["description"])

    def test_custom_regions_directive_overrides_base(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/sizes/hooded-cu.txt",
                "#@based_on: Close-Up\n"
                "#@regions: hair, neck, shoulders, skin\n"
                "A hooded close-up\n",
            )
            shot = core.build_shot(
                json.dumps({"sizes": ["hooded-cu"], "views": ["Front"], "angles": ["Eye Level"]}),
                "Deterministic (Seed)",
                8,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertEqual(shot["regions"], ["hair", "neck", "shoulders", "skin"])

    def test_custom_size_overrides_lens_depth_and_close_flag(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/sizes/portrait-head.txt",
                "#@based_on: Close-Up\n"
                "#@lens: 135mm portrait lens\n"
                "#@depth: shallow depth of field\n"
                "#@keyword: Portrait Headshot\n"
                "#@shortcuts: Close-ups, Headshots\n"
                "A portrait headshot\n",
            )
            shot = core.build_shot(
                json.dumps({"sizes": ["portrait-head"]}),
                "Deterministic (Seed)",
                5,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertEqual(shot["lens"], "135mm portrait lens")
            self.assertEqual(shot["depth_of_field"], "shallow depth of field")
            self.assertIn("Portrait Headshot", shot["keywords"])
            self.assertIn("A portrait headshot", shot["description"])
            space = core.load_option_space(tmp.wildcards)
            groups = dict(core.option_shortcuts(space, "sizes"))
            self.assertIn("portrait-head", groups["Close-ups"])
            self.assertIn("portrait-head", groups["Headshots"])

    def test_custom_long_directive_sets_long_bucket(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/sizes/vista.txt",
                "#@based_on: Full\n"
                "#@long: true\n"
                "A vast vista framing\n",
            )
            space = core.load_option_space(tmp.wildcards)
            self.assertTrue(space["sizes"]["vista"]["long"])
            shot = core.build_shot(
                json.dumps({"sizes": ["vista"]}),
                "Deterministic (Seed)",
                5,
                1024,
                768,
                wildcards_dir=tmp.wildcards,
            )
            self.assertIn("small within the frame", shot["description"])

    def test_resolve_option_without_builtin_arg(self):
        # Backward-compat path: _resolve_option falls back to _builtin_space().
        parsed = {
            "name": None,
            "based_on": "Front",
            "keyword": None,
            "shortcuts": None,
            "lens": None,
            "depth": None,
            "close": None,
            "long": None,
            "regions": None,
            "hides": None,
            "elevation": None,
            "azimuth": None,
            "roll": None,
            "family": None,
            "phrases": [],
            "close_phrases": [],
            "wide_phrases": [],
        }
        record = core._resolve_option("views", "custom-view", parsed)
        self.assertIsNotNone(record)
        self.assertEqual(record["azimuth"], 0)

    def test_custom_look_family_and_keywords(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/looks/golden-rolliflex.txt",
                "#@based_on: Rolleiflex 2.8F\n"
                "#@family: digital\n"
                "#@keyword: Warm Digital, Golden Tones\n"
                "Shot on a custom golden Rolliflex\n",
            )
            space = core.load_option_space(tmp.wildcards)
            record = space["looks"]["golden-rolliflex"]
            self.assertEqual(record["family"], "digital")
            self.assertEqual(record["keywords"], "Warm Digital, Golden Tones")
            self.assertEqual(record["keyword"], "Warm Digital, Golden Tones")
            self.assertIn("Shot on a custom golden Rolliflex", record["phrases"])
            shot = core.build_shot(
                json.dumps({"looks": ["golden-rolliflex"]}),
                "Deterministic (Seed)",
                6,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertIn("Warm Digital, Golden Tones", shot["keywords"])
            self.assertIn("custom golden Rolliflex", shot["description"])

    def test_replace_semantics_only_files_are_options(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/sizes/Close-Up.txt", "Close-Up\n")
            tmp.write("camera/sizes/Full.txt", "Full\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(set(space["sizes"]), {"Close-Up", "Full"})
            config = json.dumps({"sizes": ["Close-Up", "full", "bogus"]})
            parsed = core.parse_config(config, space)
            self.assertEqual(parsed["sizes"], ["Close-Up"])

    def test_side_placeholder_skipped_on_side_less_views(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/views/over-the-shoulder-front.txt",
                "#@based_on: Front\n"
                "the subject caught over the shoulder from the {side}\n",
            )
            shot = core.build_shot(
                json.dumps({"views": ["over-the-shoulder-front"], "sizes": ["Full"], "angles": ["Eye Level"]}),
                "Deterministic (Seed)",
                1,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertNotIn("{side}", shot["description"])
            self.assertNotIn("from the ,", shot["description"])

    def test_side_phrase_without_placeholder(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/views/three-quarter-front.txt",
                "#@name: 3/4 Front\n"
                "#@azimuth: 45\n"
                "#@hides: back, buttocks\n"
                "plain three-quarter phrasing\n",
            )
            shot = core.build_shot(
                json.dumps({"views": ["3/4 Front"], "sizes": ["Full"], "angles": ["Eye Level"]}),
                "Deterministic (Seed)",
                2,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertIn("plain three-quarter phrasing", shot["description"])
            self.assertIn(shot["side"], ("left", "right"))

    def test_based_on_missing_falls_back_to_name(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/Profile.txt", "a fresh profile phrase\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertIn("Profile", space["views"])
            self.assertEqual(space["views"]["Profile"]["phrases"], ("a fresh profile phrase",))
            self.assertEqual(space["views"]["Profile"]["azimuth"], 90)

    def test_name_directive_overrides_filename(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/three-quarter-front.txt", "#@name: 3/4 Front\n#@based_on: Front\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertIn("3/4 Front", space["views"])
            self.assertNotIn("three-quarter-front", space["views"])


class TestOptionShortcuts(unittest.TestCase):
    def test_shipped_groups_match_frontend_layout(self):
        space = core.load_option_space(_PACK_WILDCARDS)
        groups = dict(core.option_shortcuts(space, "views"))
        self.assertEqual(set(groups["Facing"]), {"Front", "3/4 Front"})
        self.assertEqual(set(groups["Away"]), {"Back", "3/4 Back"})
        look_groups = dict(core.option_shortcuts(space, "looks"))
        self.assertEqual(len(look_groups["Film"]), 11)
        self.assertEqual(len(look_groups["Digital"]), 9)

    def test_custom_group_created_by_membership(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/alt-front.txt", "#@based_on: Front\n#@shortcuts: Facing, Custom\n")
            space = core.load_option_space(tmp.wildcards)
            groups = dict(core.option_shortcuts(space, "views"))
            self.assertIn("Custom", groups)
            self.assertIn("alt-front", groups["Custom"])


class TestParseConfigWithSpace(unittest.TestCase):
    def test_unknown_options_dropped_with_space(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/Front.txt", "Front\n")
            space = core.load_option_space(tmp.wildcards)
            config = json.dumps({"views": ["Front", "3/4 Front", "totally-bogus"]})
            parsed = core.parse_config(config, space)
            self.assertEqual(parsed["views"], ["Front"])

    def test_default_config_respects_space_order(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/a-view.txt", "#@based_on: Front\n")
            tmp.write("camera/views/b-view.txt", "#@based_on: Back\n")
            space = core.load_option_space(tmp.wildcards)
            parsed = core.parse_config("{}", space)
            self.assertEqual(parsed["views"], ["a-view", "b-view"])


class TestBuildShotWithSpace(unittest.TestCase):
    def test_full_auto_covers_file_space(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/custom-view.txt", "#@based_on: Front\n")
            space = core.load_option_space(tmp.wildcards)
            shot = core.build_shot(
                json.dumps({"sizes": ["Full"]}),
                "Full Auto",
                7,
                1024,
                1024,
                option_space=space,
            )
            self.assertIn(shot["view"], ("custom-view", "Front", "Profile", "3/4 Front", "Back", "3/4 Back"))

    def test_no_repeat_uses_space(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/Front.txt", "Front\n")
            tmp.write("camera/views/custom-view.txt", "#@based_on: Front\n")
            space = core.load_option_space(tmp.wildcards)
            seen = set()
            for _ in range(64):
                shot = core.build_shot(
                    json.dumps({"views": ["custom-view", "Front"]}),
                    core.NO_REPEAT_MODE,
                    9,
                    1024,
                    1024,
                    option_space=space,
                )
                seen.add(shot["view"])
            self.assertEqual(seen, {"custom-view", "Front"})

    def test_option_space_argument_wins_over_wildcards_dir(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/custom-view.txt", "#@based_on: Front\n")
            space = core.load_option_space(tmp.wildcards)
            shot = core.build_shot(
                json.dumps({"views": ["custom-view"]}),
                "Deterministic (Seed)",
                11,
                1024,
                1024,
                wildcards_dir=os.path.join(tmp.dir, "nowhere"),
                option_space=space,
            )
            self.assertEqual(shot["view"], "custom-view")

    def test_side_rule_uses_azimuth_not_name(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/three-quarter-front.txt", "#@based_on: 3/4 Front\n")
            tmp.write("camera/views/dead-ahead.txt", "#@based_on: Front\n#@azimuth: 180\n")
            space = core.load_option_space(tmp.wildcards)
            angled = core.build_shot(
                json.dumps({"views": ["three-quarter-front"]}),
                "Deterministic (Seed)",
                13,
                1024,
                1024,
                option_space=space,
            )
            self.assertIn(angled["side"], ("left", "right"))
            dead = core.build_shot(
                json.dumps({"views": ["dead-ahead"]}),
                "Deterministic (Seed)",
                13,
                1024,
                1024,
                option_space=space,
            )
            self.assertEqual(dead["side"], "")


class TestParsingDetails(unittest.TestCase):
    def test_comments_and_unknown_directives_ignored(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "camera/views/clean.txt",
                "# a comment line\n"
                "#@unknown_key: whatever\n"
                "#@based_on: Front\n"
                "\n"
                "the visible phrase\n",
            )
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(space["views"]["clean"]["phrases"], ("the visible phrase",))

    def test_invalid_int_directive_falls_back(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/angles/odd.txt", "#@based_on: High Angle\n#@elevation: not-a-number\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(space["angles"]["odd"]["elevation"], 45)

    def test_family_directive_lowercased(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/looks/flat.txt", "#@based_on: Leica M6\n#@family: Film\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(space["looks"]["flat"]["family"], "film")

    def test_unreadable_file_skipped(self):
        with TmpWildcards() as tmp:
            bad_path = os.path.join(tmp.wildcards, "camera", "views", "bad.txt")
            os.makedirs(os.path.dirname(bad_path), exist_ok=True)
            with open(bad_path, "wb") as f:
                f.write(b"\xff\xfe invalid utf-8 \xfe\xff\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertNotIn("bad", space["views"])

    def test_bom_file_parses_directives(self):
        with TmpWildcards() as tmp:
            bom_path = os.path.join(tmp.wildcards, "camera", "views", "bomview.txt")
            os.makedirs(os.path.dirname(bom_path), exist_ok=True)
            with open(bom_path, "w", encoding="utf-8-sig") as f:
                f.write("#@based_on: Front\nthe bom view phrase\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertIn("bomview", space["views"])
            self.assertEqual(space["views"]["bomview"]["azimuth"], 0)

    def test_bool_typo_inherits_base(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/sizes/typo.txt", "#@based_on: Close-Up\n#@close: ture\nA typo close-up\n")
            tmp.write("camera/sizes/explicit-false.txt", "#@based_on: Close-Up\n#@close: false\nA false close-up\n")
            space = core.load_option_space(tmp.wildcards)
            # Close-Up base close=True; typo must inherit instead of flipping.
            self.assertTrue(space["sizes"]["typo"]["close"])
            self.assertFalse(space["sizes"]["explicit-false"]["close"])

    def test_out_of_range_gimbal_inherits_base(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/angles/crazy.txt", "#@based_on: High Angle\n#@elevation: 9999\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(space["angles"]["crazy"]["elevation"], 45)

    def test_custom_tilt_leading_comma_normalized(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/tilts/custom.txt", "#@based_on: Slight\n, framed custom with comma\n")
            space = core.load_option_space(tmp.wildcards)
            self.assertEqual(space["tilts"]["custom"]["phrases"], ("framed custom with comma",))
            shot = core.build_shot(
                json.dumps({"tilts": ["custom"], "sizes": ["Full"]}),
                "Deterministic (Seed)",
                1,
                1024,
                1024,
                wildcards_dir=tmp.wildcards,
            )
            self.assertNotIn(", ,", shot["description"])

    def test_file_space_uses_builtin_order(self):
        with TmpWildcards() as tmp:
            tmp.write("camera/views/Back.txt", "back phrase\n")
            tmp.write("camera/views/Front.txt", "front phrase\n")
            space = core.load_option_space(tmp.wildcards)
            # Alphabetical would be Back first; curated builtin order is Front.
            self.assertEqual(list(space["views"]), ["Front", "Back"])


if __name__ == "__main__":
    unittest.main()
