"""Resolution Selector node for ComfyUI.

Provides :class:`ResolutionSelector`, which calculates optimal image dimensions
from a pixel budget (constrained to the max side, the min side, or the total
pixel area) and a user-defined set of one or more aspect ratios.

Supports:
* Constraint mode: ``Max Side`` (longest dimension = pixels), ``Min Side``
  (shortest dimension = pixels), or ``Total Pixels`` (width × height ≈ pixels).
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
import math
import random
from fractions import Fraction
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
DEFAULT_TOTAL_PIXELS: int = 1_000_000
MIN_TOTAL_PIXELS: int = DEFAULT_MIN_DIMENSION * DEFAULT_MIN_DIMENSION
MAX_TOTAL_PIXELS: int = MAX_PIXELS * MAX_PIXELS

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
    "Square 1:1": "square orientation, 1:1 aspect ratio, centered symmetrical composition",
    "Portrait 2:3 (Classic)": "portrait orientation, 2:3 aspect ratio, classic vertical composition",
    "Portrait 3:4 (Standard)": "portrait orientation, 3:4 aspect ratio, standard vertical composition",
    "Portrait 4:5 (Social)": "portrait orientation, 4:5 aspect ratio, tight vertical composition",
    "Portrait 9:16 (Mobile)": "portrait orientation, 9:16 aspect ratio, tall vertical composition",
    "Landscape 3:2 (Classic)": "landscape orientation, 3:2 aspect ratio, classic horizontal composition",
    "Landscape 4:3 (Standard)": "landscape orientation, 4:3 aspect ratio, standard horizontal composition",
    "Landscape 5:4 (Display)": "landscape orientation, 5:4 aspect ratio, balanced horizontal composition",
    "Landscape 16:9 (HD)": "landscape orientation, 16:9 aspect ratio, widescreen composition",
    "Landscape 16:10 (Monitor)": "landscape orientation, 16:10 aspect ratio, wide panoramic composition",
    "Landscape 21:9 (Ultrawide)": "landscape orientation, 21:9 aspect ratio, ultrawide panoramic composition",
    "Landscape 1.85:1 (Cinema)": "landscape orientation, 1.85:1 aspect ratio, theatrical widescreen composition",
}

_ALL_LABELS: list[str] = list(_ALL_RATIOS.keys())
_PORTRAIT_LABELS: list[str] = list(_PORTRAITS.keys())
_LANDSCAPE_LABELS: list[str] = list(_LANDSCAPES.keys())

# Per-mode Pixels memory keys stored in the Aspect Ratio Config JSON.
# The frontend (js/resolution_selector.js) remembers the last Pixels value used
# for each Limit By mode here and recalls it when the mode is switched, so each
# mode keeps its own budget. Must stay in sync with MODE_PIXEL_KEYS in the JS.
_PIXELS_MEMORY_KEYS: dict[str, str] = {
    "Max Side": "pixels_max",
    "Min Side": "pixels_min",
    "Total Pixels": "pixels_total",
}

# Default config — portraits selected by default, custom disabled.
_DEFAULT_CONFIG_JSON: str = json.dumps(
    {
        "ratios": _PORTRAIT_LABELS,
        "custom_ratio": 1.0,
        "custom_enabled": False,
        "pixels_max": DEFAULT_PIXELS,
        "pixels_min": DEFAULT_PIXELS,
        "pixels_total": DEFAULT_TOTAL_PIXELS,
    }
)


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


def _compute_dimensions_from_total_pixels(total_pixels: int, ratio: float) -> tuple[int, int]:
    """Compute width and height from a total pixel-area budget and aspect *ratio*.

    Solves ``w × h ≈ total_pixels`` with ``w / h = ratio``, i.e.
    ``w = sqrt(total × ratio)`` and ``h = sqrt(total / ratio)``.

    Args:
        total_pixels: Target pixel count for the whole image area.
        ratio: Width-to-height ratio (e.g. ``16/9 ≈ 1.778``). Non-positive
            ratios fall back to square.

    Returns:
        A ``(width, height)`` tuple, both rounded to 8 px and clamped to 64 px.
    """
    if ratio <= 0:
        ratio = 1.0

    w = math.sqrt(total_pixels * ratio)
    h = math.sqrt(total_pixels / ratio)

    width_int = max(round_to_multiple(int(round(w))), DEFAULT_MIN_DIMENSION)
    height_int = max(round_to_multiple(int(round(h))), DEFAULT_MIN_DIMENSION)
    return width_int, height_int


def _preset_gap() -> float:
    """Return the largest multiplicative gap between adjacent preset ratios.

    Presets are sorted by ratio and the ratio of each adjacent pair is taken; the
    largest is returned.  This is the scale used to step past the described range
    so the cutoff grows with the preset set instead of using a magic number.
    """
    ratios: list[float] = sorted(_ALL_RATIOS.values())
    gap_factors: list[float] = [b / a for a, b in zip(ratios, ratios[1:])]
    return max(gap_factors) if gap_factors else 1.0


def _custom_ratio_bounds() -> tuple[float, float]:
    """Return the ``(tall, wide)`` ratio range the named presets describe.

    The bounds sit one gap (see :func:`_preset_gap`) past the tallest and widest
    presets, so the "beyond the described keywords" cutoff feels clearly past the
    set's extremes in both directions.

    Returns:
        ``(tall, wide)`` where ``tall`` is the smallest ratio still considered
        described and ``wide`` is the largest.
    """
    ratios: list[float] = sorted(_ALL_RATIOS.values())
    margin: float = _preset_gap()
    return ratios[0] / margin, ratios[-1] * margin


def _format_ratio(ratio: float) -> str:
    """Format a width-to-height *ratio* as a compact ``W:H`` string.

    Uses a bounded-denominator fraction so entries such as ``2.0`` render as
    ``2:1`` and ``3.5`` as ``7:2`` while staying readable for awkward values.

    Args:
        ratio: Width-to-height ratio (must be positive).

    Returns:
        The ratio as ``"{numerator}:{denominator}"``.
    """
    frac: Fraction = Fraction(ratio).limit_denominator(100)
    return f"{frac.numerator}:{frac.denominator}"


def _custom_intensity(ratio: float, tall: float, wide: float, margin: float) -> str:
    """Return the composition phrase for a custom ratio beyond the described range.

    Escalates one gap (see :func:`_preset_gap`) per tier.  Portrait ratios (below
    *tall*) get three tiers — ``tall`` / ``very tall`` / ``super tall`` — while
    landscape ratios (above *wide*) get two: ``ultrawide`` / ``super ultrawide``.

    Args:
        ratio: Width-to-height ratio, already known to be outside ``[tall, wide]``.
        tall: Lower bound of the described range.
        wide: Upper bound of the described range.
        margin: Gap factor used to size each tier.

    Returns:
        A composition phrase such as ``"tall"`` or ``"super ultrawide"``.
    """
    if ratio < tall:
        if ratio >= tall / margin:
            return "tall"
        if ratio >= tall / (margin * margin):
            return "very tall"
        return "super tall"
    if ratio <= wide * margin:
        return "ultrawide"
    return "super ultrawide"


def _keywords_for_custom_ratio(ratio: float) -> str:
    """Return keywords for a custom *ratio*, or a generated custom phrase off-map.

    Inside the described range (see :func:`_custom_ratio_bounds`) the ratio reuses
    the nearest named preset's keywords by log-ratio distance.  Beyond the range it
    builds a subject-agnostic string::

        "{orientation} orientation, {W:H} aspect ratio, custom {intensity} composition"

    Args:
        ratio: Width-to-height ratio of the custom entry.

    Returns:
        The matched preset keyword string, or a generated ``custom ...`` phrase.
    """
    if ratio <= 0:
        return "custom composition"

    tall, wide = _custom_ratio_bounds()
    if tall <= ratio <= wide:
        nearest_name: str = min(_ALL_RATIOS, key=lambda n: abs(math.log(_ALL_RATIOS[n] / ratio)))
        return _KEYWORD_MAP[nearest_name]

    orientation: str = "portrait" if ratio < 1.0 else "landscape"
    intensity: str = _custom_intensity(ratio, tall, wide, _preset_gap())
    return f"{orientation} orientation, {_format_ratio(ratio)} aspect ratio, custom {intensity} composition"


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


class ResolutionSelector:
    """Calculates image dimensions with flexible constraint and multi-select aspect ratios.

    Choose whether the *Pixels* input constrains the **max** side (longest edge),
    the **min** side (shortest edge), or the **total** pixel area
    (width × height).  The frontend remembers the last *Pixels* value per mode
    and recalls it when switching modes.  Select any number of aspect ratio
    presets (portrait, landscape, square) plus an optional custom W:H ratio.
    One ratio is chosen at random from the active set on each execution.
    """

    DESCRIPTION = (
        "Calculates width and height from a pixel budget constrained to the max side, "
        "the min side, or the total pixel area, with multi-select aspect ratios and "
        "optional scaling."
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
                    ["Max Side", "Min Side", "Total Pixels"],
                    {
                        "tooltip": (
                            "What the Pixels value constrains: the longest side (Max), "
                            "the shortest side (Min), or the total image area (Total)."
                        )
                    },
                ),
                "Pixels": (
                    "INT",
                    {
                        "default": DEFAULT_PIXELS,
                        "min": MIN_PIXELS,
                        "max": MAX_TOTAL_PIXELS,
                        "step": 1,
                        "tooltip": (
                            "Pixel budget: side length for Max/Min Side modes, total "
                            "image area (e.g. 1000000 ≈ 1MP) for Total Pixels mode. "
                            "The last value per mode is remembered and recalled on switch."
                        ),
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

        if limit_by == "Total Pixels":
            pixels = clamp_dimension(pixels, MIN_TOTAL_PIXELS, MAX_TOTAL_PIXELS)
        else:
            pixels = clamp_dimension(pixels, MIN_PIXELS, MAX_PIXELS)
        scale_factor = max(MIN_SCALE_FACTOR, min(scale_factor, MAX_SCALE_FACTOR))

        rng: random.Random = random.Random(seed)
        active_ratios: list[tuple[str, float]] = self._resolve_active_ratios(config_json)

        target_label, ratio_float = rng.choice(sorted(active_ratios))

        if limit_by == "Min Side":
            width_int, height_int = _compute_dimensions_from_min_side(pixels, ratio_float)
        elif limit_by == "Total Pixels":
            width_int, height_int = _compute_dimensions_from_total_pixels(pixels, ratio_float)
        else:
            width_int, height_int = compute_aspect_ratio_dimensions(pixels, ratio_float)

        if target_label in _KEYWORD_MAP:
            keywords: str = _KEYWORD_MAP[target_label]
        else:
            keywords = _keywords_for_custom_ratio(ratio_float)

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
