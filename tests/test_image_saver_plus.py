import io
import json
import os
import re
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

folder_paths_mock = types.ModuleType("folder_paths")
folder_paths_mock.get_output_directory = lambda: tempfile.gettempdir()  # noqa: S108


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
from PIL import Image

import Image_Saver_Plus
from Image_Saver_Plus import ImageSaverPlus


def _find_file(directory, prefix, ext):
    for name in os.listdir(directory):
        if name.startswith(prefix) and name.endswith(f".{ext}"):
            return os.path.join(directory, name)
    return None


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

    def test_year_shorthand(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="%year%_img")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"\d{4}_img", f) for f in files))

    def test_month_shorthand(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="img_%month%")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"img_\d{2}", f) for f in files))

    def test_day_shorthand(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="img_%day%")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"img_\d{2}", f) for f in files))

    def test_hour_shorthand(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="img_%hour%h")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"img_\d{2}h", f) for f in files))

    def test_minute_shorthand(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="img_%minute%m")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"img_\d{2}m", f) for f in files))

    def test_second_shorthand(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="img_%second%s")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"img_\d{2}s", f) for f in files))

    def test_combined_shorthand_vars(self):
        result = self.node.save_images(images=self.dummy_image, filename_prefix="%year%-%month%-%day%")
        self.assertIn("ui", result)
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertTrue(any(re.search(r"\d{4}-\d{2}-\d{2}", f) for f in files))

    def test_shorthand_vars_constant_exists(self):
        self.assertTrue(hasattr(Image_Saver_Plus, "_SHORTHAND_VARS"))
        self.assertIsInstance(Image_Saver_Plus._SHORTHAND_VARS, list)
        self.assertEqual(len(Image_Saver_Plus._SHORTHAND_VARS), 6)

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

    def test_save_error_logged_no_crash(self):
        with patch("PIL.Image.Image.save") as mock_save:
            mock_save.side_effect = OSError("Disk full")
            self.node.save_images(images=self.dummy_image, filename_prefix="err")
            mock_save.assert_called_once()

    def test_text_sidecar_write_error_logged_no_crash(self):
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            self.node.save_images(
                images=self.dummy_image,
                filename_prefix="txterr",
                save_text="hello",
            )

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

    def test_failed_save_not_reported_to_ui(self):
        with patch("PIL.Image.Image.save") as mock_save:
            mock_save.side_effect = OSError("Disk full")
            result = self.node.save_images(images=self.dummy_image, filename_prefix="ghost")
        self.assertEqual(result["ui"]["images"], [])

    def test_sidecar_failure_still_reports_image(self):
        import builtins

        real_open = builtins.open

        def selective_open(file, *args, **kwargs):
            if str(file).endswith(".txt"):
                raise OSError("no txt")
            return real_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            result = self.node.save_images(
                images=self.dummy_image,
                filename_prefix="sidetext",
                save_text="hello",
            )
        self.assertEqual(len(result["ui"]["images"]), 1)
        self.assertIsNone(self._find_saved_txt("sidetext"))

    def test_unsupported_format_saves_nothing(self):
        with self.assertLogs("ThatAIGod", level="ERROR"):
            result = self.node.save_images(images=self.dummy_image, filename_prefix="bmpx", file_format="bmp")
        self.assertEqual(result["ui"]["images"], [])
        self.assertFalse(any(f.endswith(".bmp") for f in os.listdir(self.temp_dir)))

    def test_colon_in_date_template_sanitized(self):
        self.node.save_images(images=self.dummy_image, filename_prefix="img_%date:HH:mm%")
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0], r"^img_\d{2}_\d{2}_\d{5}_\.png$")

    def test_duplicate_counter_placeholder_replaced_once(self):
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.node.save_images(images=self.dummy_image, filename_prefix="dup_%counter%_%counter%")
        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".png")]
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0], r"^dup_\d{5}_%counter%\.png$")

    def test_sanitize_filename_segment(self):
        self.assertEqual(Image_Saver_Plus._sanitize_filename_segment("a:b*c?"), "a_b_c_")
        self.assertEqual(Image_Saver_Plus._sanitize_filename_segment("trailing.. "), "trailing")
        self.assertEqual(Image_Saver_Plus._sanitize_filename_segment("::"), "__")
        self.assertEqual(Image_Saver_Plus._sanitize_filename_segment(" "), "_")

    def test_sanitize_filename_template_preserves_separators(self):
        self.assertEqual(Image_Saver_Plus._sanitize_filename_template("sub:a/img*1"), "sub_a/img_1")
        self.assertEqual(Image_Saver_Plus._sanitize_filename_template("plain"), "plain")


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

    def test_counter_scan_accepts_variable_digit_counts(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "img_1234567_test.txt"), "w") as f:
                f.write("")
            result = Image_Saver_Plus._find_next_counter(d, "img_%counter%_test")
            self.assertEqual(result, 1234568)


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


