"""Tests for the pure character engine in ``_character_core.py``."""

import os
import tempfile
import unittest
from typing import Any
from unittest import mock

import _character_core as core
from _character_core import build_character
from _wildcard_core import WildcardResolver

_PACK_WILDCARDS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "wildcards")


class FakeRng:
    """Deterministic stand-in RNG for forcing one-piece substitution branches."""

    def __init__(self, random_value: float) -> None:
        self.random_value = random_value

    def random(self) -> float:
        return self.random_value

    def choice(self, seq: list) -> object:
        return seq[0]

    def shuffle(self, seq: list) -> None:
        return None


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


def _make_persona(tmp: TmpWildcards, name: str = "tester") -> None:
    base = f"characters/{name}"
    tmp.write(f"{base}/subject_intro.txt", "Tester, a fictional subject")
    tmp.write(f"{base}/face.txt", "a face with gentle features")
    tmp.write(f"{base}/hair.txt", "short dark hair")
    tmp.write(f"{base}/neck.txt", "a slender neck")
    tmp.write(f"{base}/shoulders.txt", "soft shoulders")
    tmp.write(f"{base}/body.txt", "a lean torso")
    tmp.write(f"{base}/arms.txt", "toned arms")
    tmp.write(f"{base}/legs.txt", "long legs")
    tmp.write(f"{base}/feet.txt", "small feet")
    tmp.write(f"{base}/pose.txt", "standing with weight on one hip")


def _make_persona_wardrobe(tmp: TmpWildcards, name: str = "tester") -> None:
    base = f"characters/{name}/wardrobe"
    tmp.write(f"{base}/catalog.txt", f"__characters/{name}/wardrobe/signature__")
    tmp.write(f"{base}/signature/tops.txt", "a fitted top")
    tmp.write(f"{base}/signature/bottoms.txt", "tailored trousers")
    tmp.write(f"{base}/signature/shoes.txt", "leather shoes")
    tmp.write(f"{base}/signature/accessories.txt", "a delicate necklace")


def _make_common_wardrobe(tmp: TmpWildcards) -> None:
    tmp.write("characters/female/wardrobe/catalog.txt", "__characters/female/wardrobe/business__\n__characters/female/wardrobe/swimwear__")
    tmp.write("characters/female/wardrobe/business.txt", "#@occasion: office, formal, wedding\nbusiness outfit")
    tmp.write("characters/female/wardrobe/swimwear.txt", "#@occasion: beach, pool, resort\nswimwear outfit")
    tmp.write("characters/female/wardrobe/business/tops.txt", "a blazer and blouse")
    tmp.write("characters/female/wardrobe/business/bottoms.txt", "a pencil skirt")
    tmp.write("characters/female/wardrobe/business/shoes.txt", "court heels")
    tmp.write("characters/female/wardrobe/swimwear/one-piece.txt", "a black one-piece swimsuit")
    tmp.write("characters/female/wardrobe/swimwear/shoes.txt", "sandals")


def _full_camera() -> dict:
    return {
        "type": "camera",
        "regions": [
            "face",
            "hair",
            "neck",
            "shoulders",
            "chest",
            "back",
            "breasts",
            "navel",
            "arms",
            "hands",
            "waist",
            "hips",
            "buttocks",
            "thighs",
            "legs",
            "feet",
            "skin",
        ],
        "face_visible": True,
        "view": "Front",
    }


class TestSafePersona(unittest.TestCase):
    def test_normal_name_passes_through(self):
        self.assertEqual(core._safe_persona("Rohini Smirnova"), "Rohini Smirnova")

    def test_empty_falls_back(self):
        self.assertEqual(core._safe_persona(""), "female")
        self.assertEqual(core._safe_persona(None), "female")

    def test_traversal_rejected(self):
        self.assertEqual(core._safe_persona("../evil"), "female")
        self.assertEqual(core._safe_persona("..\\evil"), "female")
        self.assertEqual(core._safe_persona("a/b"), "female")
        self.assertEqual(core._safe_persona("a\\b"), "female")

    def test_hidden_name_rejected(self):
        self.assertEqual(core._safe_persona(".hidden"), "female")

    def test_whitespace_stripped(self):
        self.assertEqual(core._safe_persona("  tester  "), "tester")


class TestTagBasename(unittest.TestCase):
    def test_tag_with_slashes(self):
        self.assertEqual(core._tag_basename("__wardrobe/female/casual__"), "casual")

    def test_tag_with_spaces(self):
        self.assertEqual(core._tag_basename("__characters/Rohini Smirnova/wardrobe/signature__"), "signature")

    def test_tag_with_backslashes(self):
        self.assertEqual(core._tag_basename("__wardrobe\\female\\casual__"), "casual")

    def test_non_tag_line(self):
        self.assertEqual(core._tag_basename("a plain outfit line"), "")
        self.assertEqual(core._tag_basename(""), "")


