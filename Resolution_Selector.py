"""Resolution Selector node for ComfyUI.

Provides :class:`ResolutionSelector`, which calculates optimal image dimensions
from a pixel budget (constrained to either the max side or the min side) and a
user-defined set of one or more aspect ratios.

Supports:
* Constraint mode: ``Max Side`` (longest dimension = pixels) or ``Min Side``
  (shortest dimension = pixels).
* Multi-select aspect ratios — any subset of 12 named presets plus an optional
  custom W:H ratio — with random selection from the active set.
* Three batch-selection shortcuts (Select All, Portraits, Landscapes) via the
  ``js/resolution_selector.js`` frontend extension.
* Custom W:H ratio via a ``Custom W:H Ratio`` widget.
* Optional scale factor for upscale targets.
* Keyword output for aspect-ratio prompt injection.
* Live output-pin value labels via the ``that_ai_god.stream`` WebSocket extension.
"""

import json
import random
from typing import Any

from _utils import (
    DEFAULT_MIN_DIMENSION,
    clamp_dimension,
    compute_aspect_ratio_dimensions,
    round_to_multiple,
)

# --- Constants -----------------------------------------------------------

MIN_SCALE_FACTOR: float = 0.1
MAX_SCALE_FACTOR: float = 8.0
DEFAULT_SCALE_FACTOR: float = 1.5
DEFAULT_PIXELS: int = 1024
MIN_PIXELS: int = 1
MAX_PIXELS: int = 16384

# Aspect ratio presets (identical to Dynamic_Resolution_Picker).
_PORTRAITS: dict[str, float] = {
    "Portrait 2:3 (Classic)": 2 / 3,
    "Portrait 3:4 (Standard)": 3 / 4,
    "Portrait 4:5 (Social)": 4 / 5,
    "Portrait 9:16 (Mobile)": 9 / 16,
}

_LANDSCAPES: dict[str, float] = {
    "Landscape 3:2 (Classic)": 3 / 2,
    "Landscape 4:3 (Standard)": 4 / 3,
    "Landscape 5:4 (Display)": 5 / 4,
    "Landscape 16:9 (HD)": 16 / 9,
    "Landscape 16:10 (Monitor)": 16 / 10,
    "Landscape 21:9 (Ultrawide)": 21 / 9,
    "Landscape 1.85:1 (Cinema)": 1.85,
}

_SQUARE: dict[str, float] = {"Square 1:1": 1.0}

_ALL_RATIOS: dict[str, float] = {**_PORTRAITS, **_LANDSCAPES, **_SQUARE}

_KEYWORD_MAP: dict[str, str] = {
    "Square 1:1": "Square, 1:1 Aspect Ratio, Boxed Composition",
    "Portrait 2:3 (Classic)": "Portrait, 2:3 Aspect Ratio, Vertical Orientation",
    "Portrait 3:4 (Standard)": "Portrait, 3:4 Aspect Ratio, Vertical Format",
    "Portrait 4:5 (Social)": "Portrait, 4:5 Aspect Ratio, Vertical Composition",
    "Portrait 9:16 (Mobile)": "Portrait, 9:16 Aspect Ratio, Full Screen Vertical",
    "Landscape 3:2 (Classic)": "Landscape, 3:2 Aspect Ratio, Horizontal Orientation",
    "Landscape 4:3 (Standard)": "Landscape, 4:3 Aspect Ratio, Standard View",
    "Landscape 5:4 (Display)": "Landscape, 5:4 Aspect Ratio, Wide Format",
    "Landscape 16:9 (HD)": "Landscape, 16:9 Aspect Ratio, Widescreen Format",
    "Landscape 16:10 (Monitor)": "Landscape, 16:10 Aspect Ratio, Wide Display",
    "Landscape 21:9 (Ultrawide)": "Landscape, 21:9 Aspect Ratio, Ultra-Wide Panoramic",
    "Landscape 1.85:1 (Cinema)": "Landscape, 1.85:1 Aspect Ratio, Theatrical Format",
}