class _FakeFrame:
    def __init__(self, array, frame_format):
        self.array = array
        self.format = frame_format
        self.reformatted = None
        self.pts = None
        self.time_base = None
        self.color_primaries = None
        self.color_trc = None
        self.colorspace = None
        self.color_range = None

    def reformat(self, format=None, dst_colorspace=None):
        self.reformatted = (format, dst_colorspace)
        return self


class _FakeVideoFrame:
    @staticmethod
    def from_ndarray(array, format):
        return _FakeFrame(array, format)


class _FakeCodec:
    created = []

    def __init__(self):
        self.width = None
        self.height = None
        self.pix_fmt = None
        self.time_base = None
        self.options = None
        self.frames = []

    @classmethod
    def create(cls, name, mode):
        codec = cls()
        cls.created.append(codec)
        return codec

    def encode(self, frame):
        if frame is None:
            return [b"flushed"]
        self.frames.append(frame)
        return [b"encoded"]


class _FakeStream:
    def __init__(self):
        self.width = None
        self.height = None
        self.pix_fmt = None
        self.options = None
        self.codec_context = types.SimpleNamespace(color_primaries=None, color_trc=None, colorspace=None, color_range=None)
        self.frames = []

    def encode(self, frame):
        if frame is None:
            return [b"flushed"]
        self.frames.append(frame)
        return [b"encoded"]


class _FakeContainer:
    def __init__(self, path, **kwargs):
        self.path = path
        self.kwargs = kwargs
        self.stream = _FakeStream()
        self.muxed = []
        self.codec = None
        self.rate = None

    def add_stream(self, codec, rate=None):
        self.codec = codec
        self.rate = rate
        return self.stream

    def mux(self, packet):
        self.muxed.append(packet)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeAV:
    def __init__(self):
        self.VideoFrame = _FakeVideoFrame
        self.CodecContext = _FakeCodec
        self.containers = []

    def open(self, path, **kwargs):
        container = _FakeContainer(path, **kwargs)
        self.containers.append(container)
        return container


