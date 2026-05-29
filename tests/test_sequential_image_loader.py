import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from PIL import Image
from Sequential_Image_Loader import SequentialImageLoader


class TestSequentialImageLoader(unittest.TestCase):
    def setUp(self):
        self.node = SequentialImageLoader()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_image(self, name, size=(64, 64)):
        path = os.path.join(self.temp_dir, name)
        img = Image.new("RGB", size)
        img.save(path)
        return path

    def test_returns_image_tensor(self):
        self._create_image("test.png")
        result = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 0})
        self.assertEqual(result[0].shape[3], 3)

    def test_correct_filename_returned(self):
        self._create_image("photo.png")
        result = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 0})
        self.assertEqual(result[1], "photo")

    def test_stats_format(self):
        self._create_image("a.png")
        self._create_image("b.png")
        result = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 0})
        self.assertIn("/", result[2])

    def test_modulo_wrapping(self):
        self._create_image("img1.png")
        self._create_image("img2.png")
        result = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 5})
        expected_files = ["img1", "img2"]
        self.assertIn(result[1], expected_files)

    def test_natural_sort_order(self):
        self._create_image("img2.png")
        self._create_image("img10.png")
        self._create_image("img1.png")
        result0 = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 0})
        result1 = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 1})
        result2 = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 2})
        filenames = [result0[1], result1[1], result2[1]]
        self.assertEqual(filenames, ["img1", "img2", "img10"])

    def test_mixed_int_str_filenames(self):
        self._create_image("10image.png")
        self._create_image("file1.png")
        self._create_image("file2.png")
        result0 = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 0})
        result1 = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 1})
        result2 = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 2})
        filenames = [result0[1], result1[1], result2[1]]
        self.assertEqual(filenames, ["10image", "file1", "file2"])

    def test_invalid_directory_returns_error(self):
        result = self.node.load_next(**{"Directory Path": "C:\\nonexistent_dir_xyz", "seed": 0})
        self.assertEqual(result[1], "error_no_dir")

    def test_empty_directory_returns_error(self):
        result = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 0})
        self.assertEqual(result[1], "error_empty_dir")

    def test_multiple_extensions_accepted(self):
        self._create_image("img1.png")
        self._create_image("img2.jpg")
        self._create_image("img3.jpeg")
        self._create_image("img4.webp")
        self._create_image("img5.bmp")
        self._create_image("img6.tiff")
        result = self.node.load_next(**{"Directory Path": self.temp_dir, "seed": 5})
        self.assertNotEqual(result[1], "error_empty_dir")


if __name__ == "__main__":
    unittest.main()
