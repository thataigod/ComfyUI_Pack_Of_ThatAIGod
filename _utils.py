"""Shared utility functions and constants for ComfyUI-Pack-Of-ThatAIGod.

This module is intentionally named ``_utils`` (underscore prefix) rather than
``utils`` to avoid shadowing ComfyUI's own ``utils`` package.  See DECISIONS.md D11.

Exports:
    get_logger: Return the shared ``ThatAIGod`` logger instance.
    clamp_dimension: Clamp an integer dimension to [min, max].
    round_to_multiple: Round an integer to the nearest multiple (banker's rounding).
    round_down_to_multiple: Round an integer down to the nearest multiple.
    compute_aspect_ratio_dimensions: Compute (width, height) from a max-side and ratio.
    safe_import: Import a module by name, returning None on ImportError.
"""

import importlib
import logging
from typing import Any

# Minimum pixel dimension used throughout the pack (e.g. placeholder images, clamping).
DEFAULT_MIN_DIMENSION: int = 64
# Maximum pixel dimension — matches the practical upper limit of ComfyUI workflows.
DEFAULT_MAX_DIMENSION: int = 16384
# ComfyUI requires image dimensions to be multiples of 8 for most model architectures.
DEFAULT_MULTIPLE: int = 8


def get_logger() -> logging.Logger:
    """Return the shared ThatAIGod logger.

    All nodes in the pack use a single named logger so that log output can be
    filtered or captured by name in tests.
    """
    return logging.getLogger("ThatAIGod")


def clamp_dimension(value: int, min_val: int = DEFAULT_MIN_DIMENSION, max_val: int = DEFAULT_MAX_DIMENSION) -> int:
    """Clamp a dimension value between *min_val* and *max_val* (inclusive).

    Args:
        value: The integer to clamp.
        min_val: Lower bound (default: :data:`DEFAULT_MIN_DIMENSION`).
        max_val: Upper bound (default: :data:`DEFAULT_MAX_DIMENSION`).

    Returns:
        The clamped value.
    """
    return max(min_val, min(value, max_val))


def round_to_multiple(value: int, multiple: int = DEFAULT_MULTIPLE) -> int:
    """Round *value* to the nearest *multiple* using banker's rounding (round-half-to-even).

    Args:
        value: The integer to round.
        multiple: The rounding granularity (default: :data:`DEFAULT_MULTIPLE` = 8).

    Returns:
        The rounded value.
    """
    return int(round(value / multiple) * multiple)


def round_down_to_multiple(value: int, multiple: int = DEFAULT_MULTIPLE) -> int:
    """Round *value* down to the nearest *multiple* (floor division).

    Args:
        value: The integer to round down.
        multiple: The rounding granularity (default: :data:`DEFAULT_MULTIPLE` = 8).

    Returns:
        The largest multiple of *multiple* that is ≤ *value*.
    """
    return (value // multiple) * multiple


def compute_aspect_ratio_dimensions(max_side: int, ratio: float) -> tuple[int, int]:
    """Compute width and height from a max-side length and a width-to-height ratio.

    The longer side is set to *max_side*; the shorter side is derived from
    *ratio*.  Both dimensions are rounded to the nearest :data:`DEFAULT_MULTIPLE`
    (8 px) using banker's rounding and clamped to at least
    :data:`DEFAULT_MIN_DIMENSION`.

    Args:
        max_side: The target pixel count for the longest side.
        ratio: Width-to-height ratio (e.g. ``16/9`` for landscape, ``2/3`` for portrait).
            A ratio of exactly ``1.0`` produces a square image.

    Returns:
        A ``(width, height)`` tuple rounded to :data:`DEFAULT_MULTIPLE` and clamped
        to a minimum of :data:`DEFAULT_MIN_DIMENSION`.
    """
    if ratio > 1.0:
        w = float(max_side)
        h = max_side / ratio
    elif ratio < 1.0:
        h = float(max_side)
        w = max_side * ratio
    else:
        w = float(max_side)
        h = float(max_side)

    width_int = max(round_to_multiple(int(round(w))), DEFAULT_MIN_DIMENSION)
    height_int = max(round_to_multiple(int(round(h))), DEFAULT_MIN_DIMENSION)
    return width_int, height_int


def safe_import(module_name: str) -> Any | None:
    """Import *module_name* by name, returning ``None`` on any failure.

    On failure a WARNING is logged via :func:`get_logger` so that the caller
    can continue loading other modules without crashing.

    Args:
        module_name: Fully-qualified module name (e.g. ``"LLM_Node"``).

    Returns:
        The imported module object, or ``None`` if the import failed.
    """
    try:
        return importlib.import_module(module_name)
    except Exception as e:
        logger = get_logger()
        logger.warning(
            "ComfyUI-Pack-Of-ThatAIGod: failed to import %s: %s",
            module_name,
            e,
        )
        return None


__all__: list[str] = [
    "get_logger",
    "clamp_dimension",
    "round_to_multiple",
    "round_down_to_multiple",
    "compute_aspect_ratio_dimensions",
    "safe_import",
]