class TestResolutionHelpers(unittest.TestCase):
    def test_load_av_returns_module(self):
        with patch("Image_Saver_Plus.importlib.import_module", return_value="fake-av"):
            self.assertEqual(Image_Saver_Plus._load_av(), "fake-av")

    def test_load_av_returns_none_when_missing(self):
        with patch("Image_Saver_Plus.importlib.import_module", side_effect=ImportError):
            self.assertIsNone(Image_Saver_Plus._load_av())

    def test_png_bit_depth_defaults_and_validation(self):
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("png", "auto", "sRGB"), "8-bit")
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("png", "16-bit", "sRGB"), "16-bit")
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.assertEqual(Image_Saver_Plus._resolve_bit_depth("png", "10-bit YUV420", "sRGB"), "8-bit")

    def test_avif_bit_depth_defaults_and_validation(self):
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("avif", "auto", "sRGB"), "8-bit YUV420")
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("avif", "auto", "HDR"), "10-bit YUV420")
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("avif", "10-bit YUV420", "sRGB"), "10-bit YUV420")
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.assertEqual(Image_Saver_Plus._resolve_bit_depth("avif", "16-bit", "sRGB"), "8-bit YUV420")

    def test_exr_bit_depth_defaults_and_validation(self):
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("exr", "auto", "linear"), "16-bit float")
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("exr", "32-bit float", "linear"), "32-bit float")
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.assertEqual(Image_Saver_Plus._resolve_bit_depth("exr", "16-bit", "linear"), "16-bit float")

    def test_bit_depth_passthrough_for_other_formats(self):
        self.assertEqual(Image_Saver_Plus._resolve_bit_depth("jpeg", "16-bit", "sRGB"), "16-bit")

    def test_avif_color_space_validation(self):
        for value in ("sRGB", "HDR", "HDR PQ"):
            self.assertEqual(Image_Saver_Plus._resolve_color_space("avif", value), value)
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.assertEqual(Image_Saver_Plus._resolve_color_space("avif", "linear"), "sRGB")

    def test_exr_color_space_validation(self):
        for value in ("sRGB", "HDR", "linear", "linear ACEScg"):
            self.assertEqual(Image_Saver_Plus._resolve_color_space("exr", value), value)
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.assertEqual(Image_Saver_Plus._resolve_color_space("exr", "HDR PQ"), "HDR")
        with self.assertLogs("ThatAIGod", level="WARNING"):
            self.assertEqual(Image_Saver_Plus._resolve_color_space("exr", "bogus"), "sRGB")

    def test_other_formats_use_srgb(self):
        self.assertEqual(Image_Saver_Plus._resolve_color_space("png", "HDR"), "sRGB")

    def test_color_transforms_preserve_alpha(self):
        rgba = torch.rand((1, 4, 4, 4))
        self.assertEqual(tuple(Image_Saver_Plus._srgb_to_linear(rgba).shape), (1, 4, 4, 4))
        self.assertEqual(tuple(Image_Saver_Plus._hlg_to_linear(rgba).shape), (1, 4, 4, 4))

    def test_to_scene_linear_variants(self):
        image = torch.rand((1, 4, 4, 3))
        self.assertEqual(tuple(Image_Saver_Plus._to_scene_linear(image, "sRGB").shape), (1, 4, 4, 3))
        self.assertEqual(tuple(Image_Saver_Plus._to_scene_linear(image, "HDR").shape), (1, 4, 4, 3))
        self.assertTrue(torch.equal(Image_Saver_Plus._to_scene_linear(image, "linear"), image))
        self.assertTrue(torch.equal(Image_Saver_Plus._to_scene_linear(image, "linear ACEScg"), image))
        with self.assertRaises(ValueError):
            Image_Saver_Plus._to_scene_linear(image, "bogus")