class TestReadGender(unittest.TestCase):
    def test_missing_file_defaults_female(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(core._read_gender(d), "female")

    def test_comment_only_defaults_female(self):
        with TmpWildcards() as tmp:
            tmp.write("x/gender.txt", "# comment only\n")
            self.assertEqual(core._read_gender(os.path.join(tmp.dir, "x")), "female")

    def test_reads_first_value(self):
        with TmpWildcards() as tmp:
            tmp.write("x/gender.txt", "# comment\nmale\n")
            self.assertEqual(core._read_gender(os.path.join(tmp.dir, "x")), "male")

    def test_case_normalised(self):
        with TmpWildcards() as tmp:
            tmp.write("x/gender.txt", "Female\n")
            self.assertEqual(core._read_gender(os.path.join(tmp.dir, "x")), "female")


class TestRegionsFromCamera(unittest.TestCase):
    def test_none_means_all(self):
        regions, fv, view = core._regions_from_camera(None)
        self.assertEqual(regions, list(core._ALL_CAMERA_REGIONS))
        self.assertTrue(fv)
        self.assertEqual(view, "Front")

    def test_non_dict_means_all(self):
        regions, _fv, _view = core._regions_from_camera("nope")
        self.assertEqual(regions, list(core._ALL_CAMERA_REGIONS))

    def test_invalid_regions_types_mean_all(self):
        for bad in ("face", None, 42):
            regions, _fv, _view = core._regions_from_camera({"regions": bad})
            self.assertEqual(regions, list(core._ALL_CAMERA_REGIONS))

    def test_empty_regions_mean_all(self):
        regions, _fv, _view = core._regions_from_camera({"regions": []})
        self.assertEqual(regions, list(core._ALL_CAMERA_REGIONS))

    def test_unknown_names_only_mean_all(self):
        regions, _fv, _view = core._regions_from_camera({"regions": ["bogus"]})
        self.assertEqual(regions, list(core._ALL_CAMERA_REGIONS))

    def test_subset_preserves_canonical_order(self):
        regions, fv, view = core._regions_from_camera(
            {"regions": ["legs", "face", "feet"], "face_visible": True, "view": "3/4 Front"}
        )
        self.assertEqual(regions, ["face", "legs", "feet"])
        self.assertTrue(fv)
        self.assertEqual(view, "3/4 Front")

    def test_face_visibility_and_view_extracted(self):
        _regions, fv, view = core._regions_from_camera({"regions": ["face"], "face_visible": False, "view": "Back"})
        self.assertFalse(fv)
        self.assertEqual(view, "Back")


class TestContext(unittest.TestCase):
    def test_with_occasion(self):
        self.assertEqual(core._context("office", ["face"]), {"regions": {"face"}, "occasion": {"office"}})

    def test_unrestricted_omits_occasion(self):
        self.assertEqual(core._context("", ["face"]), {"regions": {"face"}})


class TestResolveAttribute(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._resolve_attribute(resolver, "characters/tester", "nose", {}), "")

    def test_resolves_existing_file(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            resolver = WildcardResolver(tmp.dir)
            value = core._resolve_attribute(resolver, "characters/tester", "hair", {})
            self.assertEqual(value, "short dark hair")


class TestWardrobeBase(unittest.TestCase):
    def test_persona_wardrobe_wins(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._wardrobe_base(resolver, "characters/tester", "female", True), "characters/tester/wardrobe")

    def test_common_allowed_without_persona_wardrobe(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._wardrobe_base(resolver, "characters/tester", "female", True), "characters/female/wardrobe")

    def test_common_disallowed_without_persona_wardrobe(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertIsNone(core._wardrobe_base(resolver, "characters/tester", "female", False))


class TestPickCategory(unittest.TestCase):
    def test_catalog_tag_line(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_category(resolver, "characters/tester/wardrobe", {}), "signature")

    def test_occasion_filters_common_catalog(self):
        with TmpWildcards() as tmp:
            _make_common_wardrobe(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_category(resolver, "characters/female/wardrobe", {"occasion": {"beach"}}), "swimwear")

    def test_file_fallback_without_tag(self):
        with TmpWildcards() as tmp:
            _make_common_wardrobe(tmp)
            tmp.write("characters/female/wardrobe/catalog.txt", "a plain non-tag line")
            resolver = WildcardResolver(tmp.dir)
            category = core._pick_category(resolver, "characters/female/wardrobe", {"occasion": {"office"}})
            self.assertEqual(category, "business")

    def test_nothing_eligible_returns_empty(self):
        with TmpWildcards() as tmp:
            _make_common_wardrobe(tmp)
            resolver = WildcardResolver(tmp.dir)
            self.assertEqual(core._pick_category(resolver, "characters/female/wardrobe", {"occasion": {"costume"}}), "")


class TestFillSlots(unittest.TestCase):
    def _resolver_with(self, tmp: TmpWildcards, random_value: float | None = None) -> WildcardResolver:
        resolver = WildcardResolver(tmp.dir, mode="Deterministic (Seed)", seed=1)
        if random_value is not None:
            resolver.rng = FakeRng(random_value)  # type: ignore[assignment]
        return resolver

    def test_slots_gated_by_visible_regions(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest", "waist", "arms", "face"}},
                "characters/tester/wardrobe",
                "signature",
                ["face", "shoulders", "chest", "arms", "waist"],
                False,
            )
            self.assertEqual(pieces, ["a fitted top", "a delicate necklace"])

    def test_bottoms_require_hips_or_legs(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"legs", "hips", "feet"}},
                "characters/tester/wardrobe",
                "signature",
                ["hips", "legs", "feet"],
                False,
            )
            self.assertEqual(pieces, ["tailored trousers", "leather shoes"])

    def test_one_piece_substitutes_top_and_bottom(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("characters/tester/wardrobe/signature/one-piece.txt", "a flowing gown")
            resolver = self._resolver_with(tmp, random_value=0.1)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"legs", "hips", "shoulders", "chest", "feet"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "chest", "hips", "legs", "feet"],
                False,
            )
            self.assertEqual(pieces, ["a flowing gown", "leather shoes"])

    def test_one_piece_empty_resolves_to_empty(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("characters/tester/wardrobe/signature/one-piece.txt", "## @occasion: never")
            resolver = self._resolver_with(tmp, random_value=0.1)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"hips", "legs", "shoulders", "feet"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "hips", "legs", "feet"],
                False,
            )
            self.assertEqual(pieces, ["leather shoes"])

    def test_one_piece_gets_modifier(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("characters/tester/wardrobe/signature/one-piece.txt", "a flowing gown")
            tmp.write("shared/garment-style.txt", "with flowing silk")
            resolver = self._resolver_with(tmp, random_value=0.1)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"hips", "legs", "shoulders", "chest", "feet"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "chest", "hips", "legs", "feet"],
                True,
            )
            self.assertEqual(pieces, ["a flowing gown, with flowing silk", "leather shoes"])

    def test_missing_slot_file_skipped(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"face"}},
                "characters/tester/wardrobe",
                "signature",
                ["face"],
                False,
            )
            self.assertEqual(pieces, ["a delicate necklace"])

    def test_slot_file_missing_returns_empty(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            resolver = self._resolver_with(tmp, random_value=0.9)
            value = core._resolve_slot(
                resolver,
                {"regions": {"face"}},
                "characters/tester/wardrobe/signature",
                "tops",
                False,
            )
            self.assertEqual(value, ("", {}))

    def test_slot_fully_filtered_skipped(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("characters/tester/wardrobe/signature/tops.txt", "#@occasion: never\nan occasion top")
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest"}, "occasion": {"office"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "chest"],
                False,
            )
            self.assertEqual(pieces, [])

    def test_modifier_applied_to_tagless_piece(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("shared/garment-style.txt", "with flowing silk")
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "chest"],
                True,
            )
            self.assertEqual(pieces, ["a fitted top, with flowing silk"])

    def test_modifier_disabled(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("shared/garment-style.txt", "with flowing silk")
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "chest"],
                False,
            )
            self.assertEqual(pieces, ["a fitted top"])

    def test_modifier_skipped_for_inline_tag(self):
        with TmpWildcards() as tmp:
            tmp.write("characters/tester/wardrobe/catalog.txt", "__characters/tester/wardrobe/sig__")
            tmp.write("characters/tester/wardrobe/sig/tops.txt", "a dress, __shared/colors__")
            tmp.write("shared/colors.txt", "crimson")
            tmp.write("shared/garment-style.txt", "with flowing silk")
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest"}},
                "characters/tester/wardrobe",
                "sig",
                ["shoulders", "chest"],
                True,
            )
            self.assertEqual(pieces, ["a dress, crimson"])

    def test_modifier_missing_file(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest"}},
                "characters/tester/wardrobe",
                "signature",
                ["shoulders", "chest"],
                True,
            )
            self.assertEqual(pieces, ["a fitted top"])

    def test_modifier_not_applied_to_accessories(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("shared/garment-style.txt", "with flowing silk")
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"face", "neck", "hands"}},
                "characters/tester/wardrobe",
                "signature",
                ["face", "neck", "hands"],
                True,
            )
            self.assertEqual(pieces, ["a delicate necklace"])

    def test_inline_choices_expanded(self):
        with TmpWildcards() as tmp:
            tmp.write("characters/tester/wardrobe/catalog.txt", "__characters/tester/wardrobe/sig__")
            tmp.write("characters/tester/wardrobe/sig/tops.txt", "a {silk|wool} top")
            resolver = self._resolver_with(tmp, random_value=0.9)
            pieces = core._fill_slots(
                resolver,
                {"regions": {"shoulders", "chest"}},
                "characters/tester/wardrobe",
                "sig",
                ["shoulders", "chest"],
                False,
            )
            self.assertIn(pieces[0], ("a silk top", "a wool top"))


