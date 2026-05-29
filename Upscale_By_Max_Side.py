import logging
from typing import Any
import torch
import comfy.utils


logger: logging.Logger = logging.getLogger("ThatAIGod")

DEFAULT_MAX_SIDE: int = 1024
DEFAULT_DIVISIBILITY: int = 8
DEFAULT_UPSCALE_METHOD: str = "lanczos"
MIN_MAX_SIDE: int = 64
MAX_MAX_SIDE: int = 16384
DIVISIBILITY_STEP: int = 1
MIN_DIVISIBILITY: int = 1
MAX_DIVISIBILITY: int = 128


class UpscaleByMaxSide:
    DESCRIPTION = "Upscales an image so its longest side matches a target pixel value, with configurable method and divisibility constraints."

    RETURN_TYPES: tuple[str, ...] = ("IMAGE", "INT", "INT")
    RETURN_NAMES: tuple[str, ...] = ("Image", "Width", "Height")
    FUNCTION: str = "upscale"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Image": ("IMAGE",),
                "Max Side": ("INT", {"default": DEFAULT_MAX_SIDE, "min": MIN_MAX_SIDE, "max": MAX_MAX_SIDE, "step": 8}),
                "Divisibility": ("INT", {"default": DEFAULT_DIVISIBILITY, "min": MIN_DIVISIBILITY, "max": MAX_DIVISIBILITY, "step": DIVISIBILITY_STEP}),
                "Method": (
                    ["lanczos", "bicubic", "bilinear", "nearest-exact", "area"],
                    {"default": DEFAULT_UPSCALE_METHOD},
                ),
            }
        }

    def upscale(self, **kwargs: Any) -> tuple[torch.Tensor, int, int]:
        image: torch.Tensor | None = kwargs.get("Image")
        if image is None:
            raise ValueError("Image input is required but was not provided.")

        max_side: int = kwargs.get("Max Side", DEFAULT_MAX_SIDE)
        divisibility: int = kwargs.get("Divisibility", DEFAULT_DIVISIBILITY)
        method: str = kwargs.get("Method", DEFAULT_UPSCALE_METHOD)

        _, h, w, _ = image.shape
        ratio = w / h

        if w > h:
            scale_w = max_side
            scale_h = int(max_side / ratio)
        else:
            scale_h = max_side
            scale_w = int(max_side * ratio)

        scale_w = max(scale_w, divisibility)
        scale_h = max(scale_h, divisibility)

        samples = image.movedim(-1, 1)
        s = comfy.utils.common_upscale(samples, scale_w, scale_h, method, "disabled")
        s = s.movedim(1, -1)

        target_w = (scale_w // divisibility) * divisibility
        target_h = (scale_h // divisibility) * divisibility

        target_w = max(target_w, divisibility)
        target_h = max(target_h, divisibility)

        if target_w != scale_w or target_h != scale_h:
            h_start = (scale_h - target_h) // 2
            w_start = (scale_w - target_w) // 2
            logger.info(
                "Center-cropping from %dx%d to %dx%d to meet divisibility=%d",
                scale_w,
                scale_h,
                target_w,
                target_h,
                divisibility,
            )
            s = s[:, h_start : h_start + target_h, w_start : w_start + target_w, :]

        return (s, target_w, target_h)


NODE_CLASS_MAPPINGS = {
    "UpscaleByMaxSide": UpscaleByMaxSide,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UpscaleByMaxSide": "Upscale By Max Side",
}
