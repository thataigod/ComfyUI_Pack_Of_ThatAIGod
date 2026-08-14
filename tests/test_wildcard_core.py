import logging
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _wildcard_core
from _wildcard_core import (
    _MAX_WILDCARD_ITERATIONS,
    _WILDCARD_PATTERN,
    WildcardResolver,
    _context_key,
)


class TestContextKey(unittest.TestCase):
    def test_empty_context_returns_empty_string(self):
        self.assertEqual(_context_key(None), "")
        self.assertEqual(_context_key({}), "")

    def test_context_serialised_deterministically(self):
        a = _context_key({"occasion": {"beach", "resort"}, "scale": {"wide"}})
        b = _context_key({"scale": {"wide"}, "occasion": {"resort", "beach"}})
        self.assertEqual(a, b)
        self.assertIn("beach", a)


class TestWildcardResolverCore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wildcards_dir = os.path.join(self.temp_dir, "wildcards")
        os.makedirs(self.wildcards_dir, exist_ok=True)
        WildcardResolver._file_index_cache.clear()
        WildcardResolver._file_mtimes.clear()
        WildcardResolver._annotations_cache.clear()
        WildcardResolver._deck_cache.clear()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create(self, rel_path, lines):
        path = os.path.join(self.wildcards_dir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def _resolver(self, mode="Deterministic (Seed)", seed=0):
        return WildcardResolver(self.wildcards_dir, mode=mode, seed=seed)

    def test_plain_text_passthrough(self):
        self.assertEqual(self._resolver().resolve("a cat on a mat"), "a cat on a mat")

    def test_empty_text(self):
        self.assertEqual(self._resolver().resolve(""), "")
        self.assertEqual(self._resolver().resolve(None), "")

    def test_simple_tag_resolved(self):
        self._create("colors.txt", ["red", "green", "blue"])
        result = self._resolver(seed=42).resolve("__colors__")
        self.assertIn(result, ["red", "green", "blue"])

    def test_deterministic_same_seed_same_result(self):
        self._create("colors.txt", ["red", "green", "blue"])
        r1 = self._resolver(seed=99).resolve("__colors__")
        r2 = self._resolver(seed=99).resolve("__colors__")
        self.assertEqual(r1, r2)

    def test_full_random_varies(self):
        self._create("colors.txt", [f"c{i}" for i in range(20)])
        results = set()
        for _ in range(20):
            results.add(self._resolver(mode="Full Random").resolve("__colors__"))
        self.assertGreater(len(results), 1)

    def test_nested_wildcards(self):
        self._create("primary.txt", ["__colors__"])
        self._create("colors.txt", ["red", "blue"])
        self.assertIn(self._resolver(seed=7).resolve("__primary__"), ["red", "blue"])

    def test_inline_choices(self):
        result = self._resolver(seed=3).resolve("a {red|green|blue} hat")
        self.assertIn(result, ["a red hat", "a green hat", "a blue hat"])

    def test_choice_with_empty_options_kept(self):
        self.assertEqual(self._resolver().resolve("{}"), "{}")

    def test_unresolvable_tag_vanishes(self):
        self.assertEqual(self._resolver().resolve("__nope__"), "")

    def test_unresolvable_tag_in_sentence(self):
        result = self._resolver().resolve("hello __nope__ world")
        self.assertIn("hello", result)
        self.assertIn("world", result)

    def test_cycle_terminates_at_iteration_cap(self):
        self._create("a.txt", ["__b__"])
        self._create("b.txt", ["__a__"])
        result = self._resolver().resolve("__a__")
        self.assertIn("__", result)

    def test_comments_and_blanks_ignored(self):
        self._create("colors.txt", ["# comment", "", "red", "# another"])
        result = self._resolver(seed=0).resolve("__colors__")
        self.assertEqual(result, "red")

    def test_resolve_respects_context_filter(self):
        self._create("beach.txt", ["#@occasion: beach", "sand and waves", "universal line"])
        resolver = self._resolver(seed=0)
        with_context = resolver.resolve("__beach__", {"occasion": {"beach"}})
        self.assertIn(with_context, ["sand and waves", "universal line"])
        resolver2 = self._resolver(seed=0)
        without = resolver2.resolve("__beach__", {"occasion": {"office"}})
        self.assertEqual(without, "")

    def test_directive_key_not_in_context_is_not_restrictive(self):
        self._create("item.txt", ["#@occasion: beach", "sun hat"])
        result = self._resolver(seed=0).resolve("__item__", {"scale": {"wide"}})
        self.assertEqual(result, "sun hat")

    def test_unknown_directive_key_warns(self):
        self._create("item.txt", ["#@mystery: x", "okay line"])
        with self.assertLogs("ThatAIGod", level=logging.WARNING) as captured:
            self._resolver().resolve("__item__")
        self.assertTrue(any("mystery" in m for m in captured.output))

    def test_character_object_directive_keys_are_known(self):
        self._create(
            "item.txt",
            [
                "#@time: golden hour",
                "#@location: outdoors",
                "#@facing: away",
                "#@gaze: into lens",
                "#@elevation: high angle",
                "#@awareness: unaware",
                "#@context: father-daughter",
                "#@preset: voyeur",
                "matching line",
            ],
        )
        resolver = self._resolver(seed=0)
        context = {
            "time": {"golden hour"},
            "location": {"outdoors"},
            "facing": {"away"},
            "gaze": {"into lens"},
            "elevation": {"high angle"},
            "awareness": {"unaware"},
            "context": {"father-daughter"},
            "preset": {"voyeur"},
        }
        self.assertEqual(resolver.resolve("__item__", context), "matching line")
        self.assertEqual(resolver.resolve("__item__", {"time": {"dawn"}}), "")

    def test_malformed_directive_ignored(self):
        self._create("item.txt", ["#@no-colon-here", "okay line"])
        result = self._resolver(seed=0).resolve("__item__")
        self.assertEqual(result, "okay line")

    def test_directives_accumulate_across_keys(self):
        self._create("item.txt", ["#@outfit: swimwear", "#@occasion: beach", "sand and waves"])
        resolver = self._resolver(seed=0)
        self.assertEqual(
            resolver.resolve("__item__", {"outfit": {"swimwear"}, "occasion": {"beach"}}),
            "sand and waves",
        )
        self.assertEqual(resolver.resolve("__item__", {"outfit": {"business"}, "occasion": {"beach"}}), "")
        self.assertEqual(resolver.resolve("__item__", {"outfit": {"swimwear"}, "occasion": {"office"}}), "")

    def test_repeated_directive_key_replaces_previous_value(self):
        self._create("item.txt", ["#@occasion: beach", "beach only", "#@occasion: office", "office only", "office too"])
        resolver = self._resolver(seed=0)
        self.assertEqual(resolver.resolve("__item__", {"occasion": {"beach"}}), "beach only")
        self.assertIn(resolver.resolve("__item__", {"occasion": {"office"}}), ["office only", "office too"])
        for seed in range(10):
            self.assertEqual(self._resolver(seed=seed).resolve("__item__", {"occasion": {"beach"}}), "beach only")

    def test_deep_filtering_drops_ineligible_category_lines(self):
        self._create("catalog.txt", ["__wardrobe/casual__", "__wardrobe/lingerie__"])
        self._create("wardrobe/casual.txt", ["#@occasion: casual, beach", "casual wear"])
        self._create("wardrobe/lingerie.txt", ["#@occasion: intimate", "lingerie"])
        resolver = self._resolver(seed=0)
        for _ in range(10):
            picked = resolver.pick_line("catalog", {"occasion": {"casual"}})
            self.assertEqual(picked, "__wardrobe/casual__")
        for _ in range(10):
            picked = self._resolver(seed=1).pick_line("catalog", {"occasion": {"intimate"}})
            self.assertEqual(picked, "__wardrobe/lingerie__")

    def test_deep_filter_keeps_line_when_reference_missing(self):
        self._create("catalog.txt", ["__missing/category__", "__other__"])
        self._create("other.txt", ["a line"])
        resolver = self._resolver(seed=0)
        picked = resolver.pick_line("catalog", {"occasion": {"anything"}})
        self.assertIn(picked, ["__missing/category__", "__other__"])

    def test_pick_line_missing_file_returns_empty(self):
        self.assertEqual(self._resolver().pick_line("no/such/file", None), "")

    def test_pick_line_fully_filtered_returns_empty(self):
        self._create("only.txt", ["#@occasion: beach", "sand"])
        self.assertEqual(self._resolver().pick_line("only", {"occasion": {"office"}}), "")

    def test_pick_line_returns_eligible_line(self):
        self._create("camera.txt", ["#@scale: wide", "wide shot"])
        result = self._resolver(seed=0).pick_line("camera", {"scale": {"wide"}})
        self.assertEqual(result, "wide shot")

    def test_pick_file_missing_dir_returns_none(self):
        self.assertIsNone(self._resolver().pick_file("scenes", None))

    def test_pick_file_no_eligible_returns_none(self):
        self._create("scenes/only.txt", ["#@outfit: swimwear", "beach"])
        self.assertIsNone(self._resolver().pick_file("scenes", {"outfit": {"business"}}))

    def test_pick_file_excludes_named_files(self):
        self._create("wardrobe/catalog.txt", ["x"])
        self._create("wardrobe/casual.txt", ["#@occasion: casual", "casual"])
        result = self._resolver(seed=0).pick_file("wardrobe", {"occasion": {"casual"}}, exclude={"catalog.txt"})
        self.assertEqual(result, ("wardrobe/casual", "casual"))

    def test_pick_file_returns_line_from_eligible_file(self):
        self._create("scenes/beach.txt", ["#@outfit: swimwear", "sandy beach"])
        self._create("scenes/office.txt", ["#@outfit: business", "modern office"])
        result = self._resolver(seed=0).pick_file("scenes", {"outfit": {"swimwear"}})
        self.assertEqual(result, ("scenes/beach", "sandy beach"))

    def test_file_exists(self):
        self._create("a/b.txt", ["x"])
        resolver = self._resolver()
        self.assertTrue(resolver.file_exists("a/b"))
        self.assertFalse(resolver.file_exists("a/missing"))

    def test_no_repeat_mode_pops_without_replacement(self):
        self._create("deck.txt", ["one", "two", "three"])
        resolver = self._resolver(mode="Random (No Repeat)")
        picked = {resolver.pick_line("deck", None) for _ in range(3)}
        self.assertEqual(picked, {"one", "two", "three"})

    def test_no_repeat_deck_rebuilds_when_empty(self):
        self._create("deck.txt", ["only"])
        resolver = self._resolver(mode="Random (No Repeat)")
        self.assertEqual(resolver.pick_line("deck", None), "only")
        self.assertEqual(resolver.pick_line("deck", None), "only")

    def test_no_repeat_deck_invalidates_on_mtime_change(self):
        path = self._create("deck.txt", ["one", "two"])
        resolver = self._resolver(mode="Random (No Repeat)")
        first = {resolver.pick_line("deck", None) for _ in range(2)}
        self.assertEqual(first, {"one", "two"})
        future = os.path.getmtime(path) + 10
        os.utime(path, (future, future))
        again = {resolver.pick_line("deck", None) for _ in range(2)}
        self.assertEqual(again, {"one", "two"})

    def test_no_repeat_deck_keyed_by_context(self):
        self._create("cat.txt", ["#@occasion: a", "__a__", "#@occasion: b", "__b__"])
        self._create("a.txt", ["a1", "a2"])
        self._create("b.txt", ["b1", "b2"])
        resolver = self._resolver(mode="Random (No Repeat)")
        picked_a = {resolver.pick_line("cat", {"occasion": {"a"}}) for _ in range(2)}
        picked_b = {resolver.pick_line("cat", {"occasion": {"b"}}) for _ in range(2)}
        self.assertEqual(picked_a, {"__a__", "__a__"})
        self.assertEqual(picked_b, {"__b__", "__b__"})

    def test_build_file_index_cached_then_refreshed_on_new_file(self):
        self._create("colors.txt", ["red"])
        index1 = self._resolver()._build_file_index(self.wildcards_dir)
        self.assertIn("colors.txt", index1)
        index2 = self._resolver()._build_file_index(self.wildcards_dir)
        self.assertIn("colors.txt", index2)
        self._create("hair.txt", ["ponytail"])
        index3 = self._resolver()._build_file_index(self.wildcards_dir)
        self.assertIn("hair.txt", index3)

    def test_resolve_tag_path_direct_then_basename_fallback(self):
        self._create("sub/colors.txt", ["red"])
        self._create("colors.txt", ["root red"])
        resolver = self._resolver()
        self.assertTrue(resolver._resolve_tag_path("sub/colors").endswith("sub/colors.txt"))
        self.assertTrue(resolver._resolve_tag_path("colors").endswith("colors.txt"))
        self.assertIsNone(resolver._resolve_tag_path("nothing/here"))

    def test_resolve_tag_path_with_extension(self):
        self._create("colors.txt", ["red"])
        path = self._resolver()._resolve_tag_path("colors.txt")
        self.assertTrue(path.endswith("colors.txt"))

    def test_resolve_tag_path_traversal_guard(self):
        outside = os.path.join(self.temp_dir, "secret.txt")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("secret")
        self.assertIsNone(self._resolver()._resolve_tag_path("../secret"))
        result = self._resolver().resolve("__../secret__")
        self.assertEqual(result, "")

    def test_resolve_tag_missing_path_returns_literal(self):
        self.assertEqual(self._resolver()._resolve_tag("missing", None), "__missing__")

    def test_resolve_tag_empty_eligible_returns_empty(self):
        self._create("gated.txt", ["#@occasion: beach", "sand"])
        self.assertEqual(self._resolver()._resolve_tag("gated", {"occasion": {"office"}}), "")

    def test_parse_file_returns_none_when_missing(self):
        self.assertIsNone(self._resolver()._parse_file(os.path.join(self.wildcards_dir, "nope.txt")))

    def test_parse_file_returns_none_on_decode_error(self):
        path = os.path.join(self.wildcards_dir, "bad.txt")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe\xff")
        with self.assertLogs("ThatAIGod", level=logging.WARNING):
            self.assertIsNone(self._resolver()._parse_file(path))

    def test_parse_file_cache_hit_and_mtime_invalidation(self):
        path = self._create("item.txt", ["line one"])
        resolver = self._resolver()
        first = resolver._parse_file(path)
        self.assertEqual(first, [("line one", {})])
        cached = resolver._parse_file(path)
        self.assertIs(cached, first)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\nline two")
        future = os.path.getmtime(path) + 10
        os.utime(path, (future, future))
        refreshed = resolver._parse_file(path)
        self.assertEqual(len(refreshed), 2)

    def test_annotations_cache_fifo_eviction(self):
        original = _wildcard_core._MAX_CONTENT_CACHE_SIZE
        _wildcard_core._MAX_CONTENT_CACHE_SIZE = 2
        try:
            path_a = self._create("a.txt", ["a"])
            path_b = self._create("b.txt", ["b"])
            path_c = self._create("c.txt", ["c"])
            resolver = self._resolver()
            resolver._parse_file(path_a)
            resolver._parse_file(path_b)
            self.assertIn(path_a, WildcardResolver._annotations_cache)
            resolver._parse_file(path_c)
            self.assertNotIn(path_a, WildcardResolver._annotations_cache)
            self.assertIn(path_b, WildcardResolver._annotations_cache)
            self.assertIn(path_c, WildcardResolver._annotations_cache)
        finally:
            _wildcard_core._MAX_CONTENT_CACHE_SIZE = original

    def test_file_has_eligible_lines(self):
        path = self._create("item.txt", ["#@occasion: beach", "sand"])
        resolver = self._resolver()
        self.assertTrue(resolver._file_has_eligible_lines(path, {"occasion": {"beach"}}))
        self.assertFalse(resolver._file_has_eligible_lines(path, {"occasion": {"office"}}))
        self.assertFalse(
            resolver._file_has_eligible_lines(os.path.join(self.wildcards_dir, "missing.txt"), {"occasion": {"beach"}})
        )

    def test_file_has_eligible_lines_visited_guard(self):
        path = self._create("item.txt", ["x"])
        resolver = self._resolver()
        self.assertTrue(resolver._file_has_eligible_lines(path, None, visited=frozenset({path})))

    def test_eligible_lines_context_none_returns_all(self):
        self._create("item.txt", ["#@occasion: beach", "sand", "rock"])
        resolver = self._resolver()
        lines = resolver._eligible_lines(os.path.join(self.wildcards_dir, "item.txt"), None)
        self.assertEqual(lines, ["sand", "rock"])

    def test_pick_line_with_none_context(self):
        self._create("scenes/studio.txt", ["a studio"])
        resolver = self._resolver()
        self.assertEqual(resolver.pick_line("scenes/studio", None), "a studio")
        self.assertTrue(resolver._file_has_eligible_lines(os.path.join(self.wildcards_dir, "scenes/studio.txt"), None))

    def test_pick_no_repeat_with_missing_cache_path(self):
        self._create("colors.txt", ["red", "green"])
        resolver = self._resolver(mode="Random (No Repeat)")
        missing = os.path.join(self.temp_dir, "gone.txt")
        picked = resolver._pick(["red", "green"], missing, {"occasion": {"beach"}})
        self.assertIn(picked, ["red", "green"])
        second = resolver._pick(["red", "green"], missing, {"occasion": {"beach"}})
        self.assertIn(second, ["red", "green"])

    def test_tag_deep_eligible_non_tag_line(self):
        resolver = self._resolver()
        self.assertTrue(resolver._tag_deep_eligible("not a tag", {"occasion": {"x"}}, frozenset()))
        self.assertTrue(resolver._tag_deep_eligible("__missing_tag__", {"occasion": {"x"}}, frozenset()))

    def test_wildcard_pattern_matches_subdirectory_tags(self):
        self.assertTrue(_WILDCARD_PATTERN.fullmatch("__wardrobe/female/casual__"))
        self.assertTrue(_WILDCARD_PATTERN.fullmatch("__autowildcards/colors_female__"))

    def test_multiple_tags_in_one_line_resolve_separately(self):
        self._create("colors_a.txt", ["Khaki"])
        self._create("colors_b.txt", ["Soft lilac"])
        resolver = self._resolver()
        result = resolver.resolve("a sundress, __colors_a__ and __colors_b__")
        self.assertEqual(result, "a sundress, Khaki and Soft lilac")

    def test_max_iterations_constant(self):
        self.assertEqual(_MAX_WILDCARD_ITERATIONS, 50)

    def test_pick_line_with_directives_returns_line_and_directives(self):
        self._create("pose.txt", ["#@facing: front", "#@gaze: into the lens", "seated upright"])
        resolver = self._resolver()
        line, directives = resolver.pick_line_with_directives("pose", {"regions": {"face"}})
        self.assertEqual(line, "seated upright")
        self.assertEqual(directives.get("facing"), {"front"})
        self.assertEqual(directives.get("gaze"), {"into the lens"})

    def test_pick_line_with_directives_missing_or_filtered(self):
        resolver = self._resolver()
        self.assertEqual(resolver.pick_line_with_directives("missing", None), ("", {}))
        self._create("pose.txt", ["#@facing: back", "standing away"])
        filtered = resolver.pick_line_with_directives("pose", {"facing": {"front"}})
        self.assertEqual(filtered, ("", {}))

    def test_pick_line_per_block_joins_eligible_blocks(self):
        self._create(
            "nude.txt",
            [
                "#@regions: face, chest, breasts",
                "her exposed bust with erect nipples",
                "#@regions: back",
                "her bare smooth back",
                "#@regions: thighs, legs, feet",
                "nude below the waist",
            ],
        )
        resolver = self._resolver()
        front = resolver.pick_line_per_block("nude", {"regions": {"face", "chest", "breasts", "legs", "feet"}})
        self.assertIn("her exposed bust", front)
        self.assertNotIn("bare smooth back", front)
        self.assertIn("nude below the waist", front)
        back = resolver.pick_line_per_block("nude", {"regions": {"back"}})
        self.assertIn("bare smooth back", back)
        self.assertNotIn("nipples", back)

    def test_pick_line_per_block_missing_or_empty_file(self):
        resolver = self._resolver()
        self.assertEqual(resolver.pick_line_per_block("missing", None), "")
        self._create("empty.txt", ["# a comment only"])
        self.assertEqual(resolver.pick_line_per_block("empty", None), "")
