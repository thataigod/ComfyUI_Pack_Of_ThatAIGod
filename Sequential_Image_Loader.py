"""Sequential Image Loader node for ComfyUI.

Provides :class:`SequentialImageLoader`, which loads images from a directory
one at a time using a seed as an index.  Natural sort ordering ensures that
files like ``img1.png``, ``img2.png``, ``img10.png`` are ordered numerically
rather than lexicographically.

Typical usage: connect the ``seed`` input to a node with "Control After Generate"
set to "Increment" to iterate through an image dataset frame by frame.
"""

import logging
import os
import re
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageOps

logger = logging.getLogger("ThatAIGod")

# File extensions recognised as valid images. Checked case-insensitively.
VALID_IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tiff",
)


class SequentialImageLoader:
    """Loads images sequentially from a directory using seed-based indexing.

    Supports natural sort ordering and multiple image formats (PNG, JPG, WEBP, BMP, TIFF).
    The seed is used as a direct index (modulo the number of files) rather than as
    a random-number-generator seed, so incrementing the seed steps through images in order.
    """

    DESCRIPTION = "Loads images sequentially from a directory using a seed as the index. Supports natural sort ordering and multiple image formats."

    RETURN_TYPES: tuple[str, ...] = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Image", "Filename", "Stats")
    FUNCTION: str = "load_next"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Directory Path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "C:\\Images\\Dataset",
                        "tooltip": "Absolute path to the directory containing images. Subdirectories are not searched.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "step": 1,
                        "tooltip": (
                            "Index of the image to load (wraps around with modulo). "
                            "Set 'Control After Generate' to 'Increment' to step through images automatically."
                        ),
                    },
                ),
            }
        }

    @staticmethod
    def natural_sort_key(s: str) -> list[tuple[int, int | str]]:
        """Generate a sort key that orders strings with embedded numbers numerically.

        Splits *s* on digit boundaries and produces a list of ``(type, value)``
        tuples: ``(0, int)`` for numeric segments (sorted numerically) and
        ``(1, str)`` for text segments (sorted case-insensitively).

        This ensures ``img2.png`` sorts before ``img10.png``, unlike the default
        lexicographic ordering where ``"10" < "2"``.

        Args:
            s: The filename string to produce a sort key for.

        Returns:
            A list of ``(int, int | str)`` tuples suitable for use as a
            ``key=`` argument to :func:`list.sort`.
        """
        # Split on digit boundaries; sort numeric parts as ints, text as lowercase
        return [(0, int(text)) if text.isdigit() else (1, text.lower()) for text in re.split(r"(\d+)", s)]

    def load_next(self, **kwargs: Any) -> tuple[torch.Tensor, str, str]:
        """Load a single image from the directory at the position given by the seed index.

        The seed is taken modulo the total number of files so the index wraps around
        safely regardless of how large the seed is.

        EXIF orientation is automatically applied via :func:`PIL.ImageOps.exif_transpose`
        and the image is always converted to RGB before returning.

        On any error (directory not found, no valid images, file read failure) a
        black 64×64 placeholder tensor is returned alongside an ``"ERROR"`` filename
        and a descriptive stats string.

        Args:
            **kwargs: ComfyUI widget values.  Expected keys:
                ``"Directory Path"`` (str), ``"seed"`` (int).

        Returns:
            A 3-tuple ``(image_tensor, filename_no_ext, stats)``:

            * ``image_tensor`` — shape ``(1, H, W, 3)`` float32 in ``[0, 1]``.
            * ``filename_no_ext`` — the loaded filename without its extension, or
              ``"ERROR"`` on failure.
            * ``stats`` — ``"<index>/<total>"`` (e.g. ``"3/50"``), or an error
              message on failure.
        """
        directory_path: str = kwargs.get("Directory Path", "")
        index: int = kwargs.get("seed", 0)

        if not directory_path or not os.path.isdir(directory_path):
            logger.error("Directory not found: %s", directory_path)
            placeholder = torch.zeros((1, 64, 64, 3))
            return (placeholder, "ERROR", f"Directory not found: {directory_path}")

        files: list[str] = [f for f in os.listdir(directory_path) if f.lower().endswith(VALID_IMAGE_EXTENSIONS)]
        files.sort(key=self.natural_sort_key)

        total_files: int = len(files)
        if total_files == 0:
            logger.error("No supported image files found in %s", directory_path)
            placeholder = torch.zeros((1, 64, 64, 3))
            return (placeholder, "ERROR", f"No supported image files found in {directory_path}")

        safe_index: int = index % total_files
        current_filename: str = files[safe_index]

        filename_no_ext: str = os.path.splitext(current_filename)[0]
        stats: str = f"{safe_index + 1}/{total_files}"

        logger.info("Processing %s: %s", stats, current_filename)

        img_path: str = os.path.join(directory_path, current_filename)
        try:
            i: Image.Image = Image.open(img_path)
            # Apply EXIF orientation tag so rotated photos appear correctly.
            i = ImageOps.exif_transpose(i)
            # Strip EXIF and DPI metadata to avoid PIL warnings and memory leaks.
            i.info.pop("exif", None)
            i.info.pop("dpi", None)
        except (OSError, ValueError) as e:
            logger.error("Failed to open image %s: %s", img_path, e)
            placeholder = torch.zeros((1, 64, 64, 3))
            return (placeholder, "ERROR", f"Failed to load image: {current_filename}")

        if i.mode != "RGB":
            i = i.convert("RGB")

        image: np.ndarray = np.array(i).astype(np.float32) / 255.0  # type: ignore[type-arg]
        image_tensor: torch.Tensor = torch.from_numpy(image)[None]

        return (image_tensor, filename_no_ext, stats)


NODE_CLASS_MAPPINGS = {
    "SequentialImageLoader": SequentialImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SequentialImageLoader": "Sequential Image Loader",
}

__all__: list[str] = ["SequentialImageLoader", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
