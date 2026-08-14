"""Tests for the pure scene engine in ``_scene_core.py``."""

import os
import tempfile
import unittest

import _scene_core as core
from _scene_core import ALL_TIMES, AUTO_LOCATION, build_scene
from _wildcard_core import WildcardResolver


class TmpWildcards:
    """Build a minimal wildcards tree in a temp directory."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def write(self, rel: str, content: str) -> None:
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def __enter__(self) -> "TmpWildcards":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        self._tmp.cleanup()


def _make_scenes(tmp: TmpWildcards) -> None:
    tmp.write(
        "scenes/beach.txt",
        "#@setting: outdoor\n"
        "#@outfit: swimwear\n"
        "#@occasion: beach\n"
        "#@time: noon\n"
        "a sunny beach with umbrellas\n"
        "#@setting: outdoor\n"
        "#@outfit: swimwear\n"
        "#@occasion: beach\n"
        "#@time: night\n"
        "a quiet starlit beach\n"
        "#@setting: outdoor\n"
        "#@outfit: swimwear\n"
        "#@occasion: beach\n"
        "a lively beach with umbrellas",
    )
    tmp.write(
        "scenes/ballroom.txt",
        "#@setting: indoor\n"
        "#@outfit: formal\n"
        "#@occasion: formal\n"
        "#@time: night\n"
        "a grand ballroom\n"
        "#@setting: indoor\n"
        "#@outfit: formal\n"
        "#@occasion: formal\n"
        "an opulent ballroom",
    )
    tmp.write(
        "scenes/bedroom.txt",
        "#@setting: indoor\n"
        "#@outfit: lingerie\n"
        "#@occasion: intimate\n"
        "#@time: night\n"
        "#@state: nude, slipping\n"
        "a softly furnished bedroom",
    )
    tmp.write("scenes/catalog.txt", "not a scene")


def _make_times(tmp: TmpWildcards) -> None:
    tmp.write(
        "shared/time-of-day.txt",
        "#@time: noon\n#@setting: outdoor\nharsh midday sun\n"
        "#@time: noon\n#@setting: indoor\nharsh midday glare\n"
        "#@time: night\n#@setting: outdoor\ndeep night\n"
        "#@time: night\n#@setting: indoor\ndim lamplight",
    )


def _make_styles(tmp: TmpWildcards) -> None:
    tmp.write("styles/film-look.txt", "__styles/film-look/commercial-stocks__")
    tmp.write("styles/film-look/commercial-stocks.txt", "Style and tones: Kodachrome")


class TestSceneOptions(unittest.TestCase):
    def test_scans_scenes_directory(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            self.assertEqual(core._scene_options(tmp.dir), ["ballroom", "beach", "bedroom"])

    def test_missing_directory_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(core._scene_options(d), [])

    def test_catalog_file_excluded(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/catalog.txt", "not a scene")
            self.assertEqual(core._scene_options(tmp.dir), [])


class TestTimeOptions(unittest.TestCase):
    def test_distinct_values_in_file_order(self):
        with TmpWildcards() as tmp:
            _make_times(tmp)
            self.assertEqual(core._time_options(tmp.dir), ["All", "noon", "night"])

    def test_duplicates_and_plain_lines_ignored(self):
        with TmpWildcards() as tmp:
            tmp.write(
                "shared/time-of-day.txt",
                "# comment line\n#@time: dusk\nfirst light\n#@time: dusk\na second dusk phrase",
            )
            self.assertEqual(core._time_options(tmp.dir), ["All", "dusk"])

    def test_missing_file_returns_unrestricted_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(core._time_options(d), ["All"])

    def test_case_normalised(self):
        with TmpWildcards() as tmp:
            tmp.write("shared/time-of-day.txt", "#@time: Golden Hour\nlong shadows")
            self.assertEqual(core._time_options(tmp.dir), ["All", "golden hour"])


class TestContext(unittest.TestCase):
    def test_all_dimensions(self):
        self.assertEqual(
            core._context("office", "night", "formal", "nude"),
            {"occasion": {"office"}, "time": {"night"}, "outfit": {"formal"}, "state": {"nude"}},
        )

    def test_empty_dimensions_omitted(self):
        self.assertEqual(core._context("", "", ""), {})
        self.assertEqual(core._context("office", "", ""), {"occasion": {"office"}})

    def test_dressed_state_omitted(self):
        self.assertEqual(
            core._context("office", "", "formal", "dressed"),
            {"occasion": {"office"}, "outfit": {"formal"}},
        )
        self.assertEqual(
            core._context("office", "", "formal", ""),
            {"occasion": {"office"}, "outfit": {"formal"}},
        )


class TestPickLocation(unittest.TestCase):
    def test_auto_filters_by_context(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            resolver = WildcardResolver(tmp.dir)
            location, prose = core._pick_location(resolver, AUTO_LOCATION, {"occasion": {"beach"}})
            self.assertEqual(location, "beach")
            self.assertIn(prose, ("a sunny beach with umbrellas", "a quiet starlit beach", "a lively beach with umbrellas"))

    def test_auto_outfit_context(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            resolver = WildcardResolver(tmp.dir)
            location, prose = core._pick_location(resolver, AUTO_LOCATION, {"outfit": {"formal"}})
            self.assertEqual(location, "ballroom")
            self.assertIn(prose, ("a grand ballroom", "an opulent ballroom"))

    def test_auto_nothing_eligible(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/beach.txt", "#@occasion: beach\na sunny beach")
            tmp.write("scenes/ballroom.txt", "#@occasion: formal\na grand ballroom")
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_location(resolver, AUTO_LOCATION, {"occasion": {"costume"}}), ("", ""))

    def test_auto_prefers_tagged_scenes_over_universal(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            resolver = WildcardResolver(tmp.dir, seed=1)
            location, prose = core._pick_location(resolver, AUTO_LOCATION, {"occasion": {"beach"}})
            self.assertEqual(location, "beach")
            self.assertIn(prose, ("a sunny beach with umbrellas", "a quiet starlit beach", "a lively beach with umbrellas"))

    def test_auto_falls_back_to_universal_when_nothing_tagged(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            resolver = WildcardResolver(tmp.dir, seed=1)
            self.assertEqual(
                core._pick_location(resolver, AUTO_LOCATION, {"occasion": {"costume"}}),
                ("studio", "a minimalist photography studio"),
            )

    def test_untagged_scenes_detection(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/tagged.txt", "#@occasion: beach\nx")
            tmp.write("scenes/setting_only.txt", "#@setting: indoor\nx")
            tmp.write("scenes/state_only.txt", "#@setting: indoor\n#@state: nude\nx")
            tmp.write("scenes/bare.txt", "x")
            tmp.write("scenes/catalog.txt", "not a scene")
            self.assertEqual(core._untagged_scenes(tmp.dir), {"setting_only.txt", "bare.txt"})

    def test_untagged_scenes_missing_dir(self):
        self.assertEqual(core._untagged_scenes("does/not/exist"), set())

    def test_has_selection_directive(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/a.txt", "#@setting: indoor\n#@outfit: formal\nx")
            self.assertTrue(core._has_selection_directive(os.path.join(tmp.dir, "scenes/a.txt")))
            tmp.write("scenes/b.txt", "#@setting: indoor\nx")
            self.assertFalse(core._has_selection_directive(os.path.join(tmp.dir, "scenes/b.txt")))
            tmp.write("scenes/c.txt", "#@setting: indoor\n#@state: nude\nx")
            self.assertTrue(core._has_selection_directive(os.path.join(tmp.dir, "scenes/c.txt")))
            self.assertFalse(core._has_selection_directive(os.path.join(tmp.dir, "scenes/missing.txt")))

    def test_state_scenes_detection(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            self.assertEqual(core._state_scenes(tmp.dir, "nude"), {"bedroom.txt"})
            self.assertEqual(core._state_scenes(tmp.dir, "slipping"), {"bedroom.txt"})
            self.assertEqual(core._state_scenes(tmp.dir, "mishap"), set())

    def test_state_scenes_missing_dir(self):
        self.assertEqual(core._state_scenes("does/not/exist", "nude"), set())

    def test_state_scenes_skips_unreadable_files(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            os.makedirs(os.path.join(tmp.dir, "scenes", "locked.txt"))
            self.assertEqual(core._state_scenes(tmp.dir, "nude"), {"bedroom.txt"})

    def test_state_blocked_scenes_detection(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            self.assertEqual(core._state_blocked_scenes(tmp.dir, "nude"), {"beach.txt", "ballroom.txt"})
            self.assertEqual(
                core._state_blocked_scenes(tmp.dir, "mishap"),
                {"beach.txt", "ballroom.txt", "bedroom.txt"},
            )

    def test_state_blocked_leaves_universal_scenes(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            self.assertNotIn("studio.txt", core._state_blocked_scenes(tmp.dir, "nude"))

    def test_state_blocked_scenes_missing_dir(self):
        self.assertEqual(core._state_blocked_scenes("does/not/exist", "nude"), set())

    def test_auto_state_gate_blocks_public_scenes(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            resolver = WildcardResolver(tmp.dir, seed=1)
            self.assertEqual(
                core._pick_location(resolver, AUTO_LOCATION, {"occasion": {"beach"}}, "nude"),
                ("studio", "a minimalist photography studio"),
            )

    def test_auto_state_gate_allows_private_scenes(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            resolver = WildcardResolver(tmp.dir, seed=1)
            self.assertEqual(
                core._pick_location(
                    resolver,
                    AUTO_LOCATION,
                    {"occasion": {"intimate"}, "outfit": {"lingerie"}},
                    "nude",
                ),
                ("bedroom", "a softly furnished bedroom"),
            )

    def test_auto_dressed_state_unaffected(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            resolver = WildcardResolver(tmp.dir, seed=1)
            self.assertEqual(
                core._pick_location(resolver, AUTO_LOCATION, {"occasion": {"beach"}}, "dressed"),
                ("beach", "a sunny beach with umbrellas"),
            )

    def test_auto_state_gate_without_context(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            resolver = WildcardResolver(tmp.dir, seed=1)
            location, _prose = core._pick_location(resolver, AUTO_LOCATION, {}, "nude")
            self.assertIn(location, ("bedroom", "studio"))

    def test_explicit_ignores_filtering(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            tmp.write("scenes/studio.txt", "a minimalist photography studio")
            resolver = WildcardResolver(tmp.dir)
            location, prose = core._pick_location(resolver, "studio", {"occasion": {"costume"}})
            self.assertEqual((location, prose), ("studio", "a minimalist photography studio"))

    def test_explicit_ignores_state_gate(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            resolver = WildcardResolver(tmp.dir)
            location, prose = core._pick_location(resolver, "beach", {"occasion": {"beach"}}, "nude")
            self.assertEqual(location, "beach")
            self.assertIn(prose, ("a sunny beach with umbrellas", "a quiet starlit beach", "a lively beach with umbrellas"))

    def test_explicit_missing_file(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_location(resolver, "nope", {}), ("", ""))

    def test_explicit_empty_file(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/empty.txt", "# only a comment")
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_location(resolver, "empty", {}), ("", ""))


class TestPickTime(unittest.TestCase):
    def test_all_picks_any_phrase(self):
        with TmpWildcards() as tmp:
            _make_times(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertIn(
                core._pick_time(resolver, ALL_TIMES, ""),
                ("harsh midday sun", "harsh midday glare", "deep night", "dim lamplight"),
            )

    def test_explicit_filters_phrase(self):
        with TmpWildcards() as tmp:
            _make_times(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertIn(core._pick_time(resolver, "noon", ""), ("harsh midday sun", "harsh midday glare"))

    def test_setting_filters_variant(self):
        with TmpWildcards() as tmp:
            _make_times(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_time(resolver, "noon", "indoor"), "harsh midday glare")
            self.assertEqual(core._pick_time(resolver, "noon", "outdoor"), "harsh midday sun")

    def test_time_without_matching_phrase(self):
        with TmpWildcards() as tmp:
            _make_times(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_time(resolver, "dawn", ""), "")

    def test_missing_file(self):
        with TmpWildcards() as tmp:
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_time(resolver, ALL_TIMES, ""), "")


class TestFileSetting(unittest.TestCase):
    def test_reads_setting_directive(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            self.assertEqual(core._file_setting(tmp.dir, "beach"), "outdoor")
            self.assertEqual(core._file_setting(tmp.dir, "ballroom"), "indoor")

    def test_missing_file_and_no_directive(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            self.assertEqual(core._file_setting(tmp.dir, "nope"), "")
            self.assertEqual(core._file_setting(tmp.dir, ""), "")
            tmp.write("scenes/plain.txt", "just prose")
            self.assertEqual(core._file_setting(tmp.dir, "plain"), "")


class TestPickStyle(unittest.TestCase):
    def test_disabled_returns_empty(self):
        with TmpWildcards() as tmp:
            _make_styles(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_style(resolver, False, "styles/film-look", {}), "")

    def test_enabled_picks_line(self):
        with TmpWildcards() as tmp:
            _make_styles(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_style(resolver, True, "styles/film-look", {}), "Style and tones: Kodachrome")

    def test_enabled_missing_file(self):
        with TmpWildcards() as tmp:
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_style(resolver, True, "styles/film-look", {}), "")

    def test_nested_tags_resolved(self):
        with TmpWildcards() as tmp:
            _make_styles(tmp)
            tmp.write("styles/film-look.txt", "__styles/film-look/analog-processes__")
            tmp.write("styles/film-look/analog-processes.txt", "Style and tones: wet plate collodion")
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(
                core._pick_style(resolver, True, "styles/film-look", {}),
                "Style and tones: wet plate collodion",
            )


class TestResolveOccasion(unittest.TestCase):
    def test_explicit_verbatim(self):
        self.assertEqual(core._resolve_occasion("  TRAVEL ", None, [], 0), ("travel", "explicit"))

    def test_unrestricted_tokens(self):
        for value in ("", "All (unrestricted)", "all"):
            self.assertEqual(core._resolve_occasion(value, None, [], 0), ("", "unrestricted"))

    def test_auto_uses_character_occasion(self):
        character = {"occasion": "beach"}
        self.assertEqual(core._resolve_occasion("auto", character, [], 0), ("beach", "character"))

    def test_auto_follows_unrestricted_character_verbatim(self):
        self.assertEqual(core._resolve_occasion("auto", {"occasion": ""}, ["beach", "formal"], 7), ("", "character"))

    def test_auto_without_character_picks_seeded_random(self):
        options = ["beach", "formal", "office"]
        a = core._resolve_occasion("auto", None, options, 5)
        b = core._resolve_occasion("auto", None, options, 5)
        self.assertEqual(a, b)
        self.assertEqual(a[1], "random")
        self.assertIn(a[0], options)
        picks = {core._resolve_occasion("auto", None, options, s)[0] for s in range(10)}
        self.assertGreater(len(picks), 1)

    def test_auto_without_options_is_unrestricted(self):
        self.assertEqual(core._resolve_occasion("auto", None, [], 0), ("", "unrestricted"))

    def test_random_excludes_unrestricted_entry(self):
        result, source = core._resolve_occasion("auto", None, ["All (unrestricted)", "beach"], 1)
        self.assertEqual((result, source), ("beach", "random"))


class TestAssemble(unittest.TestCase):
    def test_full_assembly(self):
        description, keywords = core._assemble(
            "a grand ballroom", "ballroom", "night", "deep night", "Style and tones: Kodachrome"
        )
        self.assertEqual(description, "a grand ballroom, deep night, Style and tones: Kodachrome")
        self.assertEqual(keywords, "ballroom, night")

    def test_empty_parts_vanish(self):
        description, keywords = core._assemble("", "", "All", "", "")
        self.assertEqual((description, keywords), ("", ""))

    def test_unrestricted_time_excluded_from_keywords(self):
        _desc, keywords = core._assemble("a beach", "beach", "All", "warm sun", "")
        self.assertEqual(keywords, "beach")

    def test_keywords_deduplicated(self):
        _desc, keywords = core._assemble("a beach", "beach", "night", "deep night", "")
        self.assertEqual(keywords, "beach, night")


class TestBuildScene(unittest.TestCase):
    def _full_args(self, tmp: TmpWildcards, **overrides: object) -> dict:
        args = {
            "wildcards_dir": tmp.dir,
            "character": {"type": "character", "outfit_category": "formal", "state": "dressed"},
            "occasion": "formal",
            "occasion_source": "explicit",
            "location": AUTO_LOCATION,
            "time": "night",
            "use_film": True,
            "mode": "Deterministic (Seed)",
            "seed": 1,
        }
        args.update(overrides)
        return args

    def test_full_pipeline(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            scene = build_scene(**self._full_args(tmp))
            self.assertEqual(scene["type"], "scene")
            self.assertEqual(scene["location_key"], "ballroom")
            self.assertEqual(scene["location"], "a grand ballroom")
            self.assertEqual(scene["setting"], "indoor")
            self.assertEqual(scene["time_of_day"], "dim lamplight")
            self.assertEqual(scene["film_look"], "Style and tones: Kodachrome")
            self.assertEqual(scene["state"], "dressed")
            self.assertEqual(scene["occasion"], "formal")
            self.assertEqual(scene["occasion_source"], "explicit")
            self.assertEqual(scene["description"], "a grand ballroom, dim lamplight, Style and tones: Kodachrome")
            self.assertEqual(scene["keywords"], "ballroom, night")
            self.assertEqual(scene["mode"], "Deterministic (Seed)")
            self.assertEqual(scene["seed"], 1)
            for dropped in ("subject", "full_prompt", "atmosphere", "lighting", "camera_description"):
                self.assertNotIn(dropped, scene)

    def test_outfit_context_blocks_mismatched_location(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/beach.txt", "#@outfit: swimwear\n#@occasion: beach\na sunny beach")
            tmp.write("scenes/ballroom.txt", "#@outfit: formal\n#@occasion: formal\na grand ballroom")
            _make_times(tmp)
            _make_styles(tmp)
            scene = build_scene(**self._full_args(tmp, character={"outfit_category": "lingerie"}))
            self.assertEqual(scene["location_key"], "")
            self.assertEqual(scene["location"], "")
            self.assertNotIn("beach", scene["description"])

    def test_block_time_filtering_picks_block_prose(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            args = self._full_args(
                tmp,
                occasion="beach",
                character={"outfit_category": "swimwear", "state": "dressed"},
                time="noon",
            )
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "beach")
            self.assertIn(scene["location"], ("a sunny beach with umbrellas", "a lively beach with umbrellas"))
            args = self._full_args(
                tmp,
                occasion="beach",
                character={"outfit_category": "swimwear", "state": "dressed"},
                time="night",
            )
            scene = build_scene(**args)
            self.assertIn(scene["location"], ("a quiet starlit beach", "a lively beach with umbrellas"))

    def test_time_neutral_fallback_for_all(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            args = self._full_args(
                tmp,
                occasion="beach",
                character={"outfit_category": "swimwear", "state": "dressed"},
                time=ALL_TIMES,
            )
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "beach")
            self.assertIn(
                scene["location"],
                ("a sunny beach with umbrellas", "a quiet starlit beach", "a lively beach with umbrellas"),
            )

    def test_unexpected_explicit_time_uses_time_neutral_fallback(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            # ballroom declares only night; a noon request must resolve to its
            # time-neutral fallback block, proving file-level and line-level
            # eligibility agree on block-scoped directives.
            args = self._full_args(
                tmp,
                occasion="formal",
                character={"outfit_category": "formal", "state": "dressed"},
                time="noon",
            )
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "ballroom")
            self.assertEqual(scene["location"], "an opulent ballroom")

    def test_state_gating_public_occasion_lands_on_studio(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            tmp.write("scenes/studio.txt", "#@setting: indoor\na minimalist photography studio")
            args = self._full_args(tmp, occasion="beach", character={"outfit_category": "swimwear", "state": "nude"})
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "studio")
            self.assertEqual(scene["state"], "nude")

    def test_state_gating_private_occasion(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            args = self._full_args(
                tmp, occasion="intimate", character={"outfit_category": "lingerie", "state": "nude"}
            )
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "bedroom")

    def test_dressed_state_unaffected(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            args = self._full_args(tmp, occasion="beach", character={"outfit_category": "swimwear", "state": "dressed"})
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "beach")

    def test_none_character(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            scene = build_scene(**self._full_args(tmp, character=None))
            self.assertEqual(scene["state"], "")
            self.assertEqual(scene["location_key"], "ballroom")

    def test_nothing_eligible_yields_empty(self):
        with TmpWildcards() as tmp:
            tmp.write("scenes/beach.txt", "#@occasion: beach\na sunny beach")
            tmp.write("scenes/ballroom.txt", "#@occasion: formal\na grand ballroom")
            scene = build_scene(**self._full_args(tmp, occasion="costume", use_film=False))
            self.assertEqual(scene["location_key"], "")
            self.assertEqual(scene["time_of_day"], "")
            self.assertEqual(scene["description"], "")
            self.assertEqual(scene["keywords"], "night")

    def test_disabled_film_and_explicit_location(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            tmp.write("scenes/studio.txt", "a minimalist photography studio")
            args = self._full_args(tmp, location="studio", use_film=False, time=ALL_TIMES)
            scene = build_scene(**args)
            self.assertEqual(scene["location_key"], "studio")
            self.assertEqual(scene["setting"], "")
            self.assertIn(
                scene["time_of_day"],
                ("harsh midday sun", "harsh midday glare", "deep night", "dim lamplight"),
            )
            self.assertEqual(scene["film_look"], "")

    def test_deterministic_same_seed_identical(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            args = self._full_args(tmp)
            self.assertEqual(build_scene(**args), build_scene(**args))

    def test_no_repeat_mode_runs_and_varies(self):
        with TmpWildcards() as tmp:
            _make_scenes(tmp)
            _make_times(tmp)
            _make_styles(tmp)
            tmp.write("scenes/studio.txt", "a minimalist photography studio")
            args = self._full_args(tmp, mode="Random (No Repeat)", seed=0, time=ALL_TIMES)
            outs = [build_scene(**args) for _ in range(5)]
            self.assertTrue(all(o["type"] == "scene" for o in outs))
            self.assertGreater(len({o["description"] for o in outs}), 1)


if __name__ == "__main__":
    unittest.main()
