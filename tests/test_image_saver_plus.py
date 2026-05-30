import json
import os
import re
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

folder_paths_mock = types.ModuleType("folder_paths")
folder_paths_mock.get_output_directory = lambda: "/tmp"


class _SaveImagePathTracker:
    def __init__(self):
        self.next_counter = 1

    def get_save_image_path(self, filename_prefix, output_dir, image_width=0, image_height=0):
        prefix = os.path.basename(os.path.normpath(filename_prefix))
        counter = self.next_counter
        self.next_counter += 1
        return (output_dir, prefix, counter, "", prefix)


_path_tracker = _SaveImagePathTracker()
folder_paths_mock.get_save_image_path = _path_tracker.get_save_image_path
sys.modules["folder_paths"] = folder_paths_mock

import tempfile
import unittest
from unittest.mock import MagicMock, patch

import torch

import Image_Saver_Plus
from Image_Saver_Plus import ImageSaverPlus


class TestImageSaverPlus(unittest.TestCase):
    def setUp(self):
        self.node = ImageSaverPlus()
        self.temp_dir = tempfile.mkdtemp()
        self.node.output_dir = self.temp_dir

        self.dummy_image = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
        self.dummy_batch = torch.zeros((2, 64, 64, 3), dtype=torch.float32)

    def _find_saved_txt(self, prefix):
        for f in os.listdir(self.temp_dir):
            if f.startswith(prefix) and f.endswith(".txt"):
                return os.path.join(self.temp_dir, f)
        return None

    def _find_by_prefix(self, prefix, ext):
        for f in os.listdir(self.temp_dir):
            base = os.path.splitext(f)[0]
            if base.startswith(prefix) and f.endswith(f".{ext}"):
                return os.path.join(self.temp_dir, f)
        return None

    def test_saves_png_by_default(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="test")
        self.assertIn("ui", result)
        self.assertIn("images", result["ui"])
        saved = self._find_by_prefix("test", "png")
        self.assertIsNotNone(saved)
        self.assertTrue(os.path.getsize(saved) > 0)

    def test_saves_jpeg(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="jpeg_test", file_format="jpeg")
        saved = self._find_by_prefix("jpeg_test", "jpeg")
        self.assertIsNotNone(saved)

    def test_saves_webp(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="webp_test", file_format="webp")
        saved = self._find_by_prefix("webp_test", "webp")
        self.assertIsNotNone(saved)

    def test_saves_text_sidecar(self):
        self.node.save_images(
            images=self.dummy_image,
            filename_prefix="sidecar",
            save_text="hello world",
        )
        txt = self._find_saved_txt("sidecar")
        self.assertIsNotNone(txt)
        with open(txt, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "hello world")

    def test_text_sidecar_with_jpeg(self):
        self.node.save_images(
            images=self.dummy_image,
            filename_prefix="jpeg_sidecar",
            file_format="jpeg",
            save_text="jpeg text",
        )
        txt = self._find_saved_txt("jpeg_sidecar")
        self.assertIsNotNone(txt)
        with open(txt, encoding="utf-8") as f:
            self.assertEqual(f.read(), "jpeg text")

    def test_batch_saves_multiple_files(self):
        self.node.save_images(images=self.dummy_batch, filename_prefix="batch")
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertEqual(len(files), 2)

    def test_batch_text_sidecar_per_image(self):
        self.node.save_images(
            images=self.dummy_batch,
            filename_prefix="batch_txt",
            save_text="same text",
        )
        txt_files = sorted(f for f in os.listdir(self.temp_dir) if f.endswith(".txt"))
        self.assertEqual(len(txt_files), 2)

    def test_quality_applied_to_jpeg(self):
        self.node.save_images(
            images=self.dummy_image,
            filename_prefix="qual",
            file_format="jpeg",
            quality=10,
        )
        saved = self._find_by_prefix("qual", "jpeg")
        self.assertIsNotNone(saved)

    def test_compress_level_applied_to_png(self):
        self.node.save_images(
            images=self.dummy_image,
            filename_prefix="compress",
            compress_level=0,
        )
        saved = self._find_by_prefix("compress", "png")
        self.assertIsNotNone(saved)

    def test_png_metadata_includes_prompt(self):
        with patch("Image_Saver_Plus.PngInfo") as mock_pnginfo_cls:
            mock_pnginfo = MagicMock()
            mock_pnginfo_cls.return_value = mock_pnginfo
            self.node.save_images(
                images=self.dummy_image,
                filename_prefix="meta",
                prompt={"test": "data"},
            )
            mock_pnginfo.add_text.assert_any_call("prompt", json.dumps({"test": "data"}))

    def test_png_metadata_includes_extra_pnginfo(self):
        with patch("Image_Saver_Plus.PngInfo") as mock_pnginfo_cls:
            mock_pnginfo = MagicMock()
            mock_pnginfo_cls.return_value = mock_pnginfo
            self.node.save_images(
                images=self.dummy_image,
                filename_prefix="meta2",
                extra_pnginfo={"workflow": {"key": "val"}},
            )
            mock_pnginfo.add_text.assert_any_call("workflow", json.dumps({"key": "val"}))

    def test_has_description(self):
        self.assertTrue(hasattr(ImageSaverPlus, "DESCRIPTION"))
        self.assertIsInstance(ImageSaverPlus.DESCRIPTION, str)

    def test_mappings_exported(self):
        from Image_Saver_Plus import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
        self.assertIn("ImageSaverPlus", NODE_CLASS_MAPPINGS)
        self.assertIn("ImageSaverPlus", NODE_DISPLAY_NAME_MAPPINGS)

    def test_counter_increments(self):
        r1 = self.node.save_images(images=self.dummy_image, filename_prefix="counter")
        r2 = self.node.save_images(images=self.dummy_image, filename_prefix="counter")
        self.assertEqual(len(r1["ui"]["images"]), 1)
        self.assertEqual(len(r2["ui"]["images"]), 1)
        self.assertNotEqual(r1["ui"]["images"][0]["filename"], r2["ui"]["images"][0]["filename"])

    def test_returns_image_results_in_ui(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="ui_test")
        self.assertIn("ui", result)
        self.assertIn("images", result["ui"])
        self.assertEqual(len(result["ui"]["images"]), 1)
        entry = result["ui"]["images"][0]
        self.assertIn("filename", entry)
        self.assertIn("subfolder", entry)
        self.assertIn("type", entry)
        self.assertEqual(entry["type"], "output")

    def test_date_pattern_in_filename(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="%date:yyyyMMdd%/snap")
        saved = self._find_by_prefix("snap", "png")
        self.assertIsNotNone(saved)

    def test_date_pattern_in_subfolder(self):
        self.node.save_images(
            images=self.dummy_image,
            filename_prefix="dated/%date:yyyy_MM_dd%/img",
        )
        saved = self._find_by_prefix("img", "png")
        self.assertIsNotNone(saved)

    def test_date_pattern_multiple(self):
        self.node.save_images(
            images=self.dummy_image,
            filename_prefix="%date:yyyy%%date:MM%%date:dd%/combined",
        )
        saved = self._find_by_prefix("combined", "png")
        self.assertIsNotNone(saved)

    def test_resolve_date_format(self):
        result = Image_Saver_Plus._resolve_date_format("yyyy_MM_dd")
        self.assertRegex(result, r"\d{4}_\d{2}_\d{2}")


    def test_counter_placeholder_in_default_position(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="nocounter")
        saved = self._find_by_prefix("nocounter", "png")
        self.assertIsNotNone(saved)
        self.assertRegex(os.path.basename(saved), r"nocounter_\d{5}_\.png")

    def test_counter_placeholder_at_end(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="img_%counter%")
        files = os.listdir(self.temp_dir)
        pngs = [f for f in files if f.endswith(".png")]
        self.assertEqual(len(pngs), 1)
        self.assertRegex(pngs[0], r"^img_\d{5}\.png$")

    def test_counter_placeholder_in_middle(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="%date:yyyyMMdd%_%counter%_PreFaceFix")
        files = os.listdir(self.temp_dir)
        pngs = [f for f in files if f.endswith(".png")]
        self.assertEqual(len(pngs), 1)
        self.assertRegex(pngs[0], r"^\d{8}_\d{5}_PreFaceFix\.png$")

    def test_counter_does_not_overwrite(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="cnt_%counter%_test")
        self.node.save_images(images=self.dummy_image, filename_prefix="cnt_%counter%_test")
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertEqual(len(files), 2)
        counters = set()
        for f in files:
            m = re.match(r"cnt_(\d{5})_test\.png", f)
            if m:
                counters.add(int(m.group(1)))
        self.assertEqual(len(counters), 2)
        self.assertIn(1, counters)
        self.assertIn(2, counters)


