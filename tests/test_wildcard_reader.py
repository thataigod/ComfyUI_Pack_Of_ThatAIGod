import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from Wildcard_Reader import WildcardReader


class TestWildcardReader(unittest.TestCase):
    def setUp(self):
        self.node = WildcardReader()
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.wildcards_dir = os.path.join(self.original_dir, "wildcards")
        self.backup_dir = None

        if os.path.exists(self.wildcards_dir):
            self.backup_dir = tempfile.mkdtemp()
            shutil.move(self.wildcards_dir, os.path.join(self.backup_dir, "wildcards"))

        os.makedirs("wildcards", exist_ok=True)

    def tearDown(self):
        shutil.rmtree("wildcards", ignore_errors=True)
        if self.backup_dir and os.path.exists(os.path.join(self.backup_dir, "wildcards")):
            shutil.move(os.path.join(self.backup_dir, "wildcards"), self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_wildcard_file(self, filename, lines):
        path = os.path.join("wildcards", filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def test_no_wildcard_in_text_returns_as_is(self):
        result = self.node.process(
            text="a cat on a mat",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", "
        )
        self.assertEqual(result[0], "a cat on a mat")

    def test_single_wildcard_resolved(self):
        self._create_wildcard_file("colors.txt", ["red", "green", "blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=42,
            delimiter=", "
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
            **{"Prependable Text": "Start:"}
        )
        self.assertTrue(result[0].startswith("Start:"))

    def test_append_text(self):
        self._create_wildcard_file("colors.txt", ["blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", ",
            **{"Appendable Text": ":End"}
        )
        self.assertTrue(result[0].endswith(":End"))

    def test_commented_lines_ignored(self):
        self._create_wildcard_file("colors.txt", ["# comment", "red", "# another", "blue"])
        result = self.node.process(
            text="__colors__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", "
        )
        self.assertNotEqual(result[0], "# comment")

    def test_nested_wildcard_resolution(self):
        self._create_wildcard_file("primary.txt", ["__colors__"])
        self._create_wildcard_file("colors.txt", ["red", "blue"])
        result = self.node.process(
            text="__primary__",
            mode="Deterministic (Seed)",
            seed=42,
            delimiter=", "
        )
        self.assertIn(result[0], ["red", "blue"])

    def test_unknown_wildcard_returns_unresolved(self):
        result = self.node.process(
            text="__nonexistent_file__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", "
        )
        self.assertEqual(result[0], "__nonexistent_file__")

    def test_empty_wildcard_file_returns_empty(self):
        self._create_wildcard_file("empty.txt", [""])
        result = self.node.process(
            text="__empty__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", "
        )
        self.assertIsInstance(result[0], str)

    def test_path_traversal_blocked(self):
        result = self.node.process(
            text="__..__",
            mode="Deterministic (Seed)",
            seed=0,
            delimiter=", "
        )
        self.assertEqual(result[0], "__..__")


if __name__ == "__main__":
    unittest.main()
