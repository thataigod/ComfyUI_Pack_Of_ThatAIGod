import sys
import os
import tempfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Wildcard_Reader
from Wildcard_Reader import WildcardReader, _WILDCARD_PATTERN


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


if __name__ == "__main__":
    unittest.main()
