"""Scene node for ComfyUI.

Provides :class:`Scene`, the location/time/film composer of the director-
style pipeline.  Unlike v1 it no longer combines components: the character
and camera prose are emitted by their own nodes and reordered downstream, so
this node emits only its own prose.

Coherence:
* Locations (``wildcards/scenes/``) are filtered by ``#@occasion``,
  ``#@outfit`` and ``#@time`` directives; an optional wired CHARACTER object
  also adds its ``outfit_category`` and its state.
* Scene files are stacked directive blocks (``#@time`` + ``#@setting`` per
  block, like ``shared/time-of-day.txt``); each block owns fixtures,
  furniture and mood only, so the location never contradicts the time phrase.
* State-aware gating: a non-dressed character state (``nude``, ``slipping``,
  ``revealing``, ``mishap``) limits eligible locations to scenes that declare
  the state (``#@state:``) plus universal scenes such as the studio.  Public
  scenes can never host a non-dressed character.
* ``Time of Day`` picks from ``wildcards/shared/time-of-day.txt``; an
  explicit value both filters locations and selects the matching phrase.
* An explicit ``Location`` override skips filtering entirely.

The node emits the SCENE object (for downstream nodes), its JSON twin, the
Description (location + time + film prose) and a Keywords list.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from _scene_core import (
    AUTO_LOCATION,
    AUTO_OCCASION,
    DEFAULT_LOCATION,
    DEFAULT_TIME,
    _resolve_occasion,
    _scene_options,
    _time_options,
    build_scene,
)
from Character import _occasion_options

_NODE_DIR: str = os.path.dirname(os.path.realpath(__file__))
_WILDCARDS_DIR: str = os.path.join(_NODE_DIR, "wildcards")

_DETERMINISTIC_MODE: str = "Deterministic (Seed)"
_NO_REPEAT_MODE: str = "Random (No Repeat)"
_MODE_OPTIONS: list[str] = [_DETERMINISTIC_MODE, _NO_REPEAT_MODE]


class Scene:
    """Composes the scene description from location, time and film look."""

    DESCRIPTION = (
        "Scene node: pick an occasion, location and time of day — the node resolves a "
        "directive-coherent location and emits the location/time/film prose only "
        "(the character and camera prose live on their own nodes). Non-dressed "
        "character states gate the location space to private scenes."
    )

    RETURN_TYPES: tuple[str, ...] = ("SCENE", "STRING", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = (
        "Scene",
        "Scene JSON",
        "Description",
        "Keywords",
    )
    FUNCTION: str = "compose"
    CATEGORY: str = "ThatAIGod/Character System"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Occasion": (
                    "STRING",
                    {
                        "default": AUTO_OCCASION,
                        "tooltip": (
                            "One occasion drives the whole frame. 'auto' uses the wired CHARACTER "
                            "object's occasion (set it in the Character node) or, without one, a "
                            "seeded random pick. Empty or 'All (unrestricted)' disables filtering; "
                            "any other value (e.g. 'travel') is used as-is. Wire the Character "
                            "node's 'Occasion' output for a value that always matches the wardrobe."
                        ),
                    },
                ),
                "Location": (
                    [AUTO_LOCATION] + _scene_options(_WILDCARDS_DIR),
                    {
                        "default": DEFAULT_LOCATION,
                        "tooltip": (
                            "Auto: directive-filtered pick from wildcards/scenes/. "
                            "An explicit scene overrides filtering entirely."
                        ),
                    },
                ),
                "Time of Day": (
                    _time_options(_WILDCARDS_DIR),
                    {
                        "default": DEFAULT_TIME,
                        "tooltip": (
                            "Filters locations by #@time directives and selects the matching "
                            "phrase from wildcards/shared/time-of-day.txt. 'All' picks any phrase."
                        ),
                    },
                ),
                "Use Film Look": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Layer a film-stock phrase from the wildcards/styles/film-look.txt "
                            "deck (Kodachrome, Portra, pushed film...). The deck spans the "
                            "commercial, Soviet, DDR, tonality, era, digital, analog and quality "
                            "family files under wildcards/styles/film-look/."
                        ),
                    },
                ),
                "Seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                        "tooltip": "Seed for scene selection. Same seed always produces the same scene.",
                    },
                ),
                "Wildcard Mode": (
                    _MODE_OPTIONS,
                    {
                        "default": _DETERMINISTIC_MODE,
                        "tooltip": (
                            "Deterministic (Seed): seeded picks, reproducible. "
                            "Random (No Repeat): cycles through every active option before repeating."
                        ),
                    },
                ),
            },
            "optional": {
                "Character": (
                    "CHARACTER",
                    {
                        "tooltip": (
                            "The CHARACTER object from the Character node. Adds its outfit category "
                            "and state to the filter context: a lingerie outfit never lands on a "
                            "beach, and a non-dressed state (nude, slipping, revealing, mishap) "
                            "restricts locations to private scenes that declare it."
                        ),
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> Any:
        """Force re-execution for no-repeat farming; stay cached otherwise."""
        if kwargs.get("Wildcard Mode") == _NO_REPEAT_MODE:
            return math.nan
        character = kwargs.get("Character")
        return (
            int(kwargs.get("Seed", 0)),
            str(kwargs.get("Occasion", AUTO_OCCASION)),
            str(character.get("occasion", "") or "") if isinstance(character, dict) else "",
            str(kwargs.get("Location", DEFAULT_LOCATION)),
            str(kwargs.get("Time of Day", DEFAULT_TIME)),
            bool(kwargs.get("Use Film Look", True)),
            str(character.get("outfit_category", "") or "") if isinstance(character, dict) else "",
            str(character.get("state", "") or "") if isinstance(character, dict) else "",
        )

    def compose(self, **kwargs: Any) -> dict[str, Any]:
        """Build the SCENE object and return results for UI and downstream nodes.

        Args:
            **kwargs: ComfyUI widget/input values. Expected keys: ``"Occasion"``,
                ``"Location"``, ``"Time of Day"``, ``"Use Film Look"``,
                ``"Seed"``, ``"Wildcard Mode"``, ``"Character"``.

        Returns:
            A dict with a 4-tuple ``"result"`` matching the node's
            ``RETURN_TYPES`` (Scene object, JSON, Description, Keywords).
        """
        occasion_raw: str = str(kwargs.get("Occasion", AUTO_OCCASION))
        seed: int = int(kwargs.get("Seed", 0))
        occasion_options: list[str] = _occasion_options()
        character: Any = kwargs.get("Character")
        occasion, occasion_source = _resolve_occasion(occasion_raw, character, occasion_options, seed)
        location: str = str(kwargs.get("Location", DEFAULT_LOCATION))
        time: str = str(kwargs.get("Time of Day", DEFAULT_TIME))
        use_film = bool(kwargs.get("Use Film Look", True))
        mode: str = str(kwargs.get("Wildcard Mode", _DETERMINISTIC_MODE))

        scene = build_scene(
            _WILDCARDS_DIR,
            character if isinstance(character, dict) else None,
            occasion,
            occasion_source,
            location,
            time,
            use_film,
            mode,
            seed,
        )

        scene_json = json.dumps(scene)

        if occasion_source == "character":
            occasion_label = f"{scene['occasion'] or 'unrestricted'} (from Character)"
        elif occasion_source == "random":
            occasion_label = f"{scene['occasion']} (random)"
        elif occasion_source == "unrestricted":
            occasion_label = "unrestricted"
        else:
            occasion_label = scene["occasion"]

        info_string = (
            f"Occasion: {occasion_label}\n"
            f"Location: {scene['location_key'] or '(none)'}\n"
            f"Time: {scene['time_of_day'] or '(none)'}\n"
            f"Film Look: {scene['film_look'] or '(off)'}\n"
            f"State: {scene['state'] or '(none)'}\n"
            f"Mode: {mode}"
        )

        return {
            "ui": {
                "text": [info_string],
                "description": [scene["description"]],
                "keywords": [scene["keywords"]],
            },
            "result": (
                scene,
                scene_json,
                scene["description"],
                scene["keywords"],
            ),
        }


NODE_CLASS_MAPPINGS = {
    "Scene": Scene,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Scene": "Scene",
}

__all__: list[str] = [
    "Scene",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "_scene_options",
    "_time_options",
]
