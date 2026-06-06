"""Image Saver Plus node for ComfyUI.

Saves images in PNG, JPEG, or WebP format with:
- Quality / compression control
- Filename template variables: %date:FORMAT%, %year%, %month%, %day%,
  %hour%, %minute%, %second%, %counter%, %batch_num%, %width%, %height%
- Optional .txt sidecar files saved alongside each image
- ComfyUI workflow metadata embedded in PNG files
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

import folder_paths
import numpy as np
import torch
from PIL import Image
from PIL.PngImagePlugin import PngInfo

logger: logging.Logger = logging.getLogger("ThatAIGod")

COMPRESS_MIN: int = 0
COMPRESS_MAX: int = 9
COMPRESS_DEFAULT: int = 4
QUALITY_MIN: int = 1
QUALITY_MAX: int = 100
QUALITY_DEFAULT: int = 95

_DATE_PATTERN: re.Pattern[str] = re.compile(r"%date:([^%]+)%")
# Ordered list of (token, strftime_code) pairs mapping Java/.NET-style date tokens
# to Python strftime format codes. Order matters: longer tokens (e.g. "yyyy") must
# be replaced before their substrings (e.g. "yy").
_DATE_FORMAT_MAP: list[tuple[str, str]] = [
    ("yyyy", "%Y"),
    ("yy", "%y"),
    ("MM", "%m"),
    ("dd", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
]

# Shorthand variable names and their equivalent strftime codes.
# These are expanded before %date:FORMAT% processing so that users can write
# %year% instead of the more verbose %date:yyyy%.
_SHORTHAND_VARS: list[tuple[str, str]] = [
    ("%year%", "%Y"),
    ("%month%", "%m"),
    ("%day%", "%d"),
    ("%hour%", "%H"),
    ("%minute%", "%M"),
    ("%second%", "%S"),
]


def _resolve_date_format(format_str: str) -> str:
    """Apply a Java/.NET-style date format string to the current local datetime.

    Tokens are replaced left-to-right (longer tokens first to avoid substring
    collisions), then ``datetime.strftime`` is called on the result.

    Args:
        format_str: A format string using tokens like ``yyyy``, ``MM``, ``dd``.

    Returns:
        The formatted date string, e.g. ``"2026_05_30"`` for ``"yyyy_MM_dd"``.
    """
    fmt: str = format_str
    for token, code in _DATE_FORMAT_MAP:
        fmt = fmt.replace(token, code)
    return datetime.now().strftime(fmt)


def _find_next_counter(folder: str, filename_template: str) -> int:
    """Scan *folder* for existing files that match *filename_template* and return the next counter.

    The template must contain the literal string ``%counter%`` exactly once.
    Existing files are matched via a regex that expects a zero-padded 5-digit
    counter in that position (e.g. ``img_00003_test.png``).  The function returns
    ``max_found + 1``, or ``1`` if no matching files exist.

    Args:
        folder: Absolute path to the output directory.  If the directory does not
            exist, ``1`` is returned immediately.
        filename_template: The filename stem (no extension) containing
            ``%counter%`` as a placeholder.

    Returns:
        The next available counter value (1-indexed).
    """
    if not os.path.isdir(folder):
        return 1
    prefix_part, suffix_part = filename_template.split("%counter%", 1)
    escaped: str = re.escape(prefix_part) + r"(\d{5})" + re.escape(suffix_part) + r"(?:\.[a-zA-Z0-9]+)?$"
    pattern: re.Pattern[str] = re.compile(escaped)
    max_c: int = 0
    for fname in os.listdir(folder):
        m = pattern.match(fname)
        if m:
            max_c = max(max_c, int(m.group(1)))
    return max_c + 1


class ImageSaverPlus:
    """ComfyUI output node that saves images with rich filename templating.

    Supports PNG (with embedded workflow metadata), JPEG, and WebP formats.
    Filename prefixes accept template variables that are expanded at save time:

    * ``%date:FORMAT%`` — current date/time in Java/.NET format (e.g. ``%date:yyyy_MM_dd%``)
    * ``%year%``, ``%month%``, ``%day%``, ``%hour%``, ``%minute%``, ``%second%`` — shorthand date parts
    * ``%counter%`` — sequential integer (5 digits, zero-padded) that auto-increments
      based on existing files in the output directory to prevent overwrites
    * ``%batch_num%`` — index of the current image within a batch
    * ``%width%``, ``%height%`` — image dimensions (handled by ComfyUI's folder_paths)

    An optional ``.txt`` sidecar file can be written alongside each saved image.
    """

    DESCRIPTION = "Saves images with format selection, quality control, and optional text sidecar file."

    def __init__(self) -> None:
        # output_dir is the ComfyUI output directory; type labels images for the UI gallery.
        self.output_dir: str = folder_paths.get_output_directory()
        self.type: str = "output"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {  # pragma: no cover
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to save."}),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "ThatAIGod",
                        "tooltip": (
                            "Prefix for the filename. Supports %width%, %height%, "
                            "%date:FORMAT% (e.g. %date:yyyy_MM_dd%), %year%, %month%, "
                            "%day%, %hour%, %minute%, %second%, "
                            "%counter% (sequential number, place anywhere in the name), "
                            "and %batch_num%."
                        ),
                    },
                ),
                "file_format": (
                    ["png", "jpeg", "webp"],
                    {"default": "png", "tooltip": "Output image format. PNG supports metadata; JPEG/WebP do not."},
                ),
                "quality": (
                    "INT",
                    {
                        "default": QUALITY_DEFAULT,
                        "min": QUALITY_MIN,
                        "max": QUALITY_MAX,
                        "step": 1,
                        "tooltip": "Quality for JPEG/WebP (1-100). Ignored for PNG where compress_level is used instead.",
                    },
                ),
                "compress_level": (
                    "INT",
                    {
                        "default": COMPRESS_DEFAULT,
                        "min": COMPRESS_MIN,
                        "max": COMPRESS_MAX,
                        "step": 1,
                        "tooltip": "PNG compression level (0-9). 0 = no compression, 9 = max. Ignored for JPEG/WebP.",
                    },
                ),
            },
            "optional": {
                "save_text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "multiline": True,
                        "tooltip": "Optional text to save as a .txt sidecar file alongside each image.",
                    },
                ),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES: tuple[()] = ()
    FUNCTION: str = "save_images"
    OUTPUT_NODE: bool = True
    CATEGORY: str = "ThatAIGod/Image Utils"

    def save_images(
        self,
        images: torch.Tensor,
        filename_prefix: str = "ThatAIGod",
        file_format: str = "png",
        quality: int = QUALITY_DEFAULT,
        compress_level: int = COMPRESS_DEFAULT,
        save_text: str | None = None,
        prompt: dict[str, Any] | None = None,
        extra_pnginfo: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a batch of images to the ComfyUI output directory.

        Template variables in *filename_prefix* are expanded in the following order:

        1. Shorthand date parts (``%year%``, ``%month%``, ``%day%``, ``%hour%``,
           ``%minute%``, ``%second%``) are replaced with the current local time.
        2. ``%date:FORMAT%`` patterns are replaced using :func:`_resolve_date_format`.
        3. ``%width%`` / ``%height%`` and path handling are delegated to
           ``folder_paths.get_save_image_path()``.
        4. ``%batch_num%`` is replaced per-image with the batch index.
        5. ``%counter%`` — if present — is replaced with a zero-padded 5-digit counter
           that is determined by scanning existing files (via :func:`_find_next_counter`)
           to avoid overwriting previous output.

        Args:
            images: A ``(N, H, W, 3)`` float32 tensor with values in ``[0, 1]``.
            filename_prefix: Filename stem with optional template variables.
            file_format: ``"png"``, ``"jpeg"``, or ``"webp"``.
            quality: JPEG/WebP quality (1–100).  Ignored for PNG.
            compress_level: PNG zlib compression level (0–9).  Ignored for JPEG/WebP.
            save_text: If provided, written to a ``.txt`` file alongside each image.
            prompt: ComfyUI workflow prompt dict embedded in PNG metadata.
            extra_pnginfo: Additional key/value pairs embedded in PNG metadata.

        Returns:
            A dict ``{"ui": {"images": [...]}}`` consumed by ComfyUI's gallery.
        """
        now = datetime.now()
        # Expand shorthand date variables first so they are not affected by %date:FORMAT%.
        for var, fmt_code in _SHORTHAND_VARS:
            if var in filename_prefix:
                filename_prefix = filename_prefix.replace(var, now.strftime(fmt_code))

        filename_prefix = _DATE_PATTERN.sub(lambda m: _resolve_date_format(m.group(1)), filename_prefix)
        full_output_folder: str
        filename: str
        counter: int
        subfolder: str
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0]
        )

        if "%counter%" in filename:
            counter = _find_next_counter(full_output_folder, filename)

        results: list[dict[str, str]] = []
        for batch_number, image in enumerate(images):
            i: np.ndarray = 255.0 * image.cpu().numpy()
            img: Image.Image = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            filename_with_batch: str = filename.replace("%batch_num%", str(batch_number))
            if "%counter%" in filename_with_batch:
                base_file: str = filename_with_batch.replace("%counter%", f"{counter:05}")
            else:
                base_file = f"{filename_with_batch}_{counter:05}_"
            file: str = f"{base_file}.{file_format}"

            file_path: str = os.path.join(full_output_folder, file)

            try:
                if file_format == "png":
                    metadata: PngInfo | None = None
                    if prompt is not None:
                        metadata = PngInfo()
                        metadata.add_text("prompt", json.dumps(prompt))
                    if extra_pnginfo is not None:
                        if metadata is None:
                            metadata = PngInfo()
                        for k, v in extra_pnginfo.items():
                            metadata.add_text(k, json.dumps(v))
                    img.save(file_path, pnginfo=metadata, compress_level=compress_level)
                elif file_format == "jpeg":
                    img.save(file_path, quality=quality)
                elif file_format == "webp":
                    img.save(file_path, quality=quality)

                if save_text:
                    text_file: str = f"{base_file}.txt"
                    text_path: str = os.path.join(full_output_folder, text_file)
                    with open(text_path, "w", encoding="utf-8") as f:
                        f.write(save_text)
            except OSError as e:
                logger.error("Failed to save %s: %s", file_path, e)

            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1

        return {"ui": {"images": results}}


NODE_CLASS_MAPPINGS = {
    "ImageSaverPlus": ImageSaverPlus,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageSaverPlus": "Image Saver Plus",
}

__all__: list[str] = ["ImageSaverPlus", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