class TestEncodingHelpers(unittest.TestCase):
    def test_encode_via_pyav_without_reformat(self):
        fake_av = _FakeAV()
        with patch("Image_Saver_Plus.av", fake_av):
            encoded = Image_Saver_Plus._encode_via_pyav("png", torch.zeros((2, 3)).numpy(), "rgb24", "rgb24", {"a": "b"})
        self.assertEqual(encoded, b"encodedflushed")
        self.assertEqual(_FakeCodec.created[-1].options, {"a": "b"})

    def test_encode_via_pyav_with_reformat(self):
        fake_av = _FakeAV()
        with patch("Image_Saver_Plus.av", fake_av):
            Image_Saver_Plus._encode_via_pyav("png", torch.zeros((2, 3)).numpy(), "rgb48le", "rgb48be")
        self.assertEqual(_FakeCodec.created[-1].frames[0].reformatted, ("rgb48be", None))

    def test_encode_via_pyav_requires_av(self):
        with patch("Image_Saver_Plus.av", None), self.assertRaises(RuntimeError):
            Image_Saver_Plus._encode_via_pyav("png", torch.zeros((2, 3)).numpy(), "rgb24", "rgb24")

    def test_encode_png16_grayscale(self):
        with patch("Image_Saver_Plus._encode_via_pyav", return_value=b"png16") as mocked:
            result = Image_Saver_Plus._encode_png16(torch.zeros((2, 2)))
        self.assertEqual(result, b"png16")
        self.assertEqual(mocked.call_args.args[2:], ("gray16le", "gray16be"))

    def test_encode_png16_rgb(self):
        with patch("Image_Saver_Plus._encode_via_pyav", return_value=b"png16"):
            result = Image_Saver_Plus._encode_png16(torch.zeros((2, 2, 3)))
        self.assertEqual(result, b"png16")

    def test_encode_png16_rejects_bad_channels(self):
        with self.assertRaises(ValueError):
            Image_Saver_Plus._encode_png16(torch.zeros((2, 2, 2)))

    def test_encode_exr_16_and_32_bit(self):
        with patch("Image_Saver_Plus._encode_via_pyav", return_value=b"exr") as mocked:
            self.assertEqual(Image_Saver_Plus._encode_exr(torch.zeros((2, 2)), "16-bit float", "sRGB"), b"exr")
        self.assertEqual(mocked.call_args.args[2], "grayf32le")
        with patch("Image_Saver_Plus._encode_via_pyav", return_value=b"exr"):
            self.assertEqual(Image_Saver_Plus._encode_exr(torch.zeros((2, 2, 4)), "32-bit float", "linear ACEScg"), b"exr")

    def test_encode_exr_rejects_bad_channels(self):
        with self.assertRaises(ValueError):
            Image_Saver_Plus._encode_exr(torch.zeros((2, 2, 2)), "16-bit float", "sRGB")

    def test_inject_png_metadata_requires_signature(self):
        self.assertEqual(Image_Saver_Plus._inject_png_metadata(b"not-png", {}, None), b"not-png")

    def test_inject_png_metadata_empty(self):
        self.assertEqual(Image_Saver_Plus._inject_png_metadata(b"\x89PNG\r\n\x1a\n", None, None), b"\x89PNG\r\n\x1a\n")

    def test_inject_png_metadata_adds_chunks(self):
        buffer = io.BytesIO()
        Image.new("RGB", (1, 1)).save(buffer, format="PNG")
        result = Image_Saver_Plus._inject_png_metadata(buffer.getvalue(), {"p": 1}, {"workflow": {"w": 2}})
        self.assertIn(b"tEXtprompt", result)
        self.assertIn(b"tEXtworkflow", result)

    def test_inject_exr_metadata_import_error(self):
        with patch.dict(sys.modules, {"comfy_extras": None, "comfy_extras.nodes_images": None}):
            self.assertEqual(Image_Saver_Plus._inject_exr_metadata(b"old", {}, None, "sRGB"), b"old")

    def test_inject_exr_metadata_success(self):
        fake = types.ModuleType("comfy_extras.nodes_images")
        fake.inject_exr_metadata = lambda data, prompt, extra, colorspace: b"new"
        with patch.dict(sys.modules, {"comfy_extras": types.ModuleType("comfy_extras"), "comfy_extras.nodes_images": fake}):
            self.assertEqual(Image_Saver_Plus._inject_exr_metadata(b"old", {}, None, "sRGB"), b"new")

    def test_inject_exr_metadata_failure_keeps_image(self):
        fake = types.ModuleType("comfy_extras.nodes_images")

        def fail(*args):
            raise ValueError("bad header")

        fake.inject_exr_metadata = fail
        with patch.dict(sys.modules, {"comfy_extras": types.ModuleType("comfy_extras"), "comfy_extras.nodes_images": fake}):
            with self.assertLogs("ThatAIGod", level="WARNING"):
                self.assertEqual(Image_Saver_Plus._inject_exr_metadata(b"old", {}, None, "sRGB"), b"old")

    def test_inject_avif_metadata_none(self):
        Image_Saver_Plus._inject_avif_metadata("unused", None)

    def test_inject_avif_metadata_import_error(self):
        with patch.dict(sys.modules, {"comfy_extras": None, "comfy_extras.nodes_images": None}):
            Image_Saver_Plus._inject_avif_metadata("unused", {"prompt": {}})

    def test_inject_avif_metadata_success(self):
        fake = types.ModuleType("comfy_extras.nodes_images")
        calls = []
        fake.inject_avif_metadata = lambda path, metadata: calls.append((path, metadata))
        with patch.dict(sys.modules, {"comfy_extras": types.ModuleType("comfy_extras"), "comfy_extras.nodes_images": fake}):
            Image_Saver_Plus._inject_avif_metadata("file.avif", {"prompt": {}})
        self.assertEqual(calls, [("file.avif", {"prompt": {}})])

    def test_inject_avif_metadata_failure_logged(self):
        fake = types.ModuleType("comfy_extras.nodes_images")

        def fail(path, metadata):
            raise ValueError("bad layout")

        fake.inject_avif_metadata = fail
        with patch.dict(sys.modules, {"comfy_extras": types.ModuleType("comfy_extras"), "comfy_extras.nodes_images": fake}):
            with self.assertLogs("ThatAIGod", level="WARNING"):
                Image_Saver_Plus._inject_avif_metadata("file.avif", {"prompt": {}})

    def test_to_pil_keeps_alpha(self):
        image = Image_Saver_Plus._to_pil(torch.zeros((4, 4, 4)))
        self.assertEqual(image.mode, "RGBA")

    def test_to_pil_squeezes_single_channel(self):
        image = Image_Saver_Plus._to_pil(torch.zeros((4, 4, 1)))
        self.assertEqual(image.mode, "L")

    def test_avif_exif_encodes_prompt_and_workflow(self):
        data = Image_Saver_Plus._avif_exif({"prompt": {"p": 1}, "workflow": {"w": 2}})
        self.assertIn(b"prompt:", data)
        self.assertIn(b"workflow:", data)

    def test_avif_exif_without_prompt(self):
        data = Image_Saver_Plus._avif_exif({"workflow": {"w": 2}})
        self.assertNotIn(b"prompt:", data)
        self.assertIn(b"workflow:", data)


