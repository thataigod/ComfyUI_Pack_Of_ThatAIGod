import logging
from typing import Any


def get_logger() -> logging.Logger:
    return logging.getLogger("ThatAIGod")


def clamp_dimension(value: int, min_val: int = 64, max_val: int = 16384) -> int:
    return max(min_val, min(value, max_val))


def round_to_multiple(value: int, multiple: int = 8) -> int:
    return int(round(value / multiple) * multiple)


def round_down_to_multiple(value: int, multiple: int = 8) -> int:
    return (value // multiple) * multiple


def compute_aspect_ratio_dimensions(
    max_side: int, ratio: float
) -> tuple[int, int]:
    if ratio > 1.0:
        w = float(max_side)
        h = max_side / ratio
    elif ratio < 1.0:
        h = float(max_side)
        w = max_side * ratio
    else:
        w = float(max_side)
        h = float(max_side)

    width_int = max(round_to_multiple(int(round(w))), 64)
    height_int = max(round_to_multiple(int(round(h))), 64)
    return width_int, height_int


def safe_import(module_name: str) -> Any | None:
    try:
        return __import__(
            f".{module_name}",
            globals(),
            locals(),
            ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"],
            level=1,
        )
    except ImportError as e:
        logger = get_logger()
        logger.warning(
            "ComfyUI-Pack-Of-ThatAIGod: failed to import %s: %s",
            module_name,
            e,
        )
        return None