class TestFindNextCounter(unittest.TestCase):
    def test_nonexistent_folder_returns_one(self):
        result = Image_Saver_Plus._find_next_counter(r"C:\does_not_exist_xyz", "img_%counter%")
        self.assertEqual(result, 1)

    def test_empty_folder_returns_one(self):
        with tempfile.TemporaryDirectory() as d:
            result = Image_Saver_Plus._find_next_counter(d, "img_%counter%")
            self.assertEqual(result, 1)

    def test_finds_max_counter_among_matching_files(self):
        with tempfile.TemporaryDirectory() as d:
            for i in (1, 3, 5):
                with open(os.path.join(d, f"img_{i:05d}_test.txt"), "w") as f:
                    f.write("")
            result = Image_Saver_Plus._find_next_counter(d, "img_%counter%_test")
            self.assertEqual(result, 6)


class TestDatePatternRegex(unittest.TestCase):
    def test_matches_date_pattern(self):
        m = Image_Saver_Plus._DATE_PATTERN.search("prefix_%date:yyyy_MM_dd%_suffix")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "yyyy_MM_dd")

    def test_no_match_without_date(self):
        m = Image_Saver_Plus._DATE_PATTERN.search("no_date_here")
        self.assertIsNone(m)

    def test_multiple_matches(self):
        matches = Image_Saver_Plus._DATE_PATTERN.findall("a%date:yyyy%b%date:MM%c")
        self.assertEqual(matches, ["yyyy", "MM"])


if __name__ == "__main__":
    unittest.main()
