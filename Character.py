"""Character node for ComfyUI (v2 — lewdity-band era).

Provides :class:`Character`, the persona-driven character node of the
director-style pipeline.  It consumes the CAMERA object produced by the
Camera node, strips the persona description down to the visible body
regions, poses the character, dresses it for a randomly rolled occasion
from a wardrobe source chosen on the node (the shared common wardrobe
gated by the persona's lewdity band, the persona's own curated wardrobe,
or everything), rolls minimal extras, resolves a matching background, and
emits a coherent CHARACTER object plus the background as its own string.

Supports:
* Persona selection from a dropdown populated at startup with ``female``,
  ``male`` and every custom persona folder under ``wildcards/characters/``.
* Camera-driven stripping: only attribute files whose region is visible are
  resolved (profile views substitute ``profile.txt`` for ``face.txt``).
* Wardrobe Source modes: Use External Wardrobe (default, band-gated common
  wardrobe with the persona's own clothes as fallback), Use Internal
  Wardrobe (persona clothes only), Use Complete Wardrobe (lewdity ignored).
* Lewdity min/max overrides (``-1`` = use the persona's ``lewdity.txt``).
* Optional Time of Day / Domain filters for the background, their values
  scanned from the location taxonomy's ``#@time:``/``#@domain:`` headers.
* Two selection modes: deterministic (seeded) and random without repeats.

The node emits the CHARACTER object (for downstream nodes), its JSON twin,
a natural-language Description, Keywords, the Background as its own string,
the rolled Occasion and the persona Trigger.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from _character_core import WARDROBE_COMPLETE, WARDROBE_EXTERNAL, WARDROBE_INTERNAL, WARDROBE_MODES, build_character

_NODE_DIR: str = os.path.dirname(os.path.realpath(__file__))
_WILDCARDS_DIR: str = os.path.join(_NODE_DIR, "wildcards")

_DETERMINISTIC_MODE: str = "Deterministic (Seed)"
_NO_REPEAT_MODE: str = "Random (No Repeat)"
_MODE_OPTIONS: list[str] = [_DETERMINISTIC_MODE, _NO_REPEAT_MODE]

_ALL_OCCASIONS: str = "All (unrestricted)"
_ANY_FILTER: str = "Any (unrestricted)"
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


def _persona_options() -> list[str]:
    """Return the persona dropdown options (guaranteed base + scanned folders)."""
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
    """Return the occasion dropdown options from ``wildcards/shared/occasions.txt``."""
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


def _scan_location_directive(key: str) -> list[str]:
    """Scan the location taxonomy for the distinct ``#@<key>:`` header values.

    The Time of Day and Domain dropdowns take their values from the data
    itself (``#@time:``/``#@domain:`` headers across ``wildcards/locations/``)
    so the widgets never drift from the authored vocabulary.
    """
    values: set[str] = set()
    locations_dir = os.path.join(_WILDCARDS_DIR, "locations")
    prefix = f"#@{key}:"
    try:
        names = sorted(name for name in os.listdir(locations_dir) if name.endswith(".txt"))
    except OSError:
        return []
    for name in names:
        try:
            with open(os.path.join(locations_dir, name), encoding="utf-8-sig") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith(prefix):
                        for value in stripped[len(prefix) :].split(","):
                            cleaned = value.strip().lower()
                            if cleaned:
                                values.add(cleaned)
        except OSError:  # pragma: no cover - unreadable file mid-scan
            continue
    return sorted(values)


def _time_options() -> list[str]:
    """Return the Time of Day dropdown options scanned from the location files."""
    return [_ANY_FILTER, *_scan_location_directive("time")]


def _domain_options() -> list[str]:
    """Return the Domain dropdown options scanned from the location files."""
    return [_ANY_FILTER, *_scan_location_directive("domain")]


def _default_character_config() -> str:
    """Return the default Character Config JSON (all occasions selected)."""
    occasions = [value for value in _occasion_options() if value != _ALL_OCCASIONS]
    return json.dumps({"occasions": occasions})


def _parse_character_config(config_json: str) -> list[str] | None:
    """Parse the Character Config JSON into an occasion selection.

    Returns ``None`` when the ``occasions`` key is absent (treated as "all
    selected"); an empty list means "truly unrestricted" (no roll, no
    filtering).
    """
    try:
        raw: Any = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("occasions")
    if not isinstance(value, list):
        return None
    return [str(item).strip().lower() for item in value if isinstance(item, str) and item.strip()]


class Character:
    """Builds a frame-consistent character description from a persona and CAMERA object."""

    DESCRIPTION = (
        "Persona-driven character node: pick a persona and wire the CAMERA object from the "
        "Camera node — the node describes only the visible body regions, poses the character, "
        "dresses it for a rolled occasion from the chosen wardrobe source (lewdity-band gated), "
        "adds minimal extras, resolves a matching background as its own output, and emits the "
        "CHARACTER object, its JSON twin, Description, Keywords, Background, Occasion and Trigger."
    )

    RETURN_TYPES: tuple[str, ...] = ("CHARACTER", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = (
        "Character",
        "Character JSON",
        "Description",
        "Keywords",
        "Background",
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
                "Wardrobe Source": (
                    list(WARDROBE_MODES),
                    {
                        "default": WARDROBE_EXTERNAL,
                        "tooltip": (
                            "Use External Wardrobe (default): dress from the shared common wardrobe within the "
                            "character's lewdity band, falling back to their own clothes. "
                            "Use Internal Wardrobe: only the persona's own curated wardrobe. "
                            "Use Complete Wardrobe: everything from the common wardrobe, lewdity ignored."
                        ),
                    },
                ),
                "Lewdity Min": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 1000000,
                        "tooltip": "Override the lewdity band's lower edge. -1 = use the persona's lewdity.txt.",
                    },
                ),
                "Lewdity Max": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 1000000,
                        "tooltip": "Override the lewdity band's upper edge. -1 = use the persona's lewdity.txt.",
                    },
                ),
                "Time of Day": (
                    _time_options(),
                    {
                        "default": _ANY_FILTER,
                        "tooltip": "Optional filter for the background location's time phrasing (scanned from the location files).",
                    },
                ),
                "Domain": (
                    _domain_options(),
                    {
                        "default": _ANY_FILTER,
                        "tooltip": "Optional filter for the background location's reality family, e.g. waterfront or civic (scanned from the location files).",
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
                        "tooltip": "JSON config managed by the frontend. Format: {\"occasions\": [...]}",
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
            str(kwargs.get("Wardrobe Source", WARDROBE_EXTERNAL)),
            int(kwargs.get("Lewdity Min", -1)),
            int(kwargs.get("Lewdity Max", -1)),
            str(kwargs.get("Time of Day", _ANY_FILTER)),
            str(kwargs.get("Domain", _ANY_FILTER)),
            str(kwargs.get("Character Config", "")),
            camera_regions,
            camera_view,
        )

    def build(self, **kwargs: Any) -> dict[str, Any]:
        """Build the CHARACTER object and return results for UI and downstream nodes.

        Args:
            **kwargs: ComfyUI widget/input values. Expected keys: ``"Persona"``,
                ``"Camera"``, ``"Wardrobe Source"``, ``"Lewdity Min"``,
                ``"Lewdity Max"``, ``"Time of Day"``, ``"Domain"``, ``"Seed"``,
                ``"Wildcard Mode"``, ``"Character Config"``.

        Returns:
            A dict with a 7-tuple ``"result"`` matching the node's
            ``RETURN_TYPES`` (Character object, JSON, Description, Keywords,
            Background, Occasion, Trigger).
        """
        persona: str = str(kwargs.get("Persona", "female"))
        camera: Any = kwargs.get("Camera")
        wardrobe_source: str = str(kwargs.get("Wardrobe Source", WARDROBE_EXTERNAL))
        lewdity_min: int = int(kwargs.get("Lewdity Min", -1))
        lewdity_max: int = int(kwargs.get("Lewdity Max", -1))
        time_raw: str = str(kwargs.get("Time of Day", _ANY_FILTER))
        domain_raw: str = str(kwargs.get("Domain", _ANY_FILTER))
        seed: int = int(kwargs.get("Seed", 0))
        mode: str = str(kwargs.get("Wildcard Mode", _DETERMINISTIC_MODE))

        time_of_day: str = "" if time_raw == _ANY_FILTER else time_raw.strip().lower()
        domain: str = "" if domain_raw == _ANY_FILTER else domain_raw.strip().lower()

        occasion = ""
        occasion_options: list[str] | None = None
        config_json = kwargs.get("Character Config")
        if config_json is not None:
            occasions = _parse_character_config(str(config_json))
            if occasions is None:
                occasion_options = [value for value in _occasion_options() if value != _ALL_OCCASIONS]
            elif len(occasions) == 1:
                occasion = occasions[0]
            elif occasions:
                occasion_options = occasions
            # An empty occasions list means truly unrestricted (no roll).
        else:
            occasion_options = [value for value in _occasion_options() if value != _ALL_OCCASIONS]

        character = build_character(
            _WILDCARDS_DIR,
            persona,
            camera if isinstance(camera, dict) else None,
            occasion,
            wardrobe_source,
            mode,
            seed,
            occasion_options=occasion_options,
            lewdity_min=lewdity_min,
            lewdity_max=lewdity_max,
            time_of_day=time_of_day,
            domain=domain,
        )

        character_json = json.dumps(character)

        rolled = occasion == "" and character["occasion"] != ""
        band = character["lewdity"]
        band_text = (
            f"{band[0]}-{band[1]}"
            if band
            else "(none — own wardrobe only)"
        )
        info_string = (
            f"Persona: {character['persona']}\n"
            f"Wardrobe: {character['wardrobe_mode']} ({character['wardrobe_base'] or 'none'})\n"
            f"Lewdity: {band_text}\n"
            f"Outfit: {character['outfit_category'] or '(none)'}\n"
            f"Occasion: {character['occasion'] or '(unrestricted)'}{' (random)' if rolled else ''}\n"
            f"Background: {character['background'][:80] or '(empty)'}\n"
            f"Regions: {', '.join(character['regions'])}\n"
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
                character["background"],
                character["occasion"],
                character["trigger"],
            ),
        }


# Frontend options endpoint: serves the occasion, wardrobe-source, time and
# domain spaces so the UI chips and dropdowns always match the backend.
try:  # pragma: no cover - ComfyUI-only integration
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/that_aigod/character_options")  # type: ignore[untyped-decorator]
    async def _character_options_endpoint(_request: Any) -> Any:
        return web.json_response(
            {
                "occasions": [value for value in _occasion_options() if value != _ALL_OCCASIONS],
                "wardrobe_modes": list(WARDROBE_MODES),
                "times": _time_options(),
                "domains": _domain_options(),
                "occasion_groups": [
                    {"text": text, "members": members}
                    for text, members in _OCCASION_GROUPS.items()
                ],
            }
        )

except Exception:  # noqa: BLE001, S110 - absent in pure-test environments
    pass


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
    "WARDROBE_EXTERNAL",
    "WARDROBE_INTERNAL",
    "WARDROBE_COMPLETE",
    "_persona_options",
    "_occasion_options",
    "_time_options",
    "_domain_options",
]
