"""Character node for ComfyUI.

Provides :class:`Character`, the persona-driven character node of the
director-style pipeline.  It consumes the CAMERA object produced by the
Camera node, strips the persona description down to the visible body
regions, poses the character, dresses it for the occasion and emits a
coherent CHARACTER object.

Supports:
* Persona selection from a dropdown populated at startup with ``female``,
  ``male`` and every custom persona folder under ``wildcards/characters/``.
* Camera-driven stripping: only attribute files whose region is visible are
  resolved (profile views substitute ``profile.txt`` for ``face.txt``).
* Per-persona wardrobes (``wildcards/characters/<persona>/wardrobe/``) with
  optional access to the common wardrobe (``wildcards/wardrobe/<gender>/``,
  gender read from the persona's ``gender.txt``), occasion-filtered via
  ``#@occasion`` directives, garment slots filled only for visible regions.
* Two selection modes: deterministic (seeded) and random without repeats
  (session-scoped per-file decks).

The node emits the CHARACTER object (for downstream Scene nodes), its JSON
twin, a natural-language Description and a comma-separated Keywords list.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from _character_core import _STATE_VALUES, build_character

_NODE_DIR: str = os.path.dirname(os.path.realpath(__file__))
_WILDCARDS_DIR: str = os.path.join(_NODE_DIR, "wildcards")

_DETERMINISTIC_MODE: str = "Deterministic (Seed)"
_NO_REPEAT_MODE: str = "Random (No Repeat)"
_MODE_OPTIONS: list[str] = [_DETERMINISTIC_MODE, _NO_REPEAT_MODE]

_ALL_OCCASIONS: str = "All (unrestricted)"
_DEFAULT_OCCASION: str = "casual"

# Guaranteed persona options; custom folders are appended in sorted order.
_BASE_PERSONAS: list[str] = ["female", "male"]

# Shortcut groups for the occasion chips (frontend button row).
_OCCASION_GROUPS: dict[str, list[str]] = {
    "Everyday": ["casual", "travel", "home"],
    "Work": ["office", "formal"],
    "Social": ["party", "wedding", "festival"],
    "Active": ["athletic", "gym", "beach", "pool", "resort"],
    "Private": ["intimate", "boudoir"],
    "Cultural": ["traditional", "costume"],
}

# Frontend options endpoint: serves the occasion and state spaces so the UI
# chips always match the backend.
try:  # pragma: no cover - ComfyUI-only integration
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/that_aigod/character_options")  # type: ignore[untyped-decorator]
    async def _character_options_endpoint(_request: Any) -> Any:
        occasions = [value for value in _occasion_options() if value != _ALL_OCCASIONS]
        return web.json_response(
            {
                "occasions": occasions,
                "states": list(_STATE_VALUES),
                "occasion_groups": [
                    {"text": text, "members": members}
                    for text, members in _OCCASION_GROUPS.items()
                ],
            }
        )

except Exception:  # noqa: BLE001, S110 - absent in pure-test environments
    pass


def _persona_options() -> list[str]:
    """Return the persona dropdown options (guaranteed base + scanned folders).

    Scans ``wildcards/characters/`` for persona folders at startup (mirroring
    the Wildcard Reader node's dropdown pattern); new folders appear after a
    ComfyUI restart.

    Returns:
        A list of persona folder names.
    """
    options: list[str] = []
    characters_dir = os.path.join(_WILDCARDS_DIR, "characters")
    if os.path.isdir(characters_dir):
        options = sorted(
            name
            for name in os.listdir(characters_dir)
            if os.path.isdir(os.path.join(characters_dir, name)) and not name.startswith(".")
        )
    return _BASE_PERSONAS + [name for name in options if name not in _BASE_PERSONAS]


def _occasion_options() -> list[str]:
    """Return the occasion dropdown options from ``wildcards/shared/occasions.txt``.

    The list is read at startup; lines starting with ``#`` and blank lines are
    ignored.  Always includes the unrestricted entry first.

    Returns:
        A list of occasion values (with the unrestricted entry).
    """
    options: list[str] = [_ALL_OCCASIONS]
    path = os.path.join(_WILDCARDS_DIR, "shared", "occasions.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                value = line.strip().lower()
                if value and not value.startswith("#") and value not in options:
                    options.append(value)
    except OSError:
        pass
    if _DEFAULT_OCCASION not in options:
        options.append(_DEFAULT_OCCASION)
    return options


def _default_character_config() -> str:
    """Return the default Character Config JSON (all occasions, all states)."""
    occasions = [value for value in _occasion_options() if value != _ALL_OCCASIONS]
    return json.dumps({"occasions": occasions, "states": list(_STATE_VALUES)})


def _parse_character_config(config_json: str) -> tuple[list[str] | None, list[str] | None]:
    """Parse the Character Config JSON into occasion and state selections.

    Args:
        config_json: JSON with optional ``occasions`` and ``states`` lists.

    Returns:
        ``(occasions, states)``; a ``None`` entry means the key was absent
        (treated as "all selected"), an empty list means "nothing selected".
    """
    try:
        raw: Any = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    def pick(key: str) -> list[str] | None:
        value = raw.get(key)
        if not isinstance(value, list):
            return None
        return [str(item).strip().lower() for item in value if isinstance(item, str) and item.strip()]

    return pick("occasions"), pick("states")


class Character:
    """Builds a frame-consistent character description from a persona and CAMERA object."""

    DESCRIPTION = (
        "Persona-driven character node: pick a persona and wire the CAMERA object from the "
        "Camera node — the node describes only the visible body regions, poses the character, "
        "dresses it for the occasion (persona or common wardrobe) and emits a CHARACTER object, "
        "its JSON twin, a natural-language Description and Keywords."
    )

    RETURN_TYPES: tuple[str, ...] = ("CHARACTER", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = (
        "Character",
        "Character JSON",
        "Description",
        "Keywords",
        "Occasion",
        "Trigger",
    )
    FUNCTION: str = "build"
    CATEGORY: str = "ThatAIGod/Character System"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Persona": (
                    _persona_options(),
                    {
                        "default": "female",
                        "tooltip": (
                            "Persona folder under wildcards/characters/. 'female' and 'male' are "
                            "always available; custom personas appear after a restart."
                        ),
                    },
                ),
                "Camera": (
                    "CAMERA",
                    {
                        "tooltip": (
                            "The CAMERA object from the Camera node. Its visible regions drive which body parts are described."
                        ),
                    },
                ),
                "Use Common Wardrobe": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Allow access to the default wardrobe of the matching default persona "
                            "(characters/<gender>/wardrobe) when the persona has no wardrobe of its "
                            "own or lacks an occasion-eligible category. "
                            "Off = the persona may only use its own wardrobe."
                        ),
                    },
                ),
                "Use Shared Garment Modifiers": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Append fabric/style phrases from wildcards/shared/garment-style.txt "
                            "to persona wardrobe pieces that carry no inline wildcard tags."
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
                        "tooltip": "Seed for character selection. Same seed always produces the same character.",
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
                # Kept last on purpose: the frontend hides this widget (the
                # chips replace it), mirroring the Camera node's config.
                "Character Config": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": _default_character_config(),
                        "tooltip": (
                            "JSON config managed by the frontend. "
                            'Format: {"occasions": [...], "states": [...]}'
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
        camera = kwargs.get("Camera")
        camera_regions = tuple(camera.get("regions", [])) if isinstance(camera, dict) else None
        camera_view = camera.get("view") if isinstance(camera, dict) else None
        return (
            int(kwargs.get("Seed", 0)),
            str(kwargs.get("Persona", "female")),
            str(kwargs.get("Character Config", "")),
            str(kwargs.get("Occasion", "")),
            bool(kwargs.get("Use Common Wardrobe", False)),
            bool(kwargs.get("Use Shared Garment Modifiers", True)),
            camera_regions,
            camera_view,
        )

    def build(self, **kwargs: Any) -> dict[str, Any]:
        """Build the CHARACTER object and return results for UI and downstream nodes.

        Args:
            **kwargs: ComfyUI widget/input values. Expected keys: ``"Persona"``,
                ``"Camera"``, ``"Character Config"`` (or the legacy
                ``"Occasion"`` dropdown value), ``"Use Common Wardrobe"``,
                ``"Use Shared Garment Modifiers"``, ``"Seed"``,
                ``"Wildcard Mode"``.

        Returns:
            A dict with a 6-tuple ``"result"`` matching the node's
            ``RETURN_TYPES`` (Character object, JSON, Description, Keywords,
            Occasion, Trigger).
        """
        persona: str = str(kwargs.get("Persona", "female"))
        camera: Any = kwargs.get("Camera")
        use_common_wardrobe = bool(kwargs.get("Use Common Wardrobe", False))
        use_shared_modifiers = bool(kwargs.get("Use Shared Garment Modifiers", True))
        seed: int = int(kwargs.get("Seed", 0))
        mode: str = str(kwargs.get("Wildcard Mode", _DETERMINISTIC_MODE))

        occasion = ""
        occasion_options: list[str] | None = None
        state = ""
        state_options: list[str] | None = None

        config_json = kwargs.get("Character Config")
        if config_json is not None:
            occasions, states = _parse_character_config(str(config_json))
            if occasions is None:
                occasion_options = [value for value in _occasion_options() if value != _ALL_OCCASIONS]
            elif len(occasions) == 1:
                occasion = occasions[0]
            elif occasions:
                occasion_options = occasions
            # empty occasions = truly unrestricted (no roll, no filtering)
            if states is not None and len(states) == 1:
                state = states[0]
            elif states is not None and 1 < len(states) < len(_STATE_VALUES):
                state_options = states
            # absent/full/empty states = Auto (weighted roll)
        else:
            occasion_raw = str(kwargs.get("Occasion", _ALL_OCCASIONS))
            unrestricted = occasion_raw == _ALL_OCCASIONS
            occasion = "" if unrestricted else occasion_raw.strip().lower()
            if unrestricted:
                occasion_options = [value for value in _occasion_options() if value != _ALL_OCCASIONS]

        character = build_character(
            _WILDCARDS_DIR,
            persona,
            camera if isinstance(camera, dict) else None,
            occasion,
            use_common_wardrobe,
            use_shared_modifiers,
            mode,
            seed,
            occasion_options=occasion_options,
            state=state,
            state_options=state_options,
        )

        character_json = json.dumps(character)

        rolled = occasion == "" and character["occasion"] != ""
        info_string = (
            f"Persona: {character['persona']}\n"
            f"State: {character['state']}\n"
            f"Regions: {', '.join(character['regions'])}\n"
            f"Outfit: {character['outfit_category'] or '(none)'}\n"
            f"Occasion: {character['occasion'] or '(unrestricted)'}{' (random)' if rolled else ''}\n"
            f"Mode: {mode}"
        )
        if character["trigger"]:
            info_string += f"\nTrigger: {character['trigger']}"

        return {
            "ui": {
                "text": [info_string],
                "description": [character["description"]],
                "keywords": [character["keywords"]],
            },
            "result": (
                character,
                character_json,
                character["description"],
                character["keywords"],
                character["occasion"],
                character["trigger"],
            ),
        }


NODE_CLASS_MAPPINGS = {
    "Character": Character,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Character": "Character",
}

__all__: list[str] = [
    "Character",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "_persona_options",
    "_occasion_options",
]