class TestBuildCharacter(unittest.TestCase):
    def test_no_camera_describes_everything(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            result = build_character(tmp.dir, "tester", None, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["type"], "character")
            self.assertEqual(result["persona"], "tester")
            self.assertEqual(result["regions"], list(core._ALL_CAMERA_REGIONS))
            self.assertIn("long legs", result["description"])
            self.assertEqual(result["pose"], "standing with weight on one hip")

    def test_camera_strips_hidden_regions(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            camera = {"regions": ["face", "hair", "neck", "shoulders"], "face_visible": True, "view": "Front"}
            result = build_character(tmp.dir, "tester", camera, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["attributes"]["legs"], "")
            self.assertEqual(result["attributes"]["body"], "")
            self.assertIn("gentle features", result["description"])

    def test_profile_view_substitutes_profile_for_face(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("characters/tester/profile.txt", "a delicate side profile")
            camera = {"regions": ["face", "hair"], "face_visible": True, "view": "Profile"}
            result = build_character(tmp.dir, "tester", camera, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["attributes"]["face"], "")
            self.assertEqual(result["attributes"]["profile"], "a delicate side profile")

    def test_profile_view_without_profile_file_skips_face(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            camera = {"regions": ["face"], "face_visible": True, "view": "Profile"}
            result = build_character(tmp.dir, "tester", camera, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["attributes"]["face"], "")
            self.assertEqual(result["attributes"]["profile"], "")

    def test_missing_attributes_stay_empty(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            result = build_character(tmp.dir, "tester", None, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["attributes"]["buttocks"], "")
            self.assertEqual(result["attributes"]["navel"], "")

    def test_persona_wardrobe_used_and_slots_gated(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            camera = {
                "regions": ["face", "hair", "neck", "shoulders", "chest", "arms", "waist", "skin"],
                "face_visible": True,
                "view": "Front",
            }
            result = build_character(tmp.dir, "tester", camera, "casual", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["outfit_category"], "signature")
            self.assertNotIn("tailored trousers", result["outfit"])
            self.assertIn("a fitted top", result["outfit"])

    def test_common_wardrobe_fallback_with_gender_file(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            tmp.write("characters/tester/gender.txt", "female")
            camera = _full_camera()
            result = build_character(tmp.dir, "tester", camera, "office", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["outfit_category"], "business")
            self.assertIn("a blazer and blouse", result["outfit"])

    def test_common_wardrobe_default_gender_female(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(tmp.dir, "tester", camera, "beach", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["outfit_category"], "swimwear")
            self.assertIn("one-piece swimsuit", result["outfit"])

    def test_common_wardrobe_disallowed_yields_no_outfit(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(tmp.dir, "tester", camera, "office", False, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["outfit_category"], "")
            self.assertEqual(result["outfit"], "")

    def test_occasion_none_eligible_yields_no_outfit(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(tmp.dir, "tester", camera, "costume", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["outfit_category"], "")
            self.assertEqual(result["outfit"], "")

    def test_unrestricted_occasion_allows_any_category(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(tmp.dir, "tester", camera, "", True, False, "Deterministic (Seed)", 1)
            self.assertIn(result["outfit_category"], ("business", "swimwear"))
            self.assertEqual(result["occasion"], "")

    def test_occasion_roll_on_unrestricted_with_options(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(
                tmp.dir,
                "tester",
                camera,
                "",
                True,
                False,
                "Deterministic (Seed)",
                1,
                occasion_options=["office", "beach", "festival"],
            )
            self.assertIn(result["occasion"], ("office", "beach"))
            self.assertNotEqual(result["outfit"], "")
            self.assertIn(result["outfit_category"], ("business", "swimwear"))

    def test_occasion_roll_never_selects_uncovered(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            for seed in range(10):
                result = build_character(
                    tmp.dir,
                    "tester",
                    camera,
                    "",
                    True,
                    False,
                    "Deterministic (Seed)",
                    seed,
                    occasion_options=["office", "beach", "festival", "costume"],
                )
                self.assertIn(result["occasion"], ("office", "beach"))

    def test_occasion_roll_uncovered_only_stays_unrestricted(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(
                tmp.dir,
                "tester",
                camera,
                "",
                True,
                False,
                "Deterministic (Seed)",
                1,
                occasion_options=["festival"],
            )
            self.assertEqual(result["occasion"], "")
            self.assertIn(result["outfit_category"], ("business", "swimwear"))

    def test_occasion_roll_deterministic_same_seed(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            kwargs = {
                "camera": camera,
                "occasion": "",
                "use_common_wardrobe": True,
                "use_shared_modifiers": False,
                "mode": "Deterministic (Seed)",
                "seed": 7,
                "occasion_options": ["office", "beach"],
            }
            a = build_character(tmp.dir, "tester", **kwargs)
            b = build_character(tmp.dir, "tester", **kwargs)
            self.assertEqual(a["occasion"], b["occasion"])
            self.assertIn(a["occasion"], ("office", "beach"))

    def test_occasion_roll_skipped_without_wardrobe(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            camera = _full_camera()
            result = build_character(
                tmp.dir,
                "tester",
                camera,
                "",
                False,
                False,
                "Deterministic (Seed)",
                1,
                occasion_options=["office", "beach"],
            )
            self.assertEqual(result["occasion"], "")
            self.assertEqual(result["outfit"], "")

    def test_occasion_roll_skipped_for_agnostic_persona_wardrobe(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(
                tmp.dir,
                "tester",
                camera,
                "",
                True,
                False,
                "Deterministic (Seed)",
                1,
                occasion_options=["office", "beach"],
            )
            self.assertEqual(result["occasion"], "")

    def test_occasion_roll_no_repeat_variety(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_common_wardrobe(tmp)
            camera = _full_camera()
            occasions = {
                build_character(
                    tmp.dir,
                    "tester",
                    camera,
                    "",
                    True,
                    False,
                    "Random (No Repeat)",
                    0,
                    occasion_options=["office", "beach"],
                )["occasion"]
                for _ in range(16)
            }
            self.assertTrue(occasions <= {"office", "beach"})
            self.assertGreater(len(occasions), 1)

    def test_deterministic_same_seed_identical(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            kwargs = {
                "camera": _full_camera(),
                "occasion": "casual",
                "use_common_wardrobe": True,
                "use_shared_modifiers": True,
                "mode": "Deterministic (Seed)",
                "seed": 7,
            }
            a = build_character(tmp.dir, "tester", **kwargs)
            b = build_character(tmp.dir, "tester", **kwargs)
            self.assertEqual(a, b)

    def test_no_repeat_mode_runs_and_varies(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("shared/garment-style.txt", "with flowing silk\nwith crisp linen")
            outs = [
                build_character(tmp.dir, "tester", _full_camera(), "casual", True, True, "Random (No Repeat)", 0)
                for _ in range(5)
            ]
            self.assertTrue(all(o["type"] == "character" for o in outs))
            self.assertGreater(len({o["description"] for o in outs}), 1)

    def test_unknown_persona_is_graceful(self):
        result = build_character(_PACK_WILDCARDS, "does-not-exist", None, "", False, False, "Deterministic (Seed)", 1)
        self.assertEqual(result["subject"], "")
        self.assertEqual(result["outfit"], "")
        self.assertEqual(result["description"], "")

    def test_persona_flat_wardrobe_occasion_filtered(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            categories = {
                "business": "#@occasion: office, formal, wedding",
                "athletic": "#@occasion: athletic, gym, beach, travel",
                "swimwear": "#@occasion: beach, pool, resort",
            }
            tmp.write(
                "characters/tester/wardrobe/catalog.txt",
                "__characters/tester/wardrobe/business__\n"
                "__characters/tester/wardrobe/athletic__\n"
                "__characters/tester/wardrobe/swimwear__",
            )
            for category, header in categories.items():
                tmp.write(f"characters/tester/wardrobe/{category}.txt", f"{header}\n{category} wear")
                garment = "an athletic garment" if category == "athletic" else f"a {category} garment"
                tmp.write(f"characters/tester/wardrobe/{category}/tops.txt", garment)
            gym = build_character(tmp.dir, "tester", _full_camera(), "gym", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(gym["outfit_category"], "athletic")
            self.assertIn("an athletic garment", gym["outfit"])
            pool = build_character(tmp.dir, "tester", _full_camera(), "pool", True, False, "Deterministic (Seed)", 2)
            self.assertEqual(pool["outfit_category"], "swimwear")
            self.assertIn("a swimwear garment", pool["outfit"])
            office = build_character(tmp.dir, "tester", _full_camera(), "office", True, False, "Deterministic (Seed)", 3)
            self.assertEqual(office["outfit_category"], "business")
            self.assertIn("a business garment", office["outfit"])

    def test_keywords_contain_pieces_without_persona(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            camera = _full_camera()
            result = build_character(tmp.dir, "tester", camera, "casual", True, False, "Deterministic (Seed)", 1)
            self.assertNotIn("tester", result["keywords"])
            self.assertIn("Tester, a fictional subject", result["keywords"])
            self.assertIn("long legs", result["keywords"])

    def test_attributes_schema_is_fixed(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            result = build_character(tmp.dir, "tester", None, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(set(result["attributes"]), set(core._ALL_ATTRIBUTES))

    def test_persona_traversal_sanitised(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            result = build_character(tmp.dir, "../tester", None, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["persona"], "female")


class TestOccasionCoverage(unittest.TestCase):
    def test_no_wardrobe_returns_none(self):
        self.assertIsNone(core._occasion_coverage("some/dir", None))

    def test_missing_root_returns_none(self):
        with TmpWildcards() as tmp:
            self.assertIsNone(core._occasion_coverage(tmp.dir, "wardrobe/missing"))

    def test_untagged_category_means_universal(self):
        with TmpWildcards() as tmp:
            _make_common_wardrobe(tmp)
            tmp.write("characters/female/wardrobe/loose.txt", "anything goes")
            self.assertIsNone(core._occasion_coverage(tmp.dir, "characters/female/wardrobe"))

    def test_only_catalog_means_universal(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            self.assertIsNone(core._occasion_coverage(tmp.dir, "characters/tester/wardrobe"))

    def test_covered_occasions_collected(self):
        with TmpWildcards() as tmp:
            _make_common_wardrobe(tmp)
            coverage = core._occasion_coverage(tmp.dir, "characters/female/wardrobe")
            self.assertEqual(coverage, {"office", "formal", "wedding", "beach", "pool", "resort"})

    def test_full_coverage_persona_wardrobe_covers_every_occasion(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            categories = {
                "business": "office, formal, wedding",
                "casual": "casual, travel, home, beach, party, athletic, resort",
                "formal": "office, formal, wedding, party",
                "party": "party, wedding, festival, costume",
                "athletic": "athletic, gym, beach, travel",
                "swimwear": "beach, pool, resort",
                "lingerie": "intimate, boudoir",
                "traditional": "festival, wedding, traditional, party",
                "costume": "costume, party, festival",
            }
            base = "characters/tester/wardrobe"
            for category, occasions in categories.items():
                tmp.write(f"{base}/{category}.txt", f"#@occasion: {occasions}\n{category} wear")
            coverage = core._occasion_coverage(tmp.dir, "characters/tester/wardrobe")
            self.assertEqual(
                coverage,
                {
                    "casual", "office", "formal", "wedding", "party", "festival", "costume",
                    "athletic", "gym", "beach", "pool", "resort", "travel", "home",
                    "intimate", "boudoir", "traditional",
                },
            )

    def test_occasion_headers_ignore_other_directives(self):
        with TmpWildcards() as tmp:
            tmp.write("wardrobe/x/cat.txt", "#@outfit: formal\n#@occasion: beach, pool\nan outfit")
            values = core._occasion_headers(os.path.join(tmp.dir, "wardrobe/x/cat.txt"))
            self.assertEqual(values, {"beach", "pool"})

    def test_occasion_headers_missing_file_empty(self):
        self.assertEqual(core._occasion_headers(os.path.join("does", "not", "exist.txt")), set())

    def test_persona_category_folders_scanned_recursively(self):
        with TmpWildcards() as tmp:
            tmp.write("characters/x/wardrobe/catalog.txt", "__characters/x/wardrobe/sig__")
            tmp.write("characters/x/wardrobe/sig/tops.txt", "#@occasion: office, formal\na top")
            tmp.write("characters/x/wardrobe/sig/bottoms.txt", "#@occasion: beach\na bottom")
            tmp.write("characters/x/wardrobe/sig/catalog.txt", "#@occasion: never\nx")
            tmp.write("characters/x/wardrobe/sig/outer/tops.txt", "#@occasion: travel\na top")
            coverage = core._occasion_coverage(tmp.dir, "characters/x/wardrobe")
            self.assertEqual(coverage, {"office", "formal", "beach", "travel"})

    def test_subdirectory_unreadable_is_universal(self):
        with TmpWildcards() as tmp:
            tmp.write("characters/x/wardrobe/catalog.txt", "__characters/x/wardrobe/sig__")
            tmp.write("characters/x/wardrobe/sig/tops.txt", "#@occasion: office\na top")
            real_listdir = os.listdir

            def failing(directory: str) -> list:
                if directory.endswith(os.path.join("wardrobe", "sig")):
                    raise OSError("unreadable")
                return real_listdir(directory)

            with mock.patch("_character_core.os.listdir", side_effect=failing):
                coverage = core._occasion_coverage(tmp.dir, "characters/x/wardrobe")
            self.assertIsNone(coverage)

    def test_mixed_persona_categories_are_universal(self):
        with TmpWildcards() as tmp:
            tmp.write("characters/x/wardrobe/catalog.txt", "__characters/x/wardrobe/tagged__\n__characters/x/wardrobe/free__")
            tmp.write("characters/x/wardrobe/tagged/tops.txt", "#@occasion: office\na top")
            tmp.write("characters/x/wardrobe/free/bottoms.txt", "anything")
            self.assertIsNone(core._occasion_coverage(tmp.dir, "characters/x/wardrobe"))

    def test_common_wardrobe_slot_folders_not_scanned(self):
        with TmpWildcards() as tmp:
            _make_common_wardrobe(tmp)
            tmp.write("characters/female/wardrobe/business/tops.txt", "#@occasion: never\nuntagged slot")
            coverage = core._occasion_coverage(tmp.dir, "characters/female/wardrobe")
            self.assertEqual(coverage, {"office", "formal", "wedding", "beach", "pool", "resort"})


class TestPoseHonesty(unittest.TestCase):
    """Pose directives agree with the camera: facing follows the view, gaze
    only when the face is in frame."""

    _POSE = (
        "#@facing: front\n"
        "standing tall with one hand resting on her hip\n"
        "#@facing: profile\n"
        "walking slowly past, lost in thought\n"
        "#@facing: back, back three-quarter\n"
        "caught mid-turn, glancing over her shoulder\n"
        "#@facing: three-quarter\n"
        "poised with her weight on one leg\n"
        "#@facing: front\n"
        "#@gaze: into the lens\n"
        "seated upright, meeting the camera with a composed gaze\n"
    )

    def _build(self, tmp: TmpWildcards, camera: dict | None, seed: int = 1, pose: str | None = None) -> str:
        _make_persona(tmp)
        tmp.write("characters/tester/pose.txt", pose if pose is not None else self._POSE)
        return build_character(tmp.dir, "tester", camera, "casual", True, False, "Deterministic (Seed)", seed)["pose"]

    def test_front_view_picks_front_lines_only(self):
        with TmpWildcards() as tmp:
            pose = self._build(tmp, {"regions": ["face", "hair"], "view": "Front", "face_visible": True})
            self.assertIn(pose, ("standing tall with one hand resting on her hip", "seated upright, meeting the camera with a composed gaze"))

    def test_back_view_picks_back_lines_only(self):
        with TmpWildcards() as tmp:
            pose = self._build(tmp, {"regions": ["back"], "view": "Back", "face_visible": False})
            self.assertEqual(pose, "caught mid-turn, glancing over her shoulder")

    def test_profile_view_picks_profile_lines_only(self):
        with TmpWildcards() as tmp:
            pose = self._build(tmp, {"regions": ["face", "hair"], "view": "Profile", "face_visible": True})
            self.assertEqual(pose, "walking slowly past, lost in thought")

    def test_three_quarter_front_uses_three_quarter_vocabulary(self):
        with TmpWildcards() as tmp:
            pose = self._build(tmp, {"regions": ["face", "hair"], "view": "3/4 Front", "face_visible": True})
            self.assertEqual(pose, "poised with her weight on one leg")

    def test_gaze_lines_blocked_when_face_hidden(self):
        with TmpWildcards() as tmp:
            pose = self._build(
                tmp,
                {"regions": ["back"], "view": "Back", "face_visible": False},
                pose="plainly standing, not looking at the camera\n"
                "#@gaze: into the lens\n"
                "seated upright, meeting the camera with a composed gaze\n",
            )
            self.assertEqual(pose, "plainly standing, not looking at the camera")

    def test_gaze_lines_eligible_when_face_visible(self):
        with TmpWildcards() as tmp:
            pose = self._build(
                tmp,
                {"regions": ["face", "hair"], "view": "Front", "face_visible": True},
                pose="plainly standing, not looking at the camera\n"
                "#@gaze: into the lens\n"
                "seated upright, meeting the camera with a composed gaze\n",
            )
            self.assertIn(pose, ("seated upright, meeting the camera with a composed gaze", "plainly standing, not looking at the camera"))

    def test_no_pose_line_for_facing_degrades_gracefully(self):
        with TmpWildcards() as tmp:
            pose = self._build(
                tmp,
                {"regions": ["back"], "view": "Back", "face_visible": False},
                pose="#@facing: front\n"
                "standing tall with one hand resting on her hip\n",
            )
            self.assertEqual(pose, "standing tall with one hand resting on her hip")

    def test_fallback_never_reveals_gaze_lines_when_face_hidden(self):
        with TmpWildcards() as tmp:
            pose = self._build(
                tmp,
                {"regions": ["back"], "view": "Back", "face_visible": False},
                pose="#@facing: front\n"
                "standing tall with one hand resting on her hip\n"
                "#@facing: front\n"
                "#@gaze: into the lens\n"
                "seated upright, meeting the camera with a composed gaze\n",
            )
            self.assertEqual(pose, "standing tall with one hand resting on her hip")

    def test_no_camera_imposes_no_facing_gate(self):
        with TmpWildcards() as tmp:
            pose = self._build(tmp, None)
            self.assertIn(
                pose,
                (
                    "standing tall with one hand resting on her hip",
                    "seated upright, meeting the camera with a composed gaze",
                    "walking slowly past, lost in thought",
                    "caught mid-turn, glancing over her shoulder",
                    "poised with her weight on one leg",
                ),
            )

    def test_pose_deterministic_per_seed(self):
        with TmpWildcards() as tmp:
            a = self._build(tmp, {"regions": ["face", "hair"], "view": "Front", "face_visible": True}, seed=9)
            b = self._build(tmp, {"regions": ["face", "hair"], "view": "Front", "face_visible": True}, seed=9)
            self.assertEqual(a, b)


class TestFitProse(unittest.TestCase):
    """Garment fit clauses: measurements.txt adjectives + #@fit zones, gated by
    the visible camera regions."""

    _FIT_TOPS = (
        "#@fit: bust, waist\n"
        "a silk camisole\n"
    )

    def _outfit(
        self,
        tmp: TmpWildcards,
        camera: dict | None,
        seed: int = 1,
        measurements: str | None = None,
        tops: str | None = None,
    ) -> str:
        _make_persona(tmp)
        _make_persona_wardrobe(tmp)
        if measurements is not None:
            tmp.write("characters/tester/measurements.txt", measurements)
        if tops is not None:
            tmp.write("characters/tester/wardrobe/signature/tops.txt", tops)
        return build_character(tmp.dir, "tester", camera, "casual", True, False, "Deterministic (Seed)", seed)["outfit"]

    def test_fit_clause_composed_from_measurements(self):
        with TmpWildcards() as tmp:
            outfit = self._outfit(tmp, None, measurements="#@bust: generous\n#@waist: tiny\n", tops=self._FIT_TOPS)
            self.assertIn("silk camisole", outfit)
            self.assertRegex(outfit, r"(fitting snugly|loose|flowing softly|fitting comfortably) over her generous bust")
            self.assertRegex(outfit, r"(fitting snugly|loose|flowing softly|fitting comfortably) (over|at)?.*tiny waist")

    def test_fit_zone_gated_by_visibility(self):
        with TmpWildcards() as tmp:
            camera = {"regions": ["shoulders", "arms", "waist", "hips", "legs"], "view": "Front", "face_visible": True}
            outfit = self._outfit(tmp, camera, measurements="#@bust: generous\n", tops=self._FIT_TOPS)
            self.assertNotIn("bust", outfit)
            self.assertIn("waist", outfit)

    def test_no_fit_directive_means_no_clause(self):
        with TmpWildcards() as tmp:
            outfit = self._outfit(tmp, None)
            self.assertNotIn("fitting", outfit)
            self.assertNotIn("over her", outfit)

    def test_default_measurements_when_file_missing(self):
        with TmpWildcards() as tmp:
            outfit = self._outfit(tmp, None, tops=self._FIT_TOPS)
            self.assertRegex(outfit, r"over her (full|slim|curved) (bust|waist)")

    def test_multiple_zones_join_clauses(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write(
                "characters/tester/wardrobe/catalog.txt",
                "__characters/tester/wardrobe/signature__",
            )
            tmp.write(
                "characters/tester/wardrobe/signature/one-piece.txt",
                "#@fit: bust, waist, hips\n"
                "a flowing gown\n",
            )
            outfit = self._outfit(tmp, None, measurements="#@bust: generous\n#@waist: tiny\n#@hips: flared\n")
            self.assertIn("bust", outfit)
            self.assertIn("waist", outfit)
            self.assertIn("hips", outfit)

    def test_fit_deterministic_per_seed(self):
        with TmpWildcards() as tmp:
            a = self._outfit(tmp, None, seed=5, tops=self._FIT_TOPS)
            b = self._outfit(tmp, None, seed=5, tops=self._FIT_TOPS)
            self.assertEqual(a, b)

    def test_category_specific_style_deck_preferred(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write("shared/garment-style.txt", "in generic fabric\n")
            tmp.write("shared/garment-style-signature.txt", "in signature fabric\n")
            result = build_character(tmp.dir, "tester", None, "casual", True, True, "Deterministic (Seed)", 1)
            self.assertIn("in signature fabric", result["outfit"])
            self.assertNotIn("in generic fabric", result["outfit"])

    def test_male_pronoun_and_chest_wording(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("characters/tester/gender.txt", "male")
            outfit = self._outfit(
                tmp,
                None,
                tops="#@fit: bust\n"
                "a fitted shirt\n",
            )
            self.assertIn("over his", outfit)
            self.assertIn("chest", outfit)
            self.assertNotIn("over her", outfit)


class TestNudeState(unittest.TestCase):
    """The nude state replaces the outfit with the persona's region-tagged
    nude.txt — one pick per visible body block, never mentioning hidden
    zones."""

    _NUDE = (
        "fully nude\n"
        "#@regions: breasts\n"
        "her exposed bust with erect pink nipples\n"
        "#@regions: navel\n"
        "her flat stomach with a delicate navel\n"
        "#@regions: back\n"
        "fully nude from behind, her bare smooth back\n"
        "#@regions: thighs\n"
        "nude below the waist, smooth thighs\n"
        "#@regions: legs, feet\n"
        "her long toned legs\n"
    )

    def test_nude_state_replaces_outfit(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("characters/tester/nude.txt", self._NUDE)
            result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", 1, state="nude")
            self.assertEqual(result["state"], "nude")
            self.assertEqual(result["outfit_category"], "nude")
            self.assertIn("fully nude", result["outfit"])
            self.assertNotIn("a fitted top", result["outfit"])
            self.assertIn("fully nude", result["description"])
            self.assertIn("fully nude", result["keywords"])

    def test_nude_respects_visible_regions(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("characters/tester/nude.txt", self._NUDE)
            back_camera = {"regions": ["back", "buttocks", "thighs", "legs", "feet", "hair"], "view": "Back", "face_visible": False}
            result = build_character(tmp.dir, "tester", back_camera, "casual", True, False, "Deterministic (Seed)", 1, state="nude")
            self.assertNotIn("nipples", result["outfit"])
            self.assertIn("from behind", result["outfit"])
            self.assertIn("toned legs", result["outfit"])
            upper_only = {"regions": ["face", "hair", "neck", "shoulders", "chest", "breasts", "navel", "arms", "hands", "waist", "hips", "skin"], "view": "Front", "face_visible": True}
            result2 = build_character(tmp.dir, "tester", upper_only, "casual", True, False, "Deterministic (Seed)", 1, state="nude")
            self.assertIn("nipples", result2["outfit"])
            self.assertNotIn("toned legs", result2["outfit"])

    def test_nude_state_without_nude_file(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", 1, state="nude")
            self.assertEqual(result["outfit"], "")
            self.assertEqual(result["outfit_category"], "nude")

    def test_default_state_stays_dressed(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["state"], "dressed")
            self.assertNotEqual(result["outfit_category"], "nude")


class TestStateMachine(unittest.TestCase):
    """State axis: explicit states, Auto weights, garment mishap/slip phrases,
    per-garment conditions."""

    def _build(self, tmp: TmpWildcards, state: str = "", seed: int = 1, occasion: str = "casual", **kwargs: Any) -> dict[str, Any]:
        _make_persona(tmp)
        _make_persona_wardrobe(tmp)
        return build_character(
            tmp.dir,
            "tester",
            None,
            occasion,
            True,
            False,
            "Deterministic (Seed)",
            seed,
            state=state,
            **kwargs,
        )

    def test_explicit_states_resolve_directly(self):
        with TmpWildcards() as tmp:
            for state in ("dressed", "revealing", "mishap", "slipping", "nude"):
                result = self._build(tmp, state=state)
                self.assertEqual(result["state"], state)

    def test_auto_rolls_occasion_weighted(self):
        with TmpWildcards() as tmp:
            professional = self._build(tmp, occasion="office")
            self.assertEqual(professional["state"], "dressed")
            states = {build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", seed)["state"] for seed in range(60)}
            self.assertLessEqual(states, set(core._STATE_VALUES))
            intimate_states = {
                build_character(tmp.dir, "tester", None, "intimate", True, False, "Deterministic (Seed)", seed)["state"] for seed in range(60)
            }
            self.assertIn("nude", intimate_states)

    def test_state_options_subset_rolls_within(self):
        with TmpWildcards() as tmp:
            seen = set()
            for seed in range(30):
                result = build_character(
                    tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", seed, state_options=["dressed", "mishap"]
                )
                seen.add(result["state"])
            self.assertLessEqual(seen, {"dressed", "mishap"})
            self.assertEqual(len(seen), 2)

    def test_garment_mishap_phrase_wins_over_deck(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write(
                "characters/tester/wardrobe/signature/tops.txt",
                "#@mishap: her blouse slipping off one shoulder\n"
                "a silk blouse\n",
            )
            result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", 1, state="mishap")
            self.assertIn("with her blouse slipping off one shoulder", result["outfit"])

    def test_generic_mishap_deck_fallback(self):
        with TmpWildcards() as tmp:
            tmp.write("shared/state-mishap.txt", "the hem riding up her thighs\n")
            result = self._build(tmp, state="mishap")
            self.assertIn("with the hem riding up her thighs", result["outfit"])

    def test_slipping_state_uses_slip_deck(self):
        with TmpWildcards() as tmp:
            tmp.write("shared/state-slip.txt", "the dress slipping down her hips, still covering her\n")
            result = self._build(tmp, state="slipping")
            self.assertIn("with the dress slipping down her hips", result["outfit"])

    def test_revealing_state_appends_revealing_clause(self):
        with TmpWildcards() as tmp:
            tmp.write("shared/state-revealing.txt", "the sheer fabric barely veiling her skin\n")
            result = self._build(tmp, state="revealing")
            self.assertIn("the sheer fabric barely veiling her skin", result["outfit"])

    def test_condition_applied_to_eligible_garment(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write(
                "characters/tester/wardrobe/signature/one-piece.txt",
                "#@condition: wet\n"
                "a swimsuit\n",
            )
            tmp.write("shared/state-condition.txt", "#@condition: wet\nclinging wet to her skin\n")
            found = False
            for seed in range(40):
                result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", seed)
                if "clinging wet" in result["outfit"]:
                    found = True
                    break
            self.assertTrue(found)

    def test_untagged_garment_never_gets_condition(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write(
                "characters/tester/wardrobe/signature/tops.txt",
                "a wool sweater\n",
            )
            tmp.write("shared/state-condition.txt", "#@condition: wet\nclinging wet to her skin\n")
            for seed in range(40):
                result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", seed)
                self.assertNotIn("clinging wet", result["outfit"])

    def test_outfit_directive_gates_attribute_variants(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            _make_persona_wardrobe(tmp)
            tmp.write(
                "characters/tester/hair.txt",
                "#@outfit: signature\n"
                "signature loose waves\n"
                "#@outfit: business\n"
                "business slick bun\n",
            )
            tmp.write(
                "characters/tester/wardrobe/catalog.txt",
                "__characters/tester/wardrobe/business__\n"
                "__characters/tester/wardrobe/signature__",
            )
            tmp.write("characters/tester/wardrobe/business.txt", "#@occasion: office, formal, wedding\nbusiness wear")
            tmp.write("characters/tester/wardrobe/business/tops.txt", "a blouse")
            business = build_character(tmp.dir, "tester", None, "office", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(business["attributes"]["hair"], "business slick bun")
            signature = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(signature["attributes"]["hair"], "signature loose waves")

    def test_state_clause_without_outfit_pieces(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("shared/state-mishap.txt", "the hem riding up her thighs\n")
            result = build_character(tmp.dir, "tester", None, "casual", True, False, "Deterministic (Seed)", 1, state="mishap")
            self.assertEqual(result["outfit"], "with the hem riding up her thighs")

    def test_state_deterministic_per_seed(self):
        with TmpWildcards() as tmp:
            a = self._build(tmp, seed=11)
            b = self._build(tmp, seed=11)
            self.assertEqual(a["state"], b["state"])
            self.assertEqual(a["outfit"], b["outfit"])


class TestTrigger(unittest.TestCase):
    def test_trigger_resolved_and_kept_out_of_prose(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("characters/tester/trigger.txt", "cha:pak:trigger\nan alternate trigger\n")
            result = build_character(tmp.dir, "tester", _full_camera(), "casual", True, False, "Deterministic (Seed)", 1)
            self.assertIn(result["trigger"], ("cha:pak:trigger", "an alternate trigger"))
            self.assertNotIn(result["trigger"], result["description"])
            self.assertNotIn(result["trigger"], result["keywords"])
            self.assertNotIn(result["trigger"], result["subject"])

    def test_missing_trigger_file_stays_empty(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            result = build_character(tmp.dir, "tester", None, "", True, False, "Deterministic (Seed)", 1)
            self.assertEqual(result["trigger"], "")

    def test_trigger_deterministic_per_seed(self):
        with TmpWildcards() as tmp:
            _make_persona(tmp)
            tmp.write("characters/tester/trigger.txt", "one\ntwo\nthree\n")
            a = build_character(tmp.dir, "tester", None, "", True, False, "Deterministic (Seed)", 5)
            b = build_character(tmp.dir, "tester", None, "", True, False, "Deterministic (Seed)", 5)
            self.assertEqual(a["trigger"], b["trigger"])


if __name__ == "__main__":
    unittest.main()