_ALL_LABELS: list[str] = list(_ALL_RATIOS.keys())
_PORTRAIT_LABELS: list[str] = list(_PORTRAITS.keys())
_LANDSCAPE_LABELS: list[str] = list(_LANDSCAPES.keys())

# Default config — portraits selected by default, custom disabled.
_DEFAULT_CONFIG_JSON: str = json.dumps({"ratios": _PORTRAIT_LABELS, "custom_ratio": 1.0, "custom_enabled": False})


def _compute_dimensions_from_min_side(min_side: int, ratio: float) -> tuple[int, int]:
    """Compute width and height from a *min_side* pixel budget and aspect *ratio*.

    Args:
        min_side: Target pixel count for the *shorter* side of the image.
        ratio: Width-to-height ratio (e.g. ``16/9 ≈ 1.778``).

    Returns:
        A ``(width, height)`` tuple, both rounded to 8 px and clamped to 64 px.
    """
    if ratio >= 1.0:
        h = float(min_side)
        w = min_side * ratio
    else:
        w = float(min_side)
        h = min_side / ratio

    width_int = max(round_to_multiple(int(round(w))), DEFAULT_MIN_DIMENSION)
    height_int = max(round_to_multiple(int(round(h))), DEFAULT_MIN_DIMENSION)
    return width_int, height_int


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


