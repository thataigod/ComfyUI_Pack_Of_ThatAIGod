import logging
import os
import re
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageOps

logger = logging.getLogger("ThatAIGod")

VALID_IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff",
)


class SequentialImageLoader:
    DESCRIPTION = "Loads images sequentially from a directory using a seed as the index. Supports natural sort ordering and multiple image formats."

    RETURN_TYPES: tuple[str, ...] = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Image", "Filename", "Stats")
    FUNCTION: str = "load_next"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Directory Path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "C:\\Images\\Dataset",
                    },
                ),
                "seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "step": 1},
                ),
            }
        }

    @staticmethod
    def natural_sort_key(s: str) -> list[tuple[int, int | str]]:
        # Split on digit boundaries; sort numeric parts as ints, text as lowercase
        return [
            (0, int(text)) if text.isdigit() else (1, text.lower())
            for text in re.split(r"(\d+)", s)
        ]

    def load_next(self, **kwargs: Any) -> tuple[torch.Tensor, str, str]:
        directory_path: str = kwargs.get("Directory Path", "")
        index: int = kwargs.get("seed", 0)

        if not directory_path or not os.path.isdir(directory_path):
            raise ValueError(f"Directory not found: {directory_path}")

        files: list[str] = [
            f
            for f in os.listdir(directory_path)
            if f.lower().endswith(VALID_IMAGE_EXTENSIONS)
        ]
        files.sort(key=self.natural_sort_key)

        total_files: int = len(files)
        if total_files == 0:
            raise FileNotFoundError(f"No supported image files found in {directory_path}")

        safe_index: int = index % total_files
        current_filename: str = files[safe_index]

        filename_no_ext: str = os.path.splitext(current_filename)[0]
        stats: str = f"{safe_index + 1}/{total_files}"

        logger.info("Processing %s: %s", stats, current_filename)

        img_path: str = os.path.join(directory_path, current_filename)
        i: Image.Image = Image.open(img_path)
        i = ImageOps.exif_transpose(i)
        i.info.pop("exif", None)
        i.info.pop("dpi", None)

        if i.mode != "RGB":
            i = i.convert("RGB")

        image: np.ndarray = np.array(i).astype(np.float32) / 255.0
        image_tensor: torch.Tensor = torch.from_numpy(image)[None,]

        return (image_tensor, filename_no_ext, stats)


NODE_CLASS_MAPPINGS = {
    "SequentialImageLoader": SequentialImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SequentialImageLoader": "Sequential Image Loader",
}
