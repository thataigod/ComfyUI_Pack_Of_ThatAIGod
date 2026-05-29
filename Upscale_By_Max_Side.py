import logging
import torch
from typing import Any
import comfy.utils

logger: logging.Logger = logging.getLogger("ThatAIGod")


class UpscaleByMaxSide:
    RETURN_TYPES: tuple[str, ...] = ("IMAGE", "INT", "INT")
    RETURN_NAMES: tuple[str, ...] = ("Image", "Width", "Height")
    FUNCTION: str = "upscale"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Image": ("IMAGE",),
                "Max Side": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 8}),
                "Divisibility": ("INT", {"default": 8, "min": 1, "max": 128, "step": 1}),
                "Method": (["lanczos", "bicubic", "bilinear", "nearest-exact", "area"], {"default": "lanczos"}),
            }
        }

    def upscale(self, **kwargs: Any) -> tuple[torch.Tensor, int, int]:
        image: torch.Tensor = kwargs.get("Image")
        max_side: int = kwargs.get("Max Side", 1024)
        divisibility: int = kwargs.get("Divisibility", 8)
        method: str = kwargs.get("Method", "lanczos")

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
            logger.info("Center-cropping from %dx%d to %dx%d to meet divisibility=%d", scale_w, scale_h, target_w, target_h, divisibility)
            s = s[:, h_start:h_start + target_h, w_start:w_start + target_w, :]

        return (s, target_w, target_h)

NODE_CLASS_MAPPINGS = {
    "UpscaleByMaxSide": UpscaleByMaxSide
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UpscaleByMaxSide": "Upscale By Max Side"
}