class TestAvifSaving(unittest.TestCase):
    def test_save_avif_pillow_still(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "still.avif")
            Image_Saver_Plus._save_avif_pillow(torch.zeros((1, 8, 8, 3)), path, 18, 6.0, False, None)
            self.assertGreater(os.path.getsize(path), 0)

    def test_save_avif_pillow_animated_with_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "anim.avif")
            Image_Saver_Plus._save_avif_pillow(torch.zeros((2, 8, 8, 3)), path, 18, 6.0, True, {"prompt": {"p": 1}})
            with Image.open(path) as image:
                self.assertEqual(getattr(image, "n_frames", 1), 2)

    def test_save_avif_pillow_requires_avif_support(self):
        with patch("Image_Saver_Plus.pil_features.check", return_value=False):
            with self.assertRaises(RuntimeError):
                Image_Saver_Plus._save_avif_pillow(torch.zeros((1, 8, 8, 3)), "unused.avif", 18, 6.0, False, None)

    def test_avif_color_properties_mapping(self):
        reformatter = types.ModuleType("av.video.reformatter")
        reformatter.ColorPrimaries = types.SimpleNamespace(BT709="bt709", BT2020="bt2020")
        reformatter.ColorTrc = types.SimpleNamespace(IEC61966_2_1="srgb", ARIB_STD_B67="hlg", SMPTE2084="pq")
        reformatter.ColorRange = types.SimpleNamespace(MPEG="mpeg")
        with patch.dict(
            sys.modules,
            {
                "av": types.ModuleType("av"),
                "av.video": types.ModuleType("av.video"),
                "av.video.reformatter": reformatter,
            },
        ):
            self.assertEqual(Image_Saver_Plus._avif_color_properties("sRGB"), ("bt709", "srgb", 1, "mpeg"))
            self.assertEqual(Image_Saver_Plus._avif_color_properties("HDR"), ("bt2020", "hlg", 9, "mpeg"))
            self.assertEqual(Image_Saver_Plus._avif_color_properties("HDR PQ"), ("bt2020", "pq", 9, "mpeg"))

    def test_avif_frame_grayscale_10bit(self):
        fake_av = _FakeAV()
        with patch("Image_Saver_Plus.av", fake_av):
            frame = Image_Saver_Plus._avif_frame(torch.zeros((4, 4)), "10-bit YUV420", "HDR", "yuv420p10le", (1, 2, 3, 4))
        self.assertEqual(frame.format, "gray16le")
        self.assertEqual(frame.reformatted, ("yuv420p10le", 3))
        self.assertEqual(frame.color_primaries, 1)

    def test_avif_frame_rgb_8bit(self):
        fake_av = _FakeAV()
        with patch("Image_Saver_Plus.av", fake_av):
            frame = Image_Saver_Plus._avif_frame(torch.zeros((4, 4, 3)), "8-bit YUV420", "sRGB", "yuv420p", (1, 2, 3, 4))
        self.assertEqual(frame.format, "rgb24")

    def test_avif_frame_rejects_rgba(self):
        with self.assertRaises(ValueError):
            Image_Saver_Plus._avif_frame(torch.zeros((4, 4, 4)), "8-bit YUV420", "sRGB", "yuv420p", (1, 2, 3, 4))

    def test_save_avif_pyav_10bit(self):
        fake_av = _FakeAV()
        with (
            patch("Image_Saver_Plus.av", fake_av),
            patch("Image_Saver_Plus._avif_color_properties", return_value=(1, 2, 3, 4)),
            patch("Image_Saver_Plus._avif_frame", return_value="frame"),
            patch("Image_Saver_Plus._inject_avif_metadata") as inject,
        ):
            Image_Saver_Plus._save_avif_pyav(
                torch.zeros((1, 8, 8, 3)), "out.avif", "10-bit YUV420", "HDR", 18, 12.0, 0, {"p": 1}
            )
        container = fake_av.containers[-1]
        self.assertEqual(container.stream.pix_fmt, "yuv420p10le")
        self.assertEqual(container.stream.options, {"crf": "18", "preset": "8"})
        self.assertEqual(container.muxed, [b"encoded", b"flushed"])
        inject.assert_called_once_with("out.avif", {"p": 1})

    def test_save_avif_pyav_8bit(self):
        fake_av = _FakeAV()
        with (
            patch("Image_Saver_Plus.av", fake_av),
            patch("Image_Saver_Plus._avif_color_properties", return_value=(1, 2, 3, 4)),
            patch("Image_Saver_Plus._avif_frame", return_value="frame"),
            patch("Image_Saver_Plus._inject_avif_metadata"),
        ):
            Image_Saver_Plus._save_avif_pyav(
                torch.zeros((1, 8, 8, 3)), "out.avif", "8-bit YUV420", "sRGB", 18, 1.0, None, None
            )
        self.assertEqual(fake_av.containers[-1].stream.pix_fmt, "yuv420p")
        self.assertIsNone(fake_av.containers[-1].kwargs["options"])

    def test_save_avif_prefers_pyav(self):
        with (
            patch("Image_Saver_Plus.av", object()),
            patch("Image_Saver_Plus._save_avif_pyav") as pyav,
            patch("Image_Saver_Plus._save_avif_pillow") as pillow,
        ):
            Image_Saver_Plus._save_avif(torch.zeros((1, 8, 8, 3)), "out.avif", "8-bit YUV420", "sRGB", 18, 1.0, 0, False, None)
        pyav.assert_called_once()
        pillow.assert_not_called()

    def test_save_avif_falls_back_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "partial.avif")
            with open(path, "wb") as f:
                f.write(b"partial")
            with (
                patch("Image_Saver_Plus.av", object()),
                patch("Image_Saver_Plus._save_avif_pyav", side_effect=ValueError("encode failed")),
                patch("Image_Saver_Plus._save_avif_pillow") as pillow,
                self.assertLogs("ThatAIGod", level="WARNING"),
            ):
                Image_Saver_Plus._save_avif(torch.zeros((1, 8, 8, 3)), path, "8-bit YUV420", "sRGB", 18, 1.0, 0, False, None)
            self.assertFalse(os.path.exists(path))
            pillow.assert_called_once()

    def test_save_avif_fallback_tolerates_missing_partial_file(self):
        with (
            patch("Image_Saver_Plus.av", object()),
            patch("Image_Saver_Plus._save_avif_pyav", side_effect=ValueError("encode failed")),
            patch("Image_Saver_Plus._save_avif_pillow") as pillow,
            patch("Image_Saver_Plus.os.remove", side_effect=OSError("no file")),
            self.assertLogs("ThatAIGod", level="WARNING"),
        ):
            Image_Saver_Plus._save_avif(
                torch.zeros((1, 8, 8, 3)), "missing.avif", "8-bit YUV420", "sRGB", 18, 1.0, 0, False, None
            )
        pillow.assert_called_once()

    def test_save_avif_oversized_hdr_animation_uses_pillow(self):
        images = torch.zeros((2, 9000, 4, 3))
        with (
            patch("Image_Saver_Plus.av", object()),
            patch("Image_Saver_Plus._save_avif_pillow") as pillow,
            self.assertLogs("ThatAIGod", level="INFO") as logs,
        ):
            Image_Saver_Plus._save_avif(images, "huge.avif", "10-bit YUV420", "HDR", 18, 6.0, 1, True, None)
        pillow.assert_called_once()
        joined = "\n".join(logs.output)
        self.assertIn("beyond SVT-AV1", joined)
        self.assertIn("8-bit SDR", joined)
        self.assertIn("loop_count", joined)

    def test_save_avif_without_pyav_uses_pillow(self):
        with (
            patch("Image_Saver_Plus.av", None),
            patch("Image_Saver_Plus._save_avif_pillow") as pillow,
        ):
            Image_Saver_Plus._save_avif(torch.zeros((1, 8, 8, 3)), "out.avif", "8-bit YUV420", "sRGB", 18, 1.0, 0, False, None)
        pillow.assert_called_once()


