import math
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Wildcard_Reader
from Wildcard_Reader import _WILDCARD_PATTERN, WildcardReader


class TestWildcardReader(unittest.TestCase):
    def setUp(self):
        self.node = WildcardReader()
        self.temp_dir = tempfile.mkdtemp()
        self.wildcards_dir = os.path.join(self.temp_dir, "wildcards")
        os.makedirs(self.wildcards_dir, exist_ok=True)

        self.module_file_patch = patch.object(
            Wildcard_Reader,
            "__file__",
            os.path.join(self.temp_dir, "Wildcard_Reader.py"),
        )
        self.module_file_patch.start()

        WildcardReader._file_index_cache.clear()
        WildcardReader._file_mtimes.clear()
        WildcardReader._file_content_cache.clear()
        WildcardReader._deck_cache.clear()

    def tearDown(self):
        self.module_file_patch.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_wildcard_file(self, filename, lines):
        path = os.path.join(self.wildcards_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def test_no_wildcard_in_text_returns_as_is(self):
        result = self.node.process(
            text="a cat on a mat",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
        )
        self.assertEqual(result[0], "a cat on a mat")

    def test_single_wildcard_resolved(self):
        self._create_wildcard_file("colors.txt", ["red", "green", "blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=42,
            delimiter=", ",
        )
        self.assertIn(result[0], ["red", "green", "blue"])

    def test_deterministic_seed_produces_same_result(self):
        self._create_wildcard_file("colors.txt", ["red", "green", "blue"])
        r1 = self.node.process(text="__colors__", mode="Deterministic (Seed)", seed=99, delimiter=", ")
        r2 = self.node.process(text="__colors__", mode="Deterministic (Seed)", seed=99, delimiter=", ")
        self.assertEqual(r1, r2)

    def test_full_random_produces_different_results(self):
        self._create_wildcard_file("colors.txt", ["red", "green", "blue"])
        results = set()
        for _ in range(10):
            r = self.node.process(text="__colors__", mode="Full Random", seed=0, delimiter=", ")
            results.add(r[0])
        self.assertGreater(len(results), 1)

    def test_prepend_text(self):
        self._create_wildcard_file("colors.txt", ["blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
            **{"Prependable Text": "Start:"},
        )
        self.assertTrue(result[0].startswith("Start:"))

    def test_append_text(self):
        self._create_wildcard_file("colors.txt", ["blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
            **{"Appendable Text": ":End"},
        )
        self.assertTrue(result[0].endswith(":End"))

    def test_commented_lines_ignored(self):
        self._create_wildcard_file("colors.txt", ["# comment", "red", "# another", "blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
        )
        self.assertNotEqual(result[0], "# comment")

    def test_nested_wildcard_resolution(self):
        self._create_wildcard_file("primary.txt", ["__colors__"])
        self._create_wildcard_file("colors.txt", ["red", "blue"])
        result = self.node.process(
            text="__primary__",
            mode="Deterministic (Seed)",
            seed=42,
            delimiter=", ",
        )
        self.assertIn(result[0], ["red", "blue"])

    def test_unknown_wildcard_returns_unresolved(self):
        result = self.node.process(
            text="__nonexistent_file__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
        )
        self.assertEqual(result[0], "__nonexistent_file__")

    def test_empty_wildcard_file_returns_empty(self):
        self._create_wildcard_file("empty.txt", [""])
        result = self.node.process(
            text="__empty__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
        )
        self.assertEqual(result[0], "")

    def test_path_traversal_blocked(self):
        result = self.node.process(
            text="__..__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
        )
        self.assertEqual(result[0], "__..__")

    def test_single_wildcard_with_subdir(self):
        os.makedirs(os.path.join(self.wildcards_dir, "sub"), exist_ok=True)
        self._create_wildcard_file("sub/colors.txt", ["red", "green"])
        result = self.node.process(
            text="__sub/colors__",
            mode="Deterministic (Seed)",
            seed=42,
            delimiter=", ",
        )
        self.assertIn(result[0], ["red", "green"])

    def test_wildcard_pattern_matches_varied_tags(self):
        self.assertTrue(_WILDCARD_PATTERN.match("__hello__"))
        self.assertTrue(_WILDCARD_PATTERN.match("__hello-world__"))
        self.assertTrue(_WILDCARD_PATTERN.match("__sub/path__"))
        self.assertIsNone(_WILDCARD_PATTERN.match("__no match!!__"))

    def test_build_file_index_caches_by_mtime(self):
        self._create_wildcard_file("colors.txt", ["red"])
        index1 = self.node._build_file_index(self.wildcards_dir)
        self.assertIn("colors.txt", index1)

        index2 = self.node._build_file_index(self.wildcards_dir)
        self.assertEqual(index1, index2)

    def test_build_file_index_refreshes_on_new_file(self):
        self._create_wildcard_file("a.txt", ["a"])
        index1 = self.node._build_file_index(self.wildcards_dir)
        self.assertIn("a.txt", index1)

        self._create_wildcard_file("b.txt", ["b"])
        index2 = self.node._build_file_index(self.wildcards_dir)
        self.assertIn("b.txt", index2)

    def test_has_description(self):
        self.assertTrue(hasattr(WildcardReader, "DESCRIPTION"))
        self.assertIsInstance(WildcardReader.DESCRIPTION, str)

    def test_mappings_exported(self):
        from Wildcard_Reader import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
        self.assertIn("WildcardReader", NODE_CLASS_MAPPINGS)
        self.assertIn("WildcardReader", NODE_DISPLAY_NAME_MAPPINGS)

    def test_is_changed_deterministic_returns_seed(self):
        result = WildcardReader.IS_CHANGED(
            text="hello", mode="Deterministic (Seed)", seed=42, delimiter=", "
        )
        self.assertEqual(result, 42)

    def test_is_changed_full_random_returns_nan(self):
        result = WildcardReader.IS_CHANGED(
            text="hello", mode="Full Random", seed=0, delimiter=", "
        )
        self.assertTrue(math.isnan(result))

    def test_is_changed_no_repeat_returns_nan(self):
        result = WildcardReader.IS_CHANGED(
            text="hello", mode="Random (No Repeat)", seed=0, delimiter=", "
        )
        self.assertTrue(math.isnan(result))

    def test_no_repeat_deck_mode_exhausts_and_refills(self):
        self._create_wildcard_file("colors.txt", ["red", "green", "blue"])
        WildcardReader._deck_cache.clear()
        first_three = set()
        for i in range(3):
            r = self.node.process(
                text="__colors__",
                mode="Random (No Repeat)",
                seed=0,
                delimiter=", ",
            )
            first_three.add(r[0])
        self.assertEqual(len(first_three), 3, "First 3 draws should exhaust the deck with 3 unique items")

        fourth = self.node.process(
            text="__colors__",
            mode="Random (No Repeat)",
            seed=1,
            delimiter=", ",
        )
        self.assertIn(fourth[0], ["red", "green", "blue"], "4th draw should refill deck with a valid item")

    def test_no_repeat_deck_resets_on_new_seed_sequence(self):
        self._create_wildcard_file("colors.txt", ["red", "green"])
        WildcardReader._deck_cache.clear()
        r1 = self.node.process(
            text="__colors__", mode="Random (No Repeat)", seed=1, delimiter=", "
        )
        r2 = self.node.process(
            text="__colors__", mode="Random (No Repeat)", seed=1, delimiter=", "
        )
        self.assertNotEqual(r1[0], r2[0],
            "Two consecutive draws from a 2-item deck with same seed should differ")


    def test_input_types_without_wildcards_dir(self):
        shutil.rmtree(self.wildcards_dir)
        result = WildcardReader.INPUT_TYPES()
        self.assertIn("required", result)
        options = result["required"]["Select to add Wildcard"]
        options_list = options[0]
        self.assertEqual(len(options_list), 1)
        self.assertEqual(options_list[0], "Select a file from the wildcards directory")

    def test_input_types_with_wildcards_dir_and_subdir(self):
        self._create_wildcard_file("colors.txt", ["red"])
        os.makedirs(os.path.join(self.wildcards_dir, "sub"), exist_ok=True)
        self._create_wildcard_file("sub/shapes.txt", ["circle"])
        result = WildcardReader.INPUT_TYPES()
        options = result["required"]["Select to add Wildcard"]
        options_list = options[0]
        self.assertIn("__colors__", options_list)
        self.assertIn("__sub/shapes__", options_list)

    def test_wildcard_tag_with_txt_suffix(self):
        self._create_wildcard_file("colors.txt", ["red", "green"])
        result = self.node.process(
            text="__colors.txt__",
            mode="Deterministic (Seed)", seed=0, delimiter=", "
        )
        self.assertIn(result[0], ["red", "green"])

    def test_wildcard_in_subdir_via_file_index(self):
        os.makedirs(os.path.join(self.wildcards_dir, "sub"), exist_ok=True)
        self._create_wildcard_file("sub/colors.txt", ["blue"])
        WildcardReader._file_index_cache.clear()
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)", seed=0, delimiter=", "
        )
        self.assertEqual(result[0], "blue")

    def test_deck_mode_empty_file_returns_empty(self):
        self._create_wildcard_file("empty.txt", ["# only a comment"])
        WildcardReader._deck_cache.clear()
        result = self.node.process(
            text="__empty__",
            mode="Random (No Repeat)", seed=0, delimiter=", "
        )
        self.assertEqual(result[0], "")

    def test_deck_mode_file_io_error_returns_unresolved(self):
        self._create_wildcard_file("colors.txt", ["red"])
        WildcardReader._deck_cache.clear()
        with patch("builtins.open", side_effect=OSError("permission denied")):
            result = self.node.process(
                text="__colors__",
                mode="Random (No Repeat)", seed=0, delimiter=", "
            )
        self.assertEqual(result[0], "__colors__")

    def test_non_deck_file_io_error_returns_unresolved(self):
        self._create_wildcard_file("colors.txt", ["red"])
        with patch("builtins.open", side_effect=OSError("permission denied")):
            result = self.node.process(
                text="__colors__",
                mode="Deterministic (Seed)", seed=0, delimiter=", "
            )
        self.assertEqual(result[0], "__colors__")

    def test_process_creates_wildcards_dir_when_missing(self):
        shutil.rmtree(self.wildcards_dir)
        self.assertFalse(os.path.exists(self.wildcards_dir))
        result = self.node.process(
            text="hello world",
            mode="Deterministic (Seed)", seed=0, delimiter=", "
        )
        self.assertTrue(os.path.isdir(self.wildcards_dir))
        self.assertEqual(result[0], "hello world")

    def test_path_traversal_realpath_blocked(self):
        self._create_wildcard_file("colors.txt", ["red"])
        WildcardReader._file_index_cache.clear()
        original_realpath = os.path.realpath
        with patch("Wildcard_Reader.os.path.realpath") as mock_realpath:
            def side_effect(path):
                if path.endswith("colors.txt"):
                    return "Z:/outside/traversal.txt"
                return original_realpath(path)
            mock_realpath.side_effect = side_effect
            result = self.node.process(
                text="__colors__",
                mode="Deterministic (Seed)", seed=0, delimiter=", "
            )
        self.assertEqual(result[0], "__colors__")

    def test_no_repeat_deck_mode_tracks_mtime(self):
        self._create_wildcard_file("colors.txt", ["red", "green"])
        WildcardReader._file_index_cache.clear()
        WildcardReader._file_mtimes.clear()
        index = self.node._build_file_index(self.wildcards_dir)
        self.assertIn("colors.txt", index)
        mtimes = WildcardReader._file_mtimes.get(self.wildcards_dir, {})
        colors_path = os.path.join(self.wildcards_dir, "colors.txt")
        self.assertIn(colors_path, mtimes)

    def test_file_content_cache_returns_same_lines(self):
        self._create_wildcard_file("colors.txt", ["red", "green"])
        path = os.path.join(self.wildcards_dir, "colors.txt")
        lines1 = self.node._get_file_lines(path)
        lines2 = self.node._get_file_lines(path)
        self.assertEqual(lines1, lines2)
        self.assertIn(path, WildcardReader._file_content_cache)

    def test_file_content_cache_returns_none_on_io_error(self):
        path = os.path.join(self.wildcards_dir, "nonexistent.txt")
        result = self.node._get_file_lines(path)
        self.assertIsNone(result)

    def test_file_content_cache_invalidates_on_mtime_change(self):
        self._create_wildcard_file("colors.txt", ["red"])
        path = os.path.join(self.wildcards_dir, "colors.txt")
        lines1 = self.node._get_file_lines(path)
        self.assertEqual(lines1, ["red"])
        self._create_wildcard_file("colors.txt", ["red", "blue"])
        current_mtime = os.path.getmtime(path)
        os.utime(path, (current_mtime + 10, current_mtime + 10))
        lines2 = self.node._get_file_lines(path)
        self.assertEqual(lines2, ["red", "blue"])

    def test_content_cache_cleared_in_setup(self):
        self.assertNotIn("anything", WildcardReader._file_content_cache)


if __name__ == "__main__":
    unittest.main()
