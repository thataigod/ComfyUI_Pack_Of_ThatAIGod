"""Upscale By Size node for ComfyUI.

Provides :class:`UpscaleByMaxSide`, which upscales an image to a target pixel
budget — the longest side, the shortest side, or the total pixel area — while
preserving the original aspect ratio.

When divisibility constraints require slightly different dimensions, a minimal
centre-crop is applied after upscaling to bring the dimensions to the nearest
valid multiple — this is preferable to padding, which would change the apparent
aspect ratio.
"""

import json
import logging
import math
from typing import Any

import comfy.utils
import torch

from _utils import clamp_dimension

logger: logging.Logger = logging.getLogger("ThatAIGod")

# Defaults and limits for the node's input widgets.
DEFAULT_MAX_SIDE: int = 1024
DEFAULT_DIVISIBILITY: int = 8
DEFAULT_UPSCALE_METHOD: str = "lanczos"
MIN_MAX_SIDE: int = 64
MAX_MAX_SIDE: int = 16384
DEFAULT_TOTAL_PIXELS: int = 1_000_000
MIN_TOTAL_PIXELS: int = MIN_MAX_SIDE * MIN_MAX_SIDE
MAX_TOTAL_PIXELS: int = MAX_MAX_SIDE * MAX_MAX_SIDE
DIVISIBILITY_STEP: int = 1
MIN_DIVISIBILITY: int = 1
MAX_DIVISIBILITY: int = 128

# Per-mode Target memory stored in the Size Config JSON.  The frontend
# (js/upscale_by_size.js) remembers the last Target used for each Limit By mode
# and recalls it on switch.  Keys must stay in sync with MODE_SIZE_KEYS in the JS.
_DEFAULT_SIZE_CONFIG_JSON: str = json.dumps(
    {
        "size_max": DEFAULT_MAX_SIDE,
        "size_min": DEFAULT_MAX_SIDE,
        "size_total": DEFAULT_TOTAL_PIXELS,
    }
)


def _scale_dimensions(limit_by: str, target: int, ratio: float) -> tuple[int, int]:
    """Return the pre-divisibility ``(width, height)`` for a target budget.

    Args:
        limit_by: One of ``"Max Side"``, ``"Min Side"``, or ``"Total Pixels"``.
        target: Pixel budget for the constrained side or total area.
        ratio: Image width-to-height ratio.

    Returns:
        A ``(width, height)`` tuple preserving *ratio* before divisibility
        rounding and centre-cropping.
    """
    if limit_by == "Total Pixels":
        area: int = clamp_dimension(target, MIN_TOTAL_PIXELS, MAX_TOTAL_PIXELS)
        return int(round(math.sqrt(area * ratio))), int(round(math.sqrt(area / ratio)))

    side: int = clamp_dimension(target, MIN_MAX_SIDE, MAX_MAX_SIDE)
    if limit_by == "Min Side":
        if ratio >= 1.0:
            return int(round(side * ratio)), side
        return side, int(round(side / ratio))

    # Default: Max Side.
    if ratio >= 1.0:
        return side, int(round(side / ratio))
    return int(round(side * ratio)), side


class UpscaleByMaxSide:
    """Upscales an image to a target pixel budget, preserving aspect ratio.

    The budget constrains the longest side (Max Side), the shortest side
    (Min Side), or the total pixel area (Total Pixels).  The frontend remembers
    the last Target per mode and recalls it when switching.  Divisibility is
    enforced via a symmetric centre-crop, removing at most ``(divisibility - 1)``
    pixels from each affected edge.
    """

    DESCRIPTION = "Upscales an image to a target max side, min side, or total pixel area, with configurable method and divisibility constraints."

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
                "Limit By": (
                    ["Max Side", "Min Side", "Total Pixels"],
                    {
                        "tooltip": (
                            "What the Target value constrains: the longest side (Max), "
                            "the shortest side (Min), or the total image area (Total)."
                        )
                    },
                ),
                "Target": (
                    "INT",
                    {
                        "default": DEFAULT_MAX_SIDE,
                        "min": 1,
                        "max": MAX_TOTAL_PIXELS,
                        "step": 1,
                        "tooltip": (
                            "Pixel budget: side length for Max/Min Side modes, total "
                            "image area (e.g. 1000000 ≈ 1MP) for Total Pixels mode. "
                            "The last value per mode is remembered and recalled on switch."
                        ),
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
                "Size Config": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": _DEFAULT_SIZE_CONFIG_JSON,
                        "tooltip": (
                            "JSON config managed by the frontend. "
                            'Format: {"size_max": 1024, "size_min": 1024, "size_total": 1000000}'
                        ),
                    },
                ),
            }
        }

    def upscale(self, **kwargs: Any) -> tuple[torch.Tensor, int, int]:
        """Upscale the input image to the target size budget.

        Algorithm:

        1. Determine scale dimensions from *Limit By* / *Target*, preserving the
           original aspect ratio.
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
                ``"Limit By"`` (str), ``"Target"`` (int), ``"Divisibility"`` (int),
                ``"Method"`` (str).

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

        limit_by: str = kwargs.get("Limit By", "Max Side")
        target: int = kwargs.get("Target", DEFAULT_MAX_SIDE)
        divisibility: int = kwargs.get("Divisibility", DEFAULT_DIVISIBILITY)
        method: str = kwargs.get("Method", DEFAULT_UPSCALE_METHOD)

        # ComfyUI image shape: (N, H, W, C)
        _, h, w, _ = image.shape
        ratio = w / h

        scale_w, scale_h = _scale_dimensions(limit_by, target, ratio)

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
    "UpscaleByMaxSide": "Upscale By Size",
}

__all__: list[str] = ["UpscaleByMaxSide", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
