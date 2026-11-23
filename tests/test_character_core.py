"""Tests for the pure character engine v2 in ``_character_core.py``.

The engine is exercised against a synthetic wildcards tree: a custom persona
("maya") with descriptors, a lewdity band and a personal wardrobe; a shared
common wardrobe (``characters/female/wardrobe``) with band-rated slot files;
matching locations plus a small location taxonomy; and extras pools.
"""

import logging
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _character_core import (
    _EXTRA_CAP,
    WARDROBE_COMPLETE,
    WARDROBE_EXTERNAL,
    WARDROBE_INTERNAL,
    WARDROBE_MODES,
    _background,
    _catalog_occasions,
    _compose_fit,
    _context,
    _fill_slots,
    _parse_keyword_directives,
    _parse_lewdity_value,
    _pick_category,
    _pose_context,
    _read_gender,
    _read_lewdity_file,
    _read_measurements,
    _regions_from_camera,
    _resolve_lewdity,
    _resolve_slot,
    _roll_extras,
    _roll_occasion,
    _safe_persona,
    _split_tokens,
    _tag_basename,
    _tag_path,
    _tag_tokens,
    _wardrobe_plan,
    build_character,
)
from _wildcard_core import WildcardResolver

_CACHES = (
    WildcardResolver._file_index_cache,
    WildcardResolver._file_mtimes,
    WildcardResolver._annotations_cache,
    WildcardResolver._block_cache,
    WildcardResolver._deck_cache,
    WildcardResolver._choice_deck_cache,
)


