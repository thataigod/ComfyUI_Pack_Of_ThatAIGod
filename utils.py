import importlib
import logging
from typing import Any

DEFAULT_MIN_DIMENSION: int = 64
DEFAULT_MAX_DIMENSION: int = 16384
DEFAULT_MULTIPLE: int = 8


def get_logger() -> logging.Logger:
    """Return the shared ThatAIGod logger."""
    return logging.getLogger("ThatAIGod")


def clamp_dimension(value: int, min_val: int = DEFAULT_MIN_DIMENSION, max_val: int = DEFAULT_MAX_DIMENSION) -> int:
    """Clamp a dimension value between min and max bounds."""
    return max(min_val, min(value, max_val))


def round_to_multiple(value: int, multiple: int = DEFAULT_MULTIPLE) -> int:
    """Round a value to the nearest multiple using bankers' rounding."""
    return int(round(value / multiple) * multiple)


def round_down_to_multiple(value: int, multiple: int = DEFAULT_MULTIPLE) -> int:
    """Round a value down to the nearest multiple."""
    return (value // multiple) * multiple


def compute_aspect_ratio_dimensions(
    max_side: int, ratio: float
) -> tuple[int, int]:
    """Compute width and height from a max side length and aspect ratio.

    Args:
        max_side: The target pixel count for the longest side.
        ratio: Width-to-height ratio (e.g. 16/9, 2/3).

    Returns:
        A (width, height) tuple rounded to DEFAULT_MULTIPLE and clamped to minimum.
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
    """Import a module by name, returning None on ImportError instead of raising."""
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        logger = get_logger()
        logger.warning(
            "ComfyUI-Pack-Of-ThatAIGod: failed to import %s: %s",
            module_name,
            e,
        )
        return None
