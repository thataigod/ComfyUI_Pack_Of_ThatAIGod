import os
import torch
import numpy as np
import re
import logging
from typing import Any
from PIL import Image, ImageOps


logger = logging.getLogger("ThatAIGod")


class SequentialImageLoader:
    RETURN_TYPES: tuple[str, ...] = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Image", "Filename", "Stats")
    FUNCTION: str = "load_next"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Directory Path": ("STRING", {"default": "", "multiline": False, "placeholder": "C:\\Images\\Dataset"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "step": 1}),
            }
        }

    def natural_sort_key(self, s: str) -> list[tuple[int, int | str]]:
        return [(0, int(text)) if text.isdigit() else (1, text.lower()) for text in re.split(r'(\d+)', s)]

    def load_next(self, **kwargs: Any) -> tuple[torch.Tensor, str, str]:
        directory_path: str = kwargs.get("Directory Path", "")
        index: int = kwargs.get("seed", 0)

        if not directory_path or not os.path.exists(directory_path):
            logger.error("Directory not found -> %s", directory_path)
            return (torch.zeros((1, 64, 64, 3)), "error_no_dir", "0/0")

        valid_extensions: tuple[str, ...] = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff')
        files: list[str] = [f for f in os.listdir(directory_path) if f.lower().endswith(valid_extensions)]
        files.sort(key=self.natural_sort_key)

        total_files: int = len(files)
        if total_files == 0:
            logger.warning("No images found in %s", directory_path)
            return (torch.zeros((1, 64, 64, 3)), "error_empty_dir", "0/0")

        safe_index: int = index % total_files
        current_filename: str = files[safe_index]

        filename_no_ext: str = os.path.splitext(current_filename)[0]
        stats: str = f"{safe_index + 1}/{total_files}"

        logger.info("Processing %s: %s", stats, current_filename)

        try:
            img_path: str = os.path.join(directory_path, current_filename)
            i: Image.Image = Image.open(img_path)
            i = ImageOps.exif_transpose(i)
            i.info.pop("exif", None)
            i.info.pop("dpi", None)

            if i.mode != 'RGB':
                i = i.convert('RGB')

            image: np.ndarray = np.array(i).astype(np.float32) / 255.0
            image_tensor: torch.Tensor = torch.from_numpy(image)[None,]

            return (image_tensor, filename_no_ext, stats)

        except Exception as e:
            logger.error("Failed to load %s: %s", current_filename, e)
            return (torch.zeros((1, 64, 64, 3)), "error_load", stats)

NODE_CLASS_MAPPINGS = {
    "SequentialImageLoader": SequentialImageLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SequentialImageLoader": "Sequential Image Loader"
}