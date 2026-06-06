"""Upscale By Max Side node for ComfyUI.

Provides :class:`UpscaleByMaxSide`, which upscales an image so that its longest
side matches a target pixel count, preserving the original aspect ratio.

When divisibility constraints require slightly different dimensions, a minimal
centre-crop is applied after upscaling to bring the dimensions to the nearest
valid multiple — this is preferable to padding, which would change the apparent
aspect ratio.
"""

import logging
from typing import Any

import comfy.utils
import torch

logger: logging.Logger = logging.getLogger("ThatAIGod")

# Defaults and limits for the node's input widgets.
DEFAULT_MAX_SIDE: int = 1024
DEFAULT_DIVISIBILITY: int = 8
DEFAULT_UPSCALE_METHOD: str = "lanczos"
MIN_MAX_SIDE: int = 64
MAX_MAX_SIDE: int = 16384
DIVISIBILITY_STEP: int = 1
MIN_DIVISIBILITY: int = 1
MAX_DIVISIBILITY: int = 128


class UpscaleByMaxSide:
    """Upscales an image so its longest side matches a target pixel value.

    Preserves aspect ratio and enforces divisibility constraints via centre-crop.
    The crop removes at most ``(divisibility - 1)`` pixels from each affected edge.
    """

    DESCRIPTION = "Upscales an image so its longest side matches a target pixel value, with configurable method and divisibility constraints."

    RETURN_TYPES: tuple[str, ...] = ("IMAGE", "INT", "INT")
    RETURN_NAMES: tuple[str, ...] = ("Image", "Width", "Height")
    FUNCTION: str = "upscale"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Image": (
                    "IMAGE",
                    {"tooltip": "Input image tensor of shape (N, H, W, C)."},
                ),
                "Max Side": (
                    "INT",
                    {
                        "default": DEFAULT_MAX_SIDE,
                        "min": MIN_MAX_SIDE,
                        "max": MAX_MAX_SIDE,
                        "step": 8,
                        "tooltip": "Target pixel count for the longest side of the output image.",
                    },
                ),
                "Divisibility": (
                    "INT",
                    {
                        "default": DEFAULT_DIVISIBILITY,
                        "min": MIN_DIVISIBILITY,
                        "max": MAX_DIVISIBILITY,
                        "step": DIVISIBILITY_STEP,
                        "tooltip": (
                            "Output dimensions are rounded down to the nearest multiple of this value. "
                            "Use 8 for most diffusion models, 64 for some architectures."
                        ),
                    },
                ),
                "Method": (
                    ["lanczos", "bicubic", "bilinear", "nearest-exact", "area"],
                    {
                        "default": DEFAULT_UPSCALE_METHOD,
                        "tooltip": "Interpolation method. Lanczos gives the sharpest result for most images.",
                    },
                ),
            }
        }

    def upscale(self, **kwargs: Any) -> tuple[torch.Tensor, int, int]:
        """Upscale the input image to the target max-side size.

        Algorithm:

        1. Determine scale dimensions so the longest side equals *Max Side*,
           preserving the original aspect ratio.
        2. Enforce a minimum of *Divisibility* pixels on each side.
        3. Upscale using ``comfy.utils.common_upscale`` with ``crop="disabled"``
           (no auto-crop by ComfyUI).
        4. Compute the largest dimensions that satisfy the divisibility constraint
           (floor division).
        5. If the upscaled dimensions differ from the target, apply a symmetric
           centre-crop to remove the excess pixels.

        .. note::
            ComfyUI image tensors have shape ``(N, H, W, C)`` (batch, height, width,
            channels).  ``comfy.utils.common_upscale`` expects ``(N, C, H, W)``
            (channels-first), so the tensor is transposed before and after the call.

        Args:
            **kwargs: ComfyUI widget values.  Expected keys: ``"Image"`` (tensor),
                ``"Max Side"`` (int), ``"Divisibility"`` (int), ``"Method"`` (str).

        Returns:
            A 3-tuple ``(upscaled_image, final_width, final_height)``:

            * ``upscaled_image`` — shape ``(N, final_height, final_width, C)`` float32.
            * ``final_width`` — width in pixels, divisible by *Divisibility*.
            * ``final_height`` — height in pixels, divisible by *Divisibility*.

        Raises:
            ValueError: If the ``"Image"`` input is ``None``.
        """
        image: torch.Tensor | None = kwargs.get("Image")
        if image is None:
            raise ValueError("Image input is required but was not provided.")

        max_side: int = kwargs.get("Max Side", DEFAULT_MAX_SIDE)
        divisibility: int = kwargs.get("Divisibility", DEFAULT_DIVISIBILITY)
        method: str = kwargs.get("Method", DEFAULT_UPSCALE_METHOD)

        # ComfyUI image shape: (N, H, W, C)
        _, h, w, _ = image.shape
        ratio = w / h

        if w > h:
            scale_w = max_side
            scale_h = int(max_side / ratio)
        else:
            scale_h = max_side
            scale_w = int(max_side * ratio)

        # Ensure neither dimension falls below the divisibility floor.
        scale_w = max(scale_w, divisibility)
        scale_h = max(scale_h, divisibility)

        # comfy.utils.common_upscale expects (N, C, H, W); "disabled" means no auto-crop.
        samples = image.movedim(-1, 1)
        s = comfy.utils.common_upscale(samples, scale_w, scale_h, method, "disabled")
        s = s.movedim(1, -1)

        target_w = (scale_w // divisibility) * divisibility
        target_h = (scale_h // divisibility) * divisibility

        target_w = max(target_w, divisibility)
        target_h = max(target_h, divisibility)

        # Centre-crop to enforce divisibility after upscale preserves aspect ratio
        if target_w != scale_w or target_h != scale_h:
            h_start = (scale_h - target_h) // 2
            w_start = (scale_w - target_w) // 2
            logger.info(
                "Centre-cropping from %dx%d to %dx%d to meet divisibility=%d",
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

__all__: list[str] = ["UpscaleByMaxSide", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
