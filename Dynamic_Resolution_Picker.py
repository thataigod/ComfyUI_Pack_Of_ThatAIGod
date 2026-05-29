import torch
import math
import random
from typing import Any


class DynamicResolution:
    RETURN_TYPES: tuple[str, ...] = ("INT", "INT", "INT", "INT", "FLOAT", "STRING", "INT", "INT")
    RETURN_NAMES: tuple[str, ...] = ("Width", "Height", "Scaled Width", "Scaled Height", "Scale Factor", "Keywords", "Guide Size", "Max Size")
    FUNCTION: str = "calculate"
    CATEGORY: str = "ThatAIGod/Image Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        ratio_options: list[str] = [
            "Random (Any)",
            "Random (Portrait)",
            "Random (Landscape)",
            "Square 1:1",
            "Portrait 2:3 (Classic)",
            "Portrait 3:4 (Standard)",
            "Portrait 4:5 (Social)",
            "Portrait 9:16 (Mobile)",
            "Landscape 3:2 (Classic)",
            "Landscape 4:3 (Standard)",
            "Landscape 5:4 (Display)",
            "Landscape 16:9 (HD)",
            "Landscape 16:10 (Monitor)",
            "Landscape 21:9 (Ultrawide)",
            "Landscape 1.85:1 (Cinema)"
        ]

        return {
            "required": {
                "Max Side Pixels": ("INT", {"default": 1024, "min": 256, "max": 16384, "step": 8}),
                "Aspect Ratio": (ratio_options, {"default": "Square 1:1"}),
                "Scale Factor": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 8.0, "step": 0.05}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
        }

    def calculate(self, **kwargs: Any) -> dict[str, Any]:
        max_side: int = kwargs.get("Max Side Pixels", 1024)
        aspect_ratio_label: str = kwargs.get("Aspect Ratio", "Square 1:1")
        scale_factor: float = kwargs.get("Scale Factor", 1.5)
        seed: int = kwargs.get("seed", 0)

        rng: random.Random = random.Random(seed)

        portraits: dict[str, float] = {
            "Portrait 2:3 (Classic)": 2/3,
            "Portrait 3:4 (Standard)": 3/4,
            "Portrait 4:5 (Social)": 4/5,
            "Portrait 9:16 (Mobile)": 9/16
        }
        landscapes: dict[str, float] = {
            "Landscape 3:2 (Classic)": 3/2,
            "Landscape 4:3 (Standard)": 4/3,
            "Landscape 5:4 (Display)": 5/4,
            "Landscape 16:9 (HD)": 16/9,
            "Landscape 16:10 (Monitor)": 16/10,
            "Landscape 21:9 (Ultrawide)": 21/9,
            "Landscape 1.85:1 (Cinema)": 1.85
        }
        square: dict[str, float] = {"Square 1:1": 1.0}

        keyword_map: dict[str, str] = {
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
            "Landscape 1.85:1 (Cinema)": "Landscape, 1.85:1 Aspect Ratio, Theatrical Format"
        }

        target_label: str = aspect_ratio_label
        ratio_float: float = 1.0

        if "Random" in aspect_ratio_label:
            if aspect_ratio_label == "Random (Portrait)":
                target_label, ratio_float = rng.choice(sorted(list(portraits.items())))
            elif aspect_ratio_label == "Random (Landscape)":
                target_label, ratio_float = rng.choice(sorted(list(landscapes.items())))
            else:
                all_ratios: dict[str, float] = {**portraits, **landscapes, **square}
                target_label, ratio_float = rng.choice(sorted(list(all_ratios.items())))
        else:
            all_known: dict[str, float] = {**portraits, **landscapes, **square}
            if target_label in all_known:
                ratio_float = all_known[target_label]
            else:
                ratio_float = 1.0
                target_label = "Square 1:1"

        keywords: str = keyword_map.get(target_label, f"{target_label}, Aspect Ratio")

        if ratio_float > 1.0:
            width = max_side
            height = max_side / ratio_float
        elif ratio_float < 1.0:
            height = max_side
            width = max_side * ratio_float
        else:
            width = max_side
            height = max_side

        width_int: int = max(int(round(width / 8) * 8), 64)
        height_int: int = max(int(round(height / 8) * 8), 64)

        guide_size: int = min(width_int, height_int)
        max_size_val: int = max(width_int, height_int)

        s_width: float = width_int * scale_factor
        s_height: float = height_int * scale_factor
        scaled_width: int = int(round(s_width / 8) * 8)
        scaled_height: int = int(round(s_height / 8) * 8)

        actual_mp: float = (width_int * height_int) / 1000000

        info_string: str = (
            f"Mode:   {target_label}\n"
            f"Base:   {width_int}x{height_int} ({actual_mp:.2f} MP)\n"
            f"Scaled: {scaled_width}x{scaled_height} (x{scale_factor})\n"
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
                "max_size": [max_size_val]
            },
            "result": (width_int, height_int, scaled_width, scaled_height, scale_factor, keywords, guide_size, max_size_val)
        }

NODE_CLASS_MAPPINGS = {
    "DynamicResolution": DynamicResolution
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DynamicResolution": "Dynamic Resolution Picker"
}