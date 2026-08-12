"""Camera node for ComfyUI.

Provides :class:`Camera`, a director-style shot node that produces a fully
coherent camera description from three independent axes — shot size, camera
angle and view — plus camera movement, dutch tilt and render look (the
body or film stock whose rendering character the shot adopts).

Supports:
* Multi-select axis options via a JSON ``Camera Config`` widget driven by the
  ``js/camera.js`` frontend extension (per-axis checkboxes and shortcuts).
* Three selection modes: deterministic (seeded), full auto (seeded over the
  whole space) and random without repeats (a session-scoped shuffle bag).
* A read-only description widget updated live via the ``that_ai_god.stream``
  WebSocket extension and a standard ``control_after_generate`` seed widget.

The node emits the shot as a prose description (for prompt use), a keyword
list, a ``CAMERA`` object (for downstream Character/Scene nodes), a JSON twin
of the object and the visible body-region list.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from _camera_core import (
    _AXIS_DIRS,
    DEFAULT_CONFIG_JSON,
    NO_REPEAT_MODE,
    _builtin_space,
    build_shot,
    load_option_space,
    option_shortcuts,
)
from _utils import DEFAULT_MAX_DIMENSION, DEFAULT_MIN_DIMENSION, clamp_dimension

_NODE_DIR: str = os.path.dirname(os.path.realpath(__file__))
_WILDCARDS_DIR: str = os.path.join(_NODE_DIR, "wildcards")

# Frontend options endpoint: serves the effective option space (wildcard files
# when present, built-ins otherwise) so the UI chips always match the backend.
try:  # pragma: no cover - ComfyUI-only integration
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/that_aigod/camera_options")  # type: ignore[untyped-decorator]
    async def _camera_options_endpoint(_request: Any) -> Any:
        space = load_option_space(_WILDCARDS_DIR)
        if space is None:
            space = _builtin_space()
        payload: dict[str, Any] = {}
        for axis in _AXIS_DIRS:
            payload[axis] = {
                "options": list(space[axis]),
                "shortcuts": [
                    {"text": text, "members": members}
                    for text, members in option_shortcuts(space, axis)
                ],
            }
        return web.json_response(payload)

except Exception:  # noqa: BLE001, S110 - absent in pure-test environments
    pass


class Camera:
    """Composes a coherent camera shot and its description, keywords and regions."""

    DESCRIPTION = (
        "Director-style camera node: pick shot size, angle, view, movement, tilt and look — "
        "the node produces a coherent natural-language shot description, keywords, "
        "a CAMERA object, its JSON twin and the visible body regions."
    )

    RETURN_TYPES: tuple[str, ...] = ("STRING", "STRING", "CAMERA", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = (
        "Description",
        "Keywords",
        "Camera",
        "Camera JSON",
        "Visible Regions",
    )
    FUNCTION: str = "shoot"
    CATEGORY: str = "ThatAIGod/Character System"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Width": (
                    "INT",
                    {
                        "default": 1024,
                        "min": DEFAULT_MIN_DIMENSION,
                        "max": DEFAULT_MAX_DIMENSION,
                        "step": 8,
                        "tooltip": "Image width; wire from a resolution node (e.g. Dynamic Resolution Picker).",
                    },
                ),
                "Height": (
                    "INT",
                    {
                        "default": 1024,
                        "min": DEFAULT_MIN_DIMENSION,
                        "max": DEFAULT_MAX_DIMENSION,
                        "step": 8,
                        "tooltip": "Image height; wire from a resolution node (e.g. Dynamic Resolution Picker).",
                    },
                ),
                "Seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                        "tooltip": "Seed for shot selection. Same seed always produces the same shot.",
                    },
                ),
                "Wildcard Mode": (
                    ["Deterministic (Seed)", "Full Auto", "Random (No Repeat)"],
                    {
                        "default": "Deterministic (Seed)",
                        "tooltip": (
                            "Deterministic (Seed): seeded pick from the active sets. "
                            "Full Auto: seeded pick over the whole space. "
                            "Random (No Repeat): cycles through every active combination before repeating."
                        ),
                    },
                ),
                # Kept last on purpose: the frontend hides this widget, and the
                # combo above must not be preceded by hidden zero-height widgets.
                "Camera Config": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": DEFAULT_CONFIG_JSON,
                        "tooltip": (
                            "JSON config managed by the frontend. "
                            'Format: {"sizes": [...], "angles": [...], "views": [...], '
                            '"movements": [...], "tilts": [...], "looks": [...]}'
                        ),
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> Any:
        """Force re-execution for no-repeat farming; stay cached otherwise."""
        if kwargs.get("Wildcard Mode") == NO_REPEAT_MODE:
            return math.nan
        return (kwargs.get("Seed", 0), kwargs.get("Wildcard Mode", ""), kwargs.get("Camera Config", ""))

    def shoot(self, **kwargs: Any) -> dict[str, Any]:
        """Build the shot and return results for UI and downstream nodes.

        Args:
            **kwargs: ComfyUI widget values. Expected keys: ``"Camera Config"``,
                ``"Width"``, ``"Height"``, ``"Seed"``, ``"Wildcard Mode"``.

        Returns:
            A dict with ``"ui"`` values (consumed by ``js/camera.js``) and a
            5-tuple ``"result"`` matching the node's ``RETURN_TYPES``.
        """
        config_json: str = kwargs.get("Camera Config", DEFAULT_CONFIG_JSON)
        width: int = clamp_dimension(int(kwargs.get("Width", 1024)))
        height: int = clamp_dimension(int(kwargs.get("Height", 1024)))
        seed: int = int(kwargs.get("Seed", 0))
        mode: str = kwargs.get("Wildcard Mode", "Deterministic (Seed)")

        shot = build_shot(config_json, mode, seed, width, height, wildcards_dir=_WILDCARDS_DIR)

        regions_text = ", ".join(shot["regions"])
        shot_json = json.dumps(shot)

        info_string = (
            f"Shot: {shot['shot_size']} | {shot['angle']} | {shot['view']}\n"
            f"Movement: {shot['movement']} | Tilt: {shot['tilt']}\n"
            f"Look: {shot['look']}\n"
            f"Lens: {shot['lens']} | {shot['depth_of_field']}\n"
            f"Orientation: {shot['orientation']} ({width}x{height})\n"
            f"Regions: {regions_text}"
        )

        return {
            "ui": {
                "text": [info_string],
                "description": [shot["description"]],
                "keywords": [shot["keywords"]],
                "shot_summary": [f"{shot['shot_size']}, {shot['angle']}, {shot['view']}, {shot['movement']}"],
                "regions": [regions_text],
                "width": [width],
                "height": [height],
            },
            "result": (
                shot["description"],
                shot["keywords"],
                shot,
                shot_json,
                regions_text,
            ),
        }


NODE_CLASS_MAPPINGS = {
    "Camera": Camera,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Camera": "Camera",
}

__all__: list[str] = ["Camera", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