class TestNodeEncodingHelpers(unittest.TestCase):
    def test_apply_png_channels_auto_and_2d(self):
        image = torch.rand((4, 4))
        self.assertEqual(tuple(Image_Saver_Plus._apply_png_channels(image, "auto").shape), (4, 4, 1))

    def test_apply_png_channels_grayscale(self):
        image = torch.rand((4, 4, 4))
        self.assertEqual(tuple(Image_Saver_Plus._apply_png_channels(image, "grayscale (1 channel)").shape), (4, 4, 1))

    def test_apply_png_channels_rgb_from_single(self):
        image = torch.rand((4, 4, 1))
        self.assertEqual(tuple(Image_Saver_Plus._apply_png_channels(image, "RGB (3 channels)").shape), (4, 4, 3))

    def test_apply_png_channels_rgb_drops_alpha(self):
        image = torch.rand((4, 4, 4))
        self.assertEqual(tuple(Image_Saver_Plus._apply_png_channels(image, "RGB (3 channels)").shape), (4, 4, 3))

    def test_apply_png_channels_rgba_from_single(self):
        image = torch.rand((4, 4, 1))
        self.assertEqual(tuple(Image_Saver_Plus._apply_png_channels(image, "RGBA (4 channels)").shape), (4, 4, 4))

    def test_apply_png_channels_rgba_adds_alpha(self):
        image = torch.rand((4, 4, 3))
        result = Image_Saver_Plus._apply_png_channels(image, "RGBA (4 channels)")
        self.assertEqual(tuple(result.shape), (4, 4, 4))
        self.assertTrue(torch.all(result[..., 3] == 1.0))

    def test_build_base_file_with_counter(self):
        self.assertEqual(Image_Saver_Plus._build_base_file("img_%counter%_x", 2, 7), "img_00007_x")

    def test_build_base_file_suffix_fallback(self):
        self.assertEqual(Image_Saver_Plus._build_base_file("img_%batch_num%", 2, 7), "img_2_00007_")

    def test_write_sidecar_skips_empty(self):
        with tempfile.TemporaryDirectory() as d:
            Image_Saver_Plus._write_sidecar(d, "base", None)
            self.assertEqual(os.listdir(d), [])

    def test_write_sidecar_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            Image_Saver_Plus._write_sidecar(d, "base", "text")
            with open(os.path.join(d, "base.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "text")

    def test_write_sidecar_failure_logged(self):
        with patch("builtins.open", side_effect=OSError("denied")), self.assertLogs("ThatAIGod", level="ERROR"):
            Image_Saver_Plus._write_sidecar("folder", "base", "text")

    def test_png_info_variants(self):
        self.assertIsNone(Image_Saver_Plus._png_info(None, None))
        info = Image_Saver_Plus._png_info({"p": 1}, None)
        self.assertEqual(len(info.chunks), 1)
        info = Image_Saver_Plus._png_info(None, {"workflow": {"w": 1}})
        self.assertEqual(len(info.chunks), 1)


class TestImageSaverPlusFormats(unittest.TestCase):
    def setUp(self):
        self.node = ImageSaverPlus()
        self.temp_dir = tempfile.mkdtemp()
        self.node.output_dir = self.temp_dir
        self.image = torch.zeros((1, 8, 8, 3))
        self.batch = torch.zeros((2, 8, 8, 3))

    def test_avif_still_uses_avif_saver(self):
        with patch("Image_Saver_Plus._save_avif") as saver:
            result = self.node.save_images(images=self.image, filename_prefix="avif", file_format="avif", save_text="t")
        self.assertEqual(len(result["ui"]["images"]), 1)
        saver.assert_called_once()
        self.assertEqual(saver.call_args.args[8], None)
        self.assertTrue(any(name.startswith("avif") and name.endswith(".txt") for name in os.listdir(self.temp_dir)))

    def test_avif_animated_saves_one_file(self):
        with patch("Image_Saver_Plus._save_avif") as saver:
            result = self.node.save_images(images=self.batch, filename_prefix="anim", file_format="avif", save_mode="animated")
        self.assertEqual(len(result["ui"]["images"]), 1)
        self.assertTrue(saver.call_args.args[7])

    def test_avif_metadata_passed(self):
        with patch("Image_Saver_Plus._save_avif") as saver:
            self.node.save_images(
                images=self.image,
                filename_prefix="meta",
                file_format="avif",
                prompt={"p": 1},
                extra_pnginfo={"workflow": {"w": 2}},
            )
        self.assertEqual(saver.call_args.args[8], {"prompt": {"p": 1}, "workflow": {"w": 2}})

    def test_avif_failure_skipped(self):
        with patch("Image_Saver_Plus._save_avif", side_effect=OSError("nope")):
            result = self.node.save_images(images=self.image, filename_prefix="bad", file_format="avif")
        self.assertEqual(result["ui"]["images"], [])

    def test_png16_writes_encoded_bytes(self):
        with (
            patch("Image_Saver_Plus._encode_png16", return_value=b"raw-png"),
            patch("Image_Saver_Plus._inject_png_metadata", return_value=b"data"),
        ):
            result = self.node.save_images(images=self.image, filename_prefix="p16", bit_depth="16-bit")
        self.assertEqual(len(result["ui"]["images"]), 1)
        path = _find_file(self.temp_dir, "p16", "png")
        self.assertIsNotNone(path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"data")

    def test_exr_writes_encoded_bytes(self):
        with (
            patch("Image_Saver_Plus._encode_exr", return_value=b"raw-exr"),
            patch("Image_Saver_Plus._inject_exr_metadata", return_value=b"exr-data"),
        ):
            result = self.node.save_images(
                images=self.image,
                filename_prefix="e",
                file_format="exr",
                bit_depth="32-bit float",
                input_color_space="linear",
            )
        self.assertEqual(len(result["ui"]["images"]), 1)
        path = _find_file(self.temp_dir, "e", "exr")
        self.assertIsNotNone(path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"exr-data")

    def test_exr_failure_skipped(self):
        with patch("Image_Saver_Plus._encode_exr", side_effect=OSError("no exr")):
            result = self.node.save_images(images=self.image, filename_prefix="badexr", file_format="exr")
        self.assertEqual(result["ui"]["images"], [])

    def test_png_grayscale_channel_conversion(self):
        self.node.save_images(images=self.image, filename_prefix="gray", channels="grayscale (1 channel)")
        path = _find_file(self.temp_dir, "gray", "png")
        self.assertIsNotNone(path)
        with Image.open(path) as image:
            self.assertEqual(image.mode, "L")

    def test_png_rgba_channel_conversion(self):
        self.node.save_images(images=self.image, filename_prefix="rgba", channels="RGBA (4 channels)")
        path = _find_file(self.temp_dir, "rgba", "png")
        self.assertIsNotNone(path)
        with Image.open(path) as image:
            self.assertEqual(image.mode, "RGBA")

    def test_jpeg_converts_rgba_to_rgb(self):
        self.node.save_images(images=torch.zeros((1, 8, 8, 4)), filename_prefix="jrgba", file_format="jpeg")
        path = _find_file(self.temp_dir, "jrgba", "jpeg")
        self.assertIsNotNone(path)
        with Image.open(path) as image:
            self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