class ResolutionSelector:
    """Calculates image dimensions with flexible constraint and multi-select aspect ratios.

    Choose whether the *Pixels* input constrains the **max** side (longest edge)
    or the **min** side (shortest edge).  Select any number of aspect ratio presets
    (portrait, landscape, square) plus an optional custom W:H ratio.  One ratio is
    chosen at random from the active set on each execution.
    """

    DESCRIPTION = (
        "Calculates width and height from a pixel budget constrained to either the "
        "max side or the min side, with multi-select aspect ratios and optional scaling."
    )

    RETURN_TYPES: tuple[str, ...] = (
        "INT",
        "INT",
        "INT",
        "INT",
        "FLOAT",
        "STRING",
        "INT",
        "INT",
    )
    RETURN_NAMES: tuple[str, ...] = (
        "Width",
        "Height",
        "Scaled Width",
        "Scaled Height",
        "Scale Factor",
        "Keywords",
        "Guide Size",
        "Max Size",
    )
    FUNCTION: str = "calculate"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Limit By": (
                    ["Max Side", "Min Side"],
                    {"tooltip": "Whether the Pixels value constrains the longest side (Max) or shortest side (Min)."},
                ),
                "Pixels": (
                    "INT",
                    {
                        "default": DEFAULT_PIXELS,
                        "min": MIN_PIXELS,
                        "max": MAX_PIXELS,
                        "step": 1,
                        "tooltip": "Pixel budget for the constrained side (max or min, depending on Limit By).",
                    },
                ),
                "Scale Factor": (
                    "FLOAT",
                    {
                        "default": DEFAULT_SCALE_FACTOR,
                        "min": MIN_SCALE_FACTOR,
                        "max": MAX_SCALE_FACTOR,
                        "step": 0.05,
                        "tooltip": "Multiplier applied to base dimensions for Scaled Width/Height outputs.",
                    },
                ),
                "Aspect Ratio Config": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": _DEFAULT_CONFIG_JSON,
                        "tooltip": (
                            "JSON config managed by the frontend. "
                            'Format: {"ratios": [...], "custom_ratio": 1.0, "custom_enabled": false}'
                        ),
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "tooltip": "Seed for random ratio selection from the active set.",
                    },
                ),
            },
        }

    @staticmethod
    def _resolve_active_ratios(
        config_json: str,
    ) -> list[tuple[str, float]]:
        """Parse the JSON config and return the list of active ``(label, ratio)`` pairs.

        Args:
            config_json: JSON string from the Aspect Ratio Config widget.

        Returns:
            List of ``(label, ratio_float)`` tuples for all active ratios.
            Falls back to all named presets if parsing fails or the list is empty.
        """
        try:
            cfg: dict[str, Any] = json.loads(config_json)
        except (json.JSONDecodeError, TypeError):
            cfg = {}

        selected_names: list[str] = cfg.get("ratios", [])
        custom_enabled: bool = cfg.get("custom_enabled", False)
        custom_ratio: float = float(cfg.get("custom_ratio", 1.0))

        active: list[tuple[str, float]] = []
        for name in selected_names:
            if name in _ALL_RATIOS:
                active.append((name, _ALL_RATIOS[name]))

        if custom_enabled:
            active.append(("Custom W:H", custom_ratio))

        if not active:
            active = list(_ALL_RATIOS.items())

        return active

    def calculate(self, **kwargs: Any) -> dict[str, Any]:
        """Calculate dimensions and return results for UI and downstream nodes.

        Args:
            **kwargs: ComfyUI widget values. Expected keys: ``"Limit By"``,
                ``"Pixels"``, ``"Scale Factor"``, ``"Aspect Ratio Config"``,
                ``"Custom W:H Ratio"``, ``"seed"``.

        Returns:
            A dict with ``"ui"`` values (consumed by ``js/resolution_selector.js``)
            and an 8-tuple ``"result"`` matching the same shape as
            :class:`DynamicResolution`.
        """
        limit_by: str = kwargs.get("Limit By", "Max Side")
        pixels: int = kwargs.get("Pixels", DEFAULT_PIXELS)
        scale_factor: float = kwargs.get("Scale Factor", DEFAULT_SCALE_FACTOR)
        config_json: str = kwargs.get("Aspect Ratio Config", _DEFAULT_CONFIG_JSON)
        seed: int = kwargs.get("seed", 0)

        pixels = clamp_dimension(pixels, MIN_PIXELS, MAX_PIXELS)
        scale_factor = max(MIN_SCALE_FACTOR, min(scale_factor, MAX_SCALE_FACTOR))

        rng: random.Random = random.Random(seed)
        active_ratios: list[tuple[str, float]] = self._resolve_active_ratios(config_json)

        target_label, ratio_float = rng.choice(sorted(active_ratios))

        if limit_by == "Max Side":
            width_int, height_int = compute_aspect_ratio_dimensions(pixels, ratio_float)
        else:
            width_int, height_int = _compute_dimensions_from_min_side(pixels, ratio_float)

        keywords: str = _KEYWORD_MAP.get(target_label, f"Custom {ratio_float:.2f} Aspect Ratio, Custom Composition")

        guide_size: int = min(width_int, height_int)
        max_size_val: int = max(width_int, height_int)

        s_width: float = width_int * scale_factor
        s_height: float = height_int * scale_factor
        scaled_width: int = int(round(s_width / 8) * 8)
        scaled_height: int = int(round(s_height / 8) * 8)

        actual_mp: float = (width_int * height_int) / 1_000_000

        info_string: str = (
            f"Limit By: {limit_by} ({pixels}px)\n"
            f"Ratio:    {target_label} ({ratio_float:.4f})\n"
            f"Base:     {width_int}x{height_int} ({actual_mp:.2f} MP)\n"
            f"Scaled:   {scaled_width}x{scaled_height} (x{scale_factor})\n"
            f"Keywords: {keywords}"
        )

        return {
            "ui": {
                "text": [info_string],
                "width": [width_int],
                "height": [height_int],
                "scaled_width": [scaled_width],
                "scaled_height": [scaled_height],
                "scale_factor": [scale_factor],
                "guide_size": [guide_size],
                "max_size": [max_size_val],
            },
            "result": (
                width_int,
                height_int,
                scaled_width,
                scaled_height,
                scale_factor,
                keywords,
                guide_size,
                max_size_val,
            ),
        }


NODE_CLASS_MAPPINGS = {
    "DynamicResolutionSelector": ResolutionSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DynamicResolutionSelector": "Dynamic Resolution Selector",
}

__all__: list[str] = ["ResolutionSelector", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