class EngineFixture(unittest.TestCase):
    """Shared fixture: tmp wildcards root with persona, wardrobes, locations, extras."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wildcards = os.path.join(self.temp_dir, "wildcards")
        os.makedirs(self.wildcards)
        for cache in _CACHES:
            cache.clear()

    def tearDown(self):
        for cache in _CACHES:
            cache.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write(self, rel: str, content: str) -> str:
        path = os.path.join(self.wildcards, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _resolver(self, mode: str = "Deterministic (Seed)", seed: int = 0) -> WildcardResolver:
        return WildcardResolver(self.wildcards, mode=mode, seed=seed)

    def _make_maya(self, lewdity: str = "20-80") -> None:
        base = "characters/maya"
        self._write(f"{base}/gender.txt", "female\n")
        if lewdity is not None:
            self._write(f"{base}/lewdity.txt", lewdity + "\n")
        self._write(
            f"{base}/subject_intro.txt",
            "a poised woman with dark hair\n"
            "#@occasion: beach\n"
            "a relaxed beachgoer with salt-tousled hair\n"
            "#@occasion: office\n"
            "a composed professional with neat dark hair\n",
        )
        self._write(f"{base}/face.txt", "#@keyword: Perfect Eyes, Bindi\na soft oval face with warm eyes\n")
        self._write(f"{base}/hair.txt", "long dark hair in a loose braid\n")
        self._write(f"{base}/profile.txt", "a fine-boned profile\n")
        self._write(
            f"{base}/pose.txt",
            "#@facing: front\n"
            "#@awareness: aware\n"
            "standing tall with calm confidence\n"
            "#@facing: profile\n"
            "walking past, glancing away\n",
        )
        self._write(f"{base}/trigger.txt", "maya_lora\n")
        self._write(f"{base}/measurements.txt", "#@bust: generous\n#@thighs: toned\n")
        self._write(
            f"{base}/wardrobe/catalog.txt",
            "#@occasion: home\n__characters/maya/wardrobe/loungewear__\n",
        )
        self._write(
            f"{base}/wardrobe/loungewear/tops.txt",
            "#@lewdity: 10\na soft knit loungewear top\nanother cozy tee\n",
        )

    def _make_common(self) -> None:
        base = "characters/female/wardrobe"
        self._write(
            f"{base}/catalog.txt",
            "#@occasion: casual, travel, home\n__characters/female/wardrobe/casual__\n\n"
            "#@occasion: intimate, boudoir\n__characters/female/wardrobe/lingerie__\n\n"
            "#@occasion: beach, pool, resort\n__characters/female/wardrobe/resort__\n",
        )
        self._write(
            f"{base}/casual/tops.txt",
            "#@lewdity: 20\n#@fit: bust\na pastel cotton tee in a soft weave\n"
            "#@lewdity: 60\n#@fit: bust\na daring crop top with thin straps\n",
        )
        self._write(f"{base}/casual/bottoms.txt", "#@lewdity: 20\n#@fit: hips\ndark straight-leg jeans\n")
        self._write(f"{base}/casual/shoes.txt", "#@lewdity: 20\nwhite canvas sneakers\n")
        self._write(f"{base}/casual/one-piece.txt", "#@lewdity: 20\na denim overall dress\n")
        self._write(f"{base}/lingerie/tops.txt", "#@lewdity: 85\na sheer lace bralette with delicate straps\n")
        self._write(f"{base}/resort/one-piece.txt", "#@lewdity: 30\na flowing kaftan in airy cotton\n")
        self._write("locations/female_casual_outfits_matching_locations.txt", "__locations/test_cafe__\n")
        self._write("locations/female_resort_matching_locations.txt", "__locations/test_beach__\n")
        self._write("locations/female_lingerie_matching_locations.txt", "__locations/test_diner__\n")
        self._write(
            "locations/test_cafe.txt",
            "in a sunlit corner cafe with oak tables\n",
        )
        self._write(
            "locations/test_diner.txt",
            "#@time: night\nin a dim diner under humming neon signs\n"
            "#@time: dawn\nin a misty diner at first light\n",
        )
        self._write("locations/test_beach.txt", "#@domain: waterfront\non a wide sandy beach with dune grass\n")
        self._write("jewellery/female_casual_jewellery.txt", "thin gold hoop earrings\n")
        self._write("accessories/female_casual_accessories.txt", "a woven canvas tote\n")
        self._write("brands/female_western_highstreet.txt", "a highstreet label\n")


class TestPersonaMeta(EngineFixture):
    def test_safe_persona_rejects_traversal_and_empties(self):
        self.assertEqual(_safe_persona("../evil"), "female")
        self.assertEqual(_safe_persona("a/b"), "female")
        self.assertEqual(_safe_persona("a\\b"), "female")
        self.assertEqual(_safe_persona(""), "female")
        self.assertEqual(_safe_persona(None), "female")
        self.assertEqual(_safe_persona("maya"), "maya")

    def test_tag_basename(self):
        self.assertEqual(_tag_basename("__characters/female/wardrobe/casual__"), "casual")
        self.assertEqual(_tag_basename("plain prose"), "")
        self.assertEqual(_tag_basename(""), "")

    def test_read_gender(self):
        self._make_maya()
        self.assertEqual(_read_gender(os.path.join(self.wildcards, "characters", "maya")), "female")
        self.assertEqual(_read_gender(os.path.join(self.temp_dir, "nowhere")), "female")
        self._write("characters/gil/gender.txt", "# comment\nmale\n")
        self.assertEqual(_read_gender(os.path.join(self.wildcards, "characters", "gil")), "male")

    def test_read_lewdity_file_comment_only_file_returns_none(self):
        self._make_maya()
        self._write("characters/maya/lewdity.txt", "# comment only\n# another comment\n")
        self.assertIsNone(_read_lewdity_file(os.path.join(self.wildcards, "characters", "maya")))
        self.assertEqual(_read_gender(os.path.join(self.temp_dir, "nowhere")), "female")
        self._write("characters/gil/gender.txt", "# comment\nmale\n")
        self.assertEqual(_read_gender(os.path.join(self.wildcards, "characters", "gil")), "male")

    def test_parse_lewdity_value(self):
        self.assertEqual(_parse_lewdity_value("15-85"), (15, 85))
        self.assertEqual(_parse_lewdity_value("40"), (0, 40))
        self.assertEqual(_parse_lewdity_value("90-10"), (10, 90))
        self.assertEqual(_parse_lewdity_value("15–85"), (15, 85))
        self.assertIsNone(_parse_lewdity_value("abc"))
        self.assertIsNone(_parse_lewdity_value("abc-def"))
        self.assertIsNone(_parse_lewdity_value("-"))
        self.assertEqual(_parse_lewdity_value("-5"), (0, 5))
        self.assertEqual(_parse_lewdity_value("120-140"), (120, 140))
        self.assertEqual(_parse_lewdity_value("1-2-3"), (1, 2))

    def test_read_lewdity_file(self):
        self._make_maya()
        self.assertEqual(_read_lewdity_file(os.path.join(self.wildcards, "characters", "maya")), (20, 80))
        self.assertIsNone(_read_lewdity_file(os.path.join(self.temp_dir, "nowhere")))
        self._write("characters/bad/lewdity.txt", "#@not a band\nnope\n")
        with self.assertLogs("ThatAIGod", level=logging.WARNING):
            self.assertIsNone(_read_lewdity_file(os.path.join(self.wildcards, "characters", "bad")))

    def test_resolve_lewdity_overrides(self):
        self._make_maya(lewdity=None)
        maya_dir = os.path.join(self.wildcards, "characters", "maya")
        self.assertIsNone(_resolve_lewdity(maya_dir, -1, -1))
        self.assertEqual(_resolve_lewdity(maya_dir, 30, -1), (30, 10**6))
        self.assertEqual(_resolve_lewdity(maya_dir, -1, 50), (0, 50))
        self.assertEqual(_resolve_lewdity(maya_dir, 90, 10), (10, 90))
        self._write("characters/maya/lewdity.txt", "20-80\n")
        self.assertEqual(_resolve_lewdity(maya_dir, -1, -1), (20, 80))
        self.assertEqual(_resolve_lewdity(maya_dir, 30, 40), (30, 40))

    def test_read_measurements_six_zones(self):
        self._make_maya()
        measurements = _read_measurements(os.path.join(self.wildcards, "characters", "maya"))
        self.assertEqual(measurements["bust"], "generous")
        self.assertEqual(measurements["thighs"], "toned")
        self.assertEqual(measurements["waist"], "slim")
        self.assertEqual(measurements["back"], "smooth")
        self.assertEqual(measurements["shoulders"], "graceful")
        self.assertEqual(measurements["hips"], "curved")
        self.assertEqual(
            _read_measurements(os.path.join(self.temp_dir, "nowhere"))["thighs"],
            "toned",
        )


class TestCameraExtraction(EngineFixture):
    def test_none_camera_shows_everything(self):
        regions, face_visible, view = _regions_from_camera(None)
        self.assertEqual(len(regions), 17)
        self.assertTrue(face_visible)
        self.assertEqual(view, "Front")

    def test_regions_filter_and_view(self):
        camera = {"regions": ["face", "chest", "skin"], "face_visible": False, "view": "Back"}
        regions, face_visible, view = _regions_from_camera(camera)
        self.assertEqual(regions, ["face", "chest", "skin"])
        self.assertFalse(face_visible)
        self.assertEqual(view, "Back")

    def test_invalid_regions_fall_back_to_all(self):
        regions, _face, _view = _regions_from_camera({"regions": []})
        self.assertEqual(len(regions), 17)
        regions, _face, _view = _regions_from_camera({"regions": "nope"})
        self.assertEqual(len(regions), 17)

    def test_context_occasion_key(self):
        context = _context("", ["face"])
        self.assertNotIn("occasion", context)
        context = _context("beach", ["face"])
        self.assertEqual(context["occasion"], {"beach"})

    def test_pose_context_asserts_facing_and_gaze(self):
        context = _pose_context({"regions": set()}, "Profile", False)
        self.assertEqual(context["facing"], {"profile"})
        self.assertEqual(context["gaze"], {"unavailable"})
        context = _pose_context({"regions": set()}, "Top Down", True)
        self.assertNotIn("facing", context)
        self.assertNotIn("gaze", context)


class TestComposeFit(EngineFixture):
    def test_declared_visible_zone_composes(self):
        import random

        rng = random.Random(1)
        measurements = {"bust": "generous", "back": "smooth", "thighs": "toned"}
        clause = _compose_fit(rng, frozenset({"bust"}), measurements, {"breasts"}, "female")
        self.assertIn("her generous bust", clause)
        self.assertNotIn("back", clause)

    def test_hidden_zone_skipped(self):
        import random

        rng = random.Random(1)
        clause = _compose_fit(rng, frozenset({"bust"}), {}, set(), "female")
        self.assertEqual(clause, "")

    def test_male_zone_word(self):
        import random

        rng = random.Random(1)
        clause = _compose_fit(rng, frozenset({"bust"}), {"bust": "broad"}, {"breasts"}, "male")
        self.assertIn("his broad chest", clause)

    def test_new_zones_live(self):
        import random

        rng = random.Random(1)
        clause = _compose_fit(rng, frozenset({"back", "shoulders", "thighs"}), {}, {"back", "shoulders", "thighs"}, "female")
        self.assertIn("back", clause)
        self.assertIn("shoulders", clause)
        self.assertIn("thighs", clause)


class TestWardrobeRouting(EngineFixture):
    def test_catalog_occasions(self):
        self._make_common()
        resolver = self._resolver()
        covered = _catalog_occasions(resolver, "characters/female/wardrobe")
        self.assertEqual(covered, {"casual", "travel", "home", "intimate", "boudoir", "beach", "pool", "resort"})
        self.assertEqual(_catalog_occasions(resolver, "characters/female/nowhere"), set())

    def test_wardrobe_plan_all_modes(self):
        self._make_maya()
        self._make_common()
        resolver = self._resolver()
        band = (20, 80)
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/maya", "female", WARDROBE_INTERNAL, band),
            [("characters/maya/wardrobe", None)],
        )
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/maya", "female", WARDROBE_COMPLETE, band),
            [("characters/female/wardrobe", None), ("characters/maya/wardrobe", None)],
        )
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/maya", "female", WARDROBE_EXTERNAL, band),
            [("characters/female/wardrobe", band), ("characters/maya/wardrobe", None)],
        )
        # Without a band a custom persona sticks to her own clothes.
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/maya", "female", WARDROBE_EXTERNAL, None),
            [("characters/maya/wardrobe", None)],
        )
        # The generic persona IS the common wardrobe; no second source.
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/female", "female", WARDROBE_EXTERNAL, band),
            [("characters/female/wardrobe", band)],
        )
        # Internal with no personal wardrobe falls back to common (band kept).
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/unknown", "female", WARDROBE_INTERNAL, band),
            [("characters/female/wardrobe", band)],
        )
        self.assertEqual(
            _wardrobe_plan(resolver, "characters/unknown", "female", WARDROBE_EXTERNAL, None),
            [("characters/female/wardrobe", None)],
        )

    def test_roll_occasion(self):
        self._make_common()
        resolver = self._resolver(seed=0)
        plan = _wardrobe_plan(resolver, "characters/female", "female", WARDROBE_EXTERNAL, (0, 100))
        rolled = _roll_occasion(resolver, plan, ["beach", "gym", "office"])
        self.assertEqual(rolled, "beach")
        self.assertEqual(_roll_occasion(resolver, plan, ["gym"]), "")
        self.assertEqual(_roll_occasion(resolver, [("characters/female/nowhere", None)], ["beach"]), "")

    def test_pick_category_routes_by_occasion(self):
        self._make_common()
        resolver = self._resolver(seed=0)
        context = _context("intimate", ["face"])
        self.assertEqual(_pick_category(resolver, "characters/female/wardrobe", context), "lingerie")
        unrestricted = _pick_category(resolver, "characters/female/wardrobe", _context("", ["face"]))
        self.assertIn(unrestricted, {"casual", "lingerie", "resort"})

    def test_pick_category_falls_back_when_occasion_uncovered(self):
        self._make_common()
        resolver = self._resolver(seed=0)
        with self.assertLogs("ThatAIGod", level=logging.WARNING):
            category = _pick_category(resolver, "characters/female/wardrobe", _context("wedding", ["face"]))
        self.assertIn(category, {"casual", "lingerie", "resort"})

    def test_pick_category_personal_falls_back_to_curated(self):
        self._make_maya()
        resolver = self._resolver(seed=0)
        with self.assertLogs("ThatAIGod", level=logging.WARNING):
            category = _pick_category(resolver, "characters/maya/wardrobe", _context("gym", ["face"]))
        self.assertEqual(category, "loungewear")

    def test_pick_category_nothing_available(self):
        self._write("characters/maya/wardrobe2/catalog.txt", "no tag lines here, just prose\n")
        resolver = self._resolver(seed=0)
        self.assertEqual(_pick_category(resolver, "characters/maya/wardrobe2", _context("gym", ["face"])), "")


class TestSlots(EngineFixture):
    def setUp(self):
        super().setUp()
        self._make_common()

    def test_resolve_slot_missing_file(self):
        self.assertEqual(_resolve_slot(self._resolver(), None, "characters/female/wardrobe/casual", "hats", None), ("", {}, []))

    def test_resolve_slot_band_filters_lines(self):
        resolver = self._resolver(seed=0)
        piece, directives, _tokens = _resolve_slot(resolver, None, "characters/female/wardrobe/casual", "tops", (0, 30))
        self.assertEqual(piece, "a pastel cotton tee in a soft weave")
        self.assertIn("bust", directives.get("fit", ()))
        piece, _directives, _tokens = _resolve_slot(resolver, None, "characters/female/wardrobe/casual", "tops", (50, 100))
        self.assertEqual(piece, "a daring crop top with thin straps")
        self.assertEqual(_resolve_slot(resolver, None, "characters/female/wardrobe/casual", "tops", (0, 10)), ("", {}, []))

    def test_resolve_slot_without_band_ignores_lewdity(self):
        resolver = self._resolver(seed=0)
        piece, _directives, _tokens = _resolve_slot(resolver, None, "characters/female/wardrobe/lingerie", "tops", None)
        self.assertEqual(piece, "a sheer lace bralette with delicate straps")

    def test_fill_slots_forces_one_piece_without_separates(self):
        resolver = self._resolver(seed=0)
        pieces, directives, _keywords = _fill_slots(
            resolver, None, "characters/female/wardrobe", "resort", ["face", "chest", "hips"], (0, 100)
        )
        self.assertEqual(pieces, ["a flowing kaftan in airy cotton"])
        self.assertEqual(len(directives), 1)

    def test_fill_slots_one_piece_probability(self):
        resolver = self._resolver(seed=0)
        with patch.object(resolver.rng, "random", return_value=0.0):
            pieces, _directives, _keywords = _fill_slots(
                resolver, None, "characters/female/wardrobe", "casual", ["shoulders", "chest", "hips", "feet"], None
            )
        joined = ", ".join(pieces)
        self.assertIn("denim overall dress", joined)
        self.assertNotIn("jeans", joined)

        resolver = self._resolver(seed=0)
        with patch.object(resolver.rng, "random", return_value=0.99):
            pieces, _directives, _keywords = _fill_slots(
                resolver, None, "characters/female/wardrobe", "casual", ["shoulders", "chest", "hips", "feet"], None
            )
        joined = ", ".join(pieces)
        self.assertIn("jeans", joined)
        self.assertIn("sneakers", joined)
        self.assertNotIn("denim overall dress", joined)

    def test_fill_slots_skips_hidden_regions(self):
        resolver = self._resolver(seed=0)
        with patch.object(resolver.rng, "random", return_value=0.99):
            pieces, _directives, _keywords = _fill_slots(
                resolver, None, "characters/female/wardrobe", "casual", ["shoulders", "chest"], None
            )
        joined = ", ".join(pieces)
        self.assertNotIn("jeans", joined)
        self.assertNotIn("sneakers", joined)

    def test_fill_slots_empty_category(self):
        self._write("characters/female/wardrobe/empty/tops.txt", "#@lewdity: 10\n")
        resolver = self._resolver(seed=0)
        pieces, directives, keywords = _fill_slots(resolver, None, "characters/female/wardrobe", "empty", ["face"], None)
        self.assertEqual(pieces, [])
        self.assertEqual(directives, [])
        self.assertEqual(keywords, [])


class TestKeywordDirectives(EngineFixture):
    def test_file_default_and_per_line_overrides(self):
        self._write(
            "characters/maya/kw.txt",
            "#@keyword: Default A, Default B\n# plain comment\nplain line\n#@keyword: Override X\noverridden line\n",
        )
        path = os.path.join(self.wildcards, "characters", "maya", "kw.txt")
        default_tokens, mapping = _parse_keyword_directives(path)
        self.assertEqual(default_tokens, ["Default A", "Default B"])
        self.assertEqual(mapping, {"overridden line": "Override X"})

    def test_missing_file_degrades_to_no_keywords(self):
        self.assertEqual(
            _parse_keyword_directives(os.path.join(self.wildcards, "nope.txt")),
            ([], {}),
        )

    def test_split_tokens_trims_and_drops_empties(self):
        self.assertEqual(_split_tokens(" A , B ,, C "), ["A", "B", "C"])

    def test_tag_tokens_title_case_from_realized_values(self):
        values = ["Deep merlot", "a bold floral print", "an espresso", "the off-white weave"]
        self.assertEqual(
            _tag_tokens(values),
            ["Deep Merlot", "Bold Floral Print", "Espresso", "Off-White Weave"],
        )

    def test_tag_tokens_skips_unusable_values(self):
        values = [
            "",
            "   ",
            "__nested/tag__",
            "{a|b}",
            "prose that is far too long to serve as a compact keyword token",
        ]
        self.assertEqual(_tag_tokens(values), [])

    def test_resolve_slot_collects_keywords_and_tag_tokens(self):
        self._write("colors/female_test_color.txt", "deep teal\n")
        self._write(
            "characters/female/wardrobe/tagged/tops.txt",
            "#@keyword: Tagged Top\n#@fit: bust\na soft blouse in __colors/female_test_color__\n",
        )
        resolver = self._resolver(seed=0)
        piece, _directives, tokens = _resolve_slot(
            resolver, None, "characters/female/wardrobe/tagged", "tops", None
        )
        self.assertIn("deep teal", piece)
        self.assertEqual(tokens, ["Tagged Top", "Deep Teal"])


class TestExtras(EngineFixture):
    def setUp(self):
        super().setUp()
        self._make_common()

    def test_roll_extras_probabilities(self):
        resolver = self._resolver(seed=0)
        with patch.object(resolver.rng, "random", side_effect=[0.0, 0.99, 0.99]):
            self.assertEqual(_roll_extras(resolver, "casual"), ["thin gold hoop earrings"])
        with patch.object(resolver.rng, "random", side_effect=[0.99, 0.99, 0.99]):
            self.assertEqual(_roll_extras(resolver, "casual"), [])
        with patch.object(resolver.rng, "random", side_effect=[0.0, 0.0, 0.0]):
            extras = _roll_extras(resolver, "casual")
        self.assertEqual(extras, ["thin gold hoop earrings", "a woven canvas tote"])
        self.assertLessEqual(len(extras), _EXTRA_CAP)

    def test_roll_extras_missing_pools_skip_silently(self):
        resolver = self._resolver(seed=0)
        with patch.object(resolver.rng, "random", return_value=0.0):
            self.assertEqual(_roll_extras(resolver, "lingerie"), [])

    def test_roll_extras_empty_category(self):
        self.assertEqual(_roll_extras(self._resolver(), ""), [])

    def test_roll_extras_pool_name_mapping(self):
        self._write("jewellery/female_saree_jewellery.txt", "gold jhumka earrings\n")
        resolver = self._resolver(seed=0)
        with patch.object(resolver.rng, "random", side_effect=[0.0, 0.99, 0.99]):
            self.assertEqual(_roll_extras(resolver, "sarees"), ["gold jhumka earrings"])


class TestBackground(EngineFixture):
    def setUp(self):
        super().setUp()
        self._make_common()

    def test_background_resolves_matching_location(self):
        resolver = self._resolver(seed=0)
        background = _background(resolver, "casual", "", "")
        self.assertEqual(background, "in a sunlit corner cafe with oak tables")

    def test_background_time_filter_prefers_tagged_lines(self):
        resolver = self._resolver(seed=0)
        # The diner taxonomy has only time-tagged lines: a night request
        # must resolve to the night line, never the dawn one.
        self.assertEqual(_background(resolver, "lingerie", "night", ""), "in a dim diner under humming neon signs")
        self.assertEqual(_background(resolver, "lingerie", "dawn", ""), "in a misty diner at first light")
        self.assertIn(_background(resolver, "lingerie", "", ""), {"in a dim diner under humming neon signs", "in a misty diner at first light"})

    def test_background_time_filter_on_universal_file_keeps_universal(self):
        resolver = self._resolver(seed=0)
        # The cafe taxonomy has one universal line and no time blocks: the
        # time filter cannot invent a variant, so the universal line serves.
        self.assertEqual(_background(resolver, "casual", "night", ""), "in a sunlit corner cafe with oak tables")

    def test_background_domain_filter_excludes(self):
        resolver = self._resolver(seed=0)
        # The cafe taxonomy has no #@domain header, so a domain filter drops
        # its only universal line?  No — unasserted keys never restrict; the
        # header-less line stays eligible.
        self.assertEqual(_background(resolver, "casual", "", "waterfront"), "in a sunlit corner cafe with oak tables")

    def test_background_domain_matching(self):
        resolver = self._resolver(seed=0)
        self.assertEqual(_background(resolver, "resort", "", "waterfront"), "on a wide sandy beach with dune grass")

    def test_background_missing_matching_file_warns(self):
        resolver = self._resolver(seed=0)
        with self.assertLogs("ThatAIGod", level=logging.WARNING):
            self.assertEqual(_background(resolver, "business", "", ""), "")

    def test_background_non_tag_matching_line_returns_empty(self):
        self._write("locations/female_business_matching_locations.txt", "just prose, not a tag\n")
        resolver = self._resolver(seed=0)
        self.assertEqual(_background(resolver, "business", "", ""), "")
        self.assertEqual(_tag_path("just prose, not a tag"), "")

    def test_background_without_category(self):
        self.assertEqual(_background(self._resolver(), "", "", ""), "")

    def test_background_empty_matching_file(self):
        self._write("locations/female_lingerie_matching_locations.txt", "#@occasion: intimate\n")
        resolver = self._resolver(seed=0)
        self.assertEqual(_background(resolver, "lingerie", "", ""), "")


class TestBuildCharacter(EngineFixture):
    def setUp(self):
        super().setUp()
        self._make_maya()
        self._make_common()

    def _build(self, **overrides):
        params = dict(
            wildcards_dir=self.wildcards,
            persona="maya",
            camera=None,
            occasion="casual",
            wardrobe_mode=WARDROBE_EXTERNAL,
            mode="Deterministic (Seed)",
            seed=0,
            lewdity_min=-1,
            lewdity_max=-1,
        )
        params.update(overrides)
        return build_character(**params)

    def test_output_shape(self):
        character = self._build()
        for key in (
            "type",
            "persona",
            "trigger",
            "occasion",
            "wardrobe_mode",
            "wardrobe_base",
            "lewdity",
            "regions",
            "face_visible",
            "attributes",
            "pose",
            "outfit_category",
            "outfit",
            "background",
            "subject",
            "description",
            "keywords",
        ):
            self.assertIn(key, character)
        self.assertEqual(character["type"], "character")
        self.assertEqual(character["persona"], "maya")
        self.assertEqual(character["trigger"], "maya_lora")
        self.assertEqual(character["lewdity"], (20, 80))

    def test_band_gates_common_wardrobe(self):
        character = self._build(lewdity_min=20, lewdity_max=30)
        self.assertEqual(character["wardrobe_base"], "characters/female/wardrobe")
        self.assertEqual(character["outfit_category"], "casual")
        self.assertIn("tee", character["outfit"])

    def test_narrow_band_falls_back_to_personal_wardrobe(self):
        character = self._build(occasion="intimate", lewdity_min=0, lewdity_max=10)
        # Lingerie (85) is out of band; maya's loungewear serves instead.
        self.assertEqual(character["wardrobe_base"], "characters/maya/wardrobe")
        self.assertEqual(character["outfit_category"], "loungewear")

    def test_internal_mode_uses_personal_wardrobe(self):
        character = self._build(occasion="home", wardrobe_mode=WARDROBE_INTERNAL)
        self.assertEqual(character["wardrobe_base"], "characters/maya/wardrobe")
        self.assertEqual(character["outfit_category"], "loungewear")

    def test_complete_mode_ignores_band(self):
        character = self._build(occasion="intimate", wardrobe_mode=WARDROBE_COMPLETE, lewdity_min=0, lewdity_max=10)
        self.assertEqual(character["wardrobe_base"], "characters/female/wardrobe")
        self.assertEqual(character["outfit_category"], "lingerie")
        self.assertIn("bralette", character["outfit"])

    def test_no_lewdity_sticks_to_own_wardrobe(self):
        lewdity_path = os.path.join(self.wildcards, "characters", "maya", "lewdity.txt")
        if os.path.exists(lewdity_path):
            os.remove(lewdity_path)
        character = self._build()
        self.assertIsNone(character["lewdity"])
        self.assertEqual(character["wardrobe_base"], "characters/maya/wardrobe")

    def test_subject_intro_universal_fallback(self):
        character = self._build(occasion="gym")
        self.assertEqual(character["attributes"]["intro"], "a poised woman with dark hair")

    def test_occasion_rolls_from_coverage(self):
        character = self._build(occasion="", occasion_options=["beach", "gym"])
        self.assertEqual(character["occasion"], "beach")
        self.assertEqual(character["outfit_category"], "resort")

    def test_subject_intro_occasion_blocks(self):
        beach = self._build(occasion="beach")
        self.assertIn("beachgoer", beach["attributes"]["intro"])
        office = self._build(occasion="office")
        self.assertIn("professional", office["attributes"]["intro"])
        self.assertNotIn("beachgoer", office["description"])

    def test_camera_stripping_and_profile_substitution(self):
        camera = {"regions": ["face", "chest"], "face_visible": True, "view": "Front"}
        character = self._build(camera=camera)
        self.assertIn("oval face", character["description"])
        self.assertNotIn("braid", character["description"])
        profile_cam = {"regions": ["face"], "face_visible": True, "view": "Profile"}
        character = self._build(camera=profile_cam)
        self.assertIn("fine-boned profile", character["description"])

    def test_pose_respects_facing_and_falls_back(self):
        camera = {"regions": ["face"], "face_visible": True, "view": "Back"}
        character = self._build(camera=camera)
        # No back-facing pose line exists; the fallback still yields a pose.
        self.assertTrue(character["pose"])

    def test_pose_fallback_blocks_gaze_when_face_hidden(self):
        camera = {"regions": ["face"], "face_visible": False, "view": "Back"}
        character = self._build(camera=camera)
        # No back-facing line and the face is out of frame: the fallback pose
        # resolves under the gaze-blocked context and never meets the lens.
        self.assertTrue(character["pose"])
        self.assertNotIn("lens", character["pose"])

    def test_plan_base_without_category_falls_to_next(self):
        # A common catalog with no tag lines routes nothing; the personal
        # wardrobe later in the plan serves instead.
        self._write("characters/female/wardrobe/catalog.txt", "no categories here, just prose\n")
        character = self._build(occasion="home")
        self.assertEqual(character["wardrobe_base"], "characters/maya/wardrobe")
        self.assertEqual(character["outfit_category"], "loungewear")

    def test_outfit_context_gates_attributes(self):
        self._write("characters/maya/hair.txt", "#@outfit: lingerie\nhair pinned up elegantly\n")
        lingerie = self._build(occasion="intimate", wardrobe_mode=WARDROBE_COMPLETE)
        self.assertIn("pinned up", lingerie["description"])
        casual = self._build(occasion="casual")
        self.assertNotIn("pinned up", casual["description"])

    def test_background_separate_from_description(self):
        character = self._build()
        self.assertEqual(character["background"], "in a sunlit corner cafe with oak tables")
        self.assertNotIn("cafe", character["description"])
        self.assertNotIn("cafe", character["keywords"])

    def test_keywords_are_camera_style_tokens(self):
        character = self._build(occasion="casual")
        self.assertEqual(character["keywords"], "Solo, Perfect Eyes, Bindi")
        # The prose lives in the description only.
        self.assertNotIn("oval", character["keywords"])
        self.assertNotIn("weave", character["keywords"])

    def test_background_with_time_filter(self):
        character = build_character(
            wildcards_dir=self.wildcards,
            persona="female",
            camera=None,
            occasion="intimate",
            wardrobe_mode=WARDROBE_EXTERNAL,
            mode="Deterministic (Seed)",
            seed=0,
            time_of_day="night",
        )
        self.assertEqual(character["background"], "in a dim diner under humming neon signs")

    def test_fit_clause_uses_measurements(self):
        camera = {"regions": ["face", "chest", "breasts"], "face_visible": True, "view": "Front"}
        character = self._build(camera=camera, seed=3)
        self.assertIn("generous bust", character["outfit"])

    def test_no_outfit_available_warns(self):
        # Internal mode with a category whose only slot file has no garment
        # lines: nothing can be dressed, but the category WAS routed, so no
        # "no category routed" warning — the outfit is simply empty.
        self._write("characters/maya/wardrobe/loungewear/tops.txt", "#@lewdity: 10\n")
        character = build_character(
            wildcards_dir=self.wildcards,
            persona="maya",
            camera=None,
            occasion="home",
            wardrobe_mode=WARDROBE_INTERNAL,
            mode="Deterministic (Seed)",
            seed=0,
        )
        self.assertEqual(character["outfit_category"], "")
        self.assertEqual(character["outfit"], "")
        self.assertEqual(character["background"], "")
        self.assertEqual(character["keywords"], "Solo, Perfect Eyes, Bindi")

    def test_no_category_routed_warns(self):
        # A wardrobe whose catalog has no tag lines routes nothing at all.
        self._write("characters/maya/wardrobe/catalog.txt", "no categories here, just prose\n")
        with self.assertLogs("ThatAIGod", level=logging.WARNING):
            character = build_character(
                wildcards_dir=self.wildcards,
                persona="maya",
                camera=None,
                occasion="home",
                wardrobe_mode=WARDROBE_INTERNAL,
                mode="Deterministic (Seed)",
                seed=0,
            )
        self.assertEqual(character["outfit_category"], "")

    def test_extras_ride_the_outfit(self):
        resolver = self._resolver(seed=1)
        with patch.object(resolver.rng, "random", side_effect=[0.0, 0.0, 0.0]):
            character = build_character(
                wildcards_dir=self.wildcards,
                persona="female",
                camera=None,
                occasion="casual",
                wardrobe_mode=WARDROBE_EXTERNAL,
                mode="Deterministic (Seed)",
                seed=1,
                resolver=resolver,
            )
        self.assertIn("gold hoop earrings", character["outfit"])
        self.assertIn("canvas tote", character["outfit"])
        self.assertNotIn("highstreet label", character["outfit"])


class TestWardrobeModeConstants(unittest.TestCase):
    def test_mode_values(self):
        self.assertEqual(
            WARDROBE_MODES,
            (WARDROBE_EXTERNAL, WARDROBE_INTERNAL, WARDROBE_COMPLETE),
        )
        self.assertEqual(WARDROBE_EXTERNAL, "Use External Wardrobe")
        self.assertEqual(WARDROBE_INTERNAL, "Use Internal Wardrobe")
        self.assertEqual(WARDROBE_COMPLETE, "Use Complete Wardrobe")


if __name__ == "__main__":
    unittest.main()
