"""Pure camera-shot engine for the Camera node.

Implements a director-style shot grammar built from three independent axes —
shot size (how much of the subject is in frame), camera angle (height and
attitude) and view (which side of the subject the camera sees) — plus two
modifiers: camera movement and dutch tilt.  Every pick is seeded and
deterministic; the node supports three selection modes:

* ``Deterministic (Seed)`` — one seeded draw per axis from the active sets.
* ``Full Auto`` — the full option space on every axis, still seeded.
* ``Random (No Repeat)`` — a session-scoped shuffle bag that cycles through
  every combination of the active sets before repeating anything.

The engine is *geometry honest*: the visible body regions are the
intersection of the shot-size set, the angle set and the view set, so a back
view never mentions the eyes and a top-down never mentions the face.

The module has no node code and depends only on the standard library.
"""

from __future__ import annotations

import json
import os
import random
import re
import zlib
from itertools import product
from typing import Any

# ---------------------------------------------------------------------------
# Axis vocabulary
# ---------------------------------------------------------------------------

SHOT_SIZES: list[str] = [
    "Extreme Close-Up",
    "Close-Up",
    "Medium Close-Up",
    "Medium",
    "Cowboy",
    "Medium Full",
    "Full",
    "Long",
    "Extreme Long",
]

ANGLES: list[str] = [
    "Eye Level",
    "Low Angle",
    "High Angle",
    "Top Down",
    "Worm's Eye",
]

VIEWS: list[str] = [
    "Front",
    "3/4 Front",
    "Profile",
    "3/4 Back",
    "Back",
]

MOVEMENTS: list[str] = [
    "Static",
    "Pan",
    "Tilt",
    "Tracking",
    "Handheld",
]

TILTS: list[str] = [
    "None",
    "Slight",
    "Strong",
]

# ---------------------------------------------------------------------------
# Look axis (render character)
# ---------------------------------------------------------------------------

# Famous camera bodies and film stocks as a render-character axis.  Entries
# describe how the image is *rendered* (format, era, grain, color science) —
# never a focal length, which stays owned by the shot-size lens map.
LOOKS: list[str] = [
    "Hasselblad 500C/M",
    "Rolleiflex 2.8F",
    "Mamiya RZ67 Pro II",
    "Leica M6",
    "Nikon F3",
    "Canon AE-1 Program",
    "Pentax K1000",
    "Contax T2",
    "Fujifilm X100V",
    "Sony A7R V",
    "Leica M11",
    "Canon EOS R5",
    "RED Komodo 6K",
    "ARRI Alexa Mini",
    "iPhone 15 Pro",
]

# Family buckets for future Scene-side filtering (a Scene node can assert a
# ``look`` context dimension against these).
_LOOK_FAMILIES: dict[str, tuple[str, ...]] = {
    "film": (
        "Hasselblad 500C/M",
        "Rolleiflex 2.8F",
        "Mamiya RZ67 Pro II",
        "Leica M6",
        "Nikon F3",
        "Canon AE-1 Program",
        "Pentax K1000",
        "Contax T2",
    ),
    "digital": (
        "Fujifilm X100V",
        "Sony A7R V",
        "Leica M11",
        "Canon EOS R5",
        "RED Komodo 6K",
        "ARRI Alexa Mini",
        "iPhone 15 Pro",
    ),
    "medium format": (
        "Hasselblad 500C/M",
        "Rolleiflex 2.8F",
        "Mamiya RZ67 Pro II",
    ),
    "35mm": (
        "Leica M6",
        "Nikon F3",
        "Canon AE-1 Program",
        "Pentax K1000",
        "Contax T2",
    ),
    "cinema": ("RED Komodo 6K", "ARRI Alexa Mini"),
}

_LOOK_PHRASES: dict[str, list[str]] = {
    "Hasselblad 500C/M": [
        "Shot on a Hasselblad 500C/M, its medium-format film rendering softly rounded tones with gentle grain.",
        "Captured on a Hasselblad 500C/M, medium-format film lending the frame creamy texture and natural color.",
    ],
    "Rolleiflex 2.8F": [
        "Shot on a Rolleiflex 2.8F twin-lens reflex, smooth medium-format tones with fine, even grain.",
        "Captured on a Rolleiflex 2.8F, its waist-level finder framing a look of quiet, measured calm.",
    ],
    "Mamiya RZ67 Pro II": [
        "Shot on a Mamiya RZ67 Pro II, medium-format film with rich tonality and pronounced lens character.",
        "Captured on a Mamiya RZ67 Pro II, large negatives delivering deep, saturated film color.",
    ],
    "Leica M6": [
        "Shot on a Leica M6 rangefinder, 35mm film with delicate grain and honest, natural color.",
        "Captured on a Leica M6, its classic 35mm look staying unobtrusive and truthful.",
    ],
    "Nikon F3": [
        "Shot on a Nikon F3, professional 35mm film with crisp yet gentle rendering.",
        "Captured on a Nikon F3, a workhorse SLR look with balanced, neutral color.",
    ],
    "Canon AE-1 Program": [
        "Shot on a Canon AE-1 Program, classic 35mm film with warm color and subtle grain.",
        "Captured on a Canon AE-1 Program, the warm analog look of the classic-era SLR.",
    ],
    "Pentax K1000": [
        "Shot on a Pentax K1000, no-frills 35mm film with honest texture and gentle grain.",
        "Captured on a Pentax K1000, a simple film look with natural contrast.",
    ],
    "Contax T2": [
        "Shot on a Contax T2, a luxury compact capturing clean, refined film tones.",
        "Captured on a Contax T2, sharp compact rendering with a premium point-and-shoot feel.",
    ],
    "Fujifilm X100V": [
        "Shot on a Fujifilm X100V, its film-simulation colors lending a balanced, modern rendering.",
        "Captured on a Fujifilm X100V, clean digital detail with tasteful color grading.",
    ],
    "Sony A7R V": [
        "Shot on a Sony A7R V, high-resolution digital with clinically sharp, neutral detail.",
        "Captured on a Sony A7R V, modern full-frame digital with clean, exact color.",
    ],
    "Leica M11": [
        "Shot on a Leica M11 digital rangefinder with smooth highlight roll-off.",
        "Captured on a Leica M11, refined digital rendering with beautiful tonal smoothness.",
    ],
    "Canon EOS R5": [
        "Shot on a Canon EOS R5, modern digital with vibrant yet accurate color.",
        "Captured on a Canon EOS R5, crisp digital detail with professional color science.",
    ],
    "RED Komodo 6K": [
        "Shot on a RED Komodo 6K, digital cinema capture with deep dynamic range.",
        "Captured on a RED Komodo 6K, cinematic stills with rich shadow detail.",
    ],
    "ARRI Alexa Mini": [
        "Shot on an ARRI Alexa Mini, cinematic digital with beautiful highlight roll-off and rich skintones.",
        "Captured on an ARRI Alexa Mini, the industry-standard cinema look with natural color.",
    ],
    "iPhone 15 Pro": [
        "Shot on an iPhone 15 Pro, computational smartphone photography with crisp detail.",
        "Captured on an iPhone 15 Pro, HDR-processing modern phone rendering.",
    ],
}

_LOOK_KEYWORDS: dict[str, str] = {
    "Hasselblad 500C/M": "Medium Format Film, Soft Film Grain, Natural Color Science, 6x6 Medium Format",
    "Rolleiflex 2.8F": "Medium Format Film, Twin-Lens Reflex, Fine Film Grain, Smooth Tonal Rendering",
    "Mamiya RZ67 Pro II": "Medium Format Film, Rich Tonality, Pronounced Lens Character, Film Color",
    "Leica M6": "35mm Rangefinder Film, Delicate Film Grain, Honest Natural Color, Classic 35mm Look",
    "Nikon F3": "35mm Film, Professional SLR, Fine Film Grain, Neutral Color Balance",
    "Canon AE-1 Program": "35mm Film, Classic SLR, Warm Color Cast, Subtle Film Grain",
    "Pentax K1000": "35mm Film, Analog SLR, Honest Texture, Film Grain",
    "Contax T2": "35mm Compact Film, Sharp Compact Lens, Clean Film Tones, Premium Point-and-Shoot",
    "Fujifilm X100V": "Mirrorless Digital, Film Simulation Colors, Balanced Rendering, Modern Clean Look",
    "Sony A7R V": "Full-Frame Digital, High Resolution, Clinically Sharp Detail, Neutral Modern Color",
    "Leica M11": "Digital Rangefinder, Smooth Highlight Roll-Off, Clean Digital Color, Modern Classic",
    "Canon EOS R5": "Full-Frame Digital, Vibrant Accurate Color, Crisp Digital Detail, Professional Color Science",
    "RED Komodo 6K": "Digital Cinema Look, Rich Dynamic Range, Cinematic Color Science, Deep Shadows",
    "ARRI Alexa Mini": "Digital Cinema, Cinematic Color Science, Smooth Highlight Roll-Off, Rich Skintones",
    "iPhone 15 Pro": "Smartphone Computational Photography, Crisp Digital Detail, HDR Processing, Modern Phone Look",
}

# ---------------------------------------------------------------------------
# Body regions
# ---------------------------------------------------------------------------

# The full region vocabulary used by downstream character nodes.
_ALL_REGIONS: list[str] = [
    "face",
    "hair",
    "neck",
    "shoulders",
    "chest",
    "back",
    "breasts",
    "navel",
    "arms",
    "hands",
    "waist",
    "hips",
    "buttocks",
    "thighs",
    "legs",
    "feet",
    "skin",
]

# Potential regions per shot size (front AND back features — the geometry
# strips the hidden side afterwards).
_REGIONS_BY_SIZE: dict[str, list[str]] = {
    "Extreme Close-Up": ["face", "hair", "neck", "skin"],
    "Close-Up": ["face", "hair", "neck", "shoulders", "skin"],
    "Medium Close-Up": ["face", "hair", "neck", "shoulders", "chest", "back", "skin"],
    "Medium": [
        "face",
        "hair",
        "neck",
        "shoulders",
        "chest",
        "back",
        "breasts",
        "arms",
        "hands",
        "waist",
        "skin",
    ],
    "Cowboy": [
        "face",
        "hair",
        "neck",
        "shoulders",
        "chest",
        "back",
        "breasts",
        "navel",
        "arms",
        "hands",
        "waist",
        "hips",
        "thighs",
        "skin",
    ],
    "Medium Full": [
        "face",
        "hair",
        "neck",
        "shoulders",
        "chest",
        "back",
        "breasts",
        "navel",
        "arms",
        "hands",
        "waist",
        "hips",
        "buttocks",
        "thighs",
        "legs",
        "skin",
    ],
    "Full": [
        "face",
        "hair",
        "neck",
        "shoulders",
        "chest",
        "back",
        "breasts",
        "navel",
        "arms",
        "hands",
        "waist",
        "hips",
        "buttocks",
        "thighs",
        "legs",
        "feet",
        "skin",
    ],
    "Long": [
        "face",
        "hair",
        "neck",
        "shoulders",
        "chest",
        "back",
        "breasts",
        "navel",
        "arms",
        "hands",
        "waist",
        "hips",
        "buttocks",
        "thighs",
        "legs",
        "feet",
        "skin",
        "environment",
    ],
    "Extreme Long": [
        "face",
        "hair",
        "neck",
        "shoulders",
        "chest",
        "back",
        "breasts",
        "navel",
        "arms",
        "hands",
        "waist",
        "hips",
        "buttocks",
        "thighs",
        "legs",
        "feet",
        "skin",
        "environment",
    ],
}

# ---------------------------------------------------------------------------
# Lens, depth of field, gimbal
# ---------------------------------------------------------------------------

_LENS_BY_SIZE: dict[str, str] = {
    "Extreme Close-Up": "100mm macro lens",
    "Close-Up": "85mm portrait lens",
    "Medium Close-Up": "85mm lens",
    "Medium": "50mm lens",
    "Cowboy": "50mm lens",
    "Medium Full": "35mm lens",
    "Full": "35mm lens",
    "Long": "24mm wide-angle lens",
    "Extreme Long": "16mm wide-angle lens",
}

_DEPTH_BY_SIZE: dict[str, str] = {
    "Extreme Close-Up": "shallow depth of field",
    "Close-Up": "shallow depth of field",
    "Medium Close-Up": "shallow depth of field",
    "Medium": "moderate depth of field",
    "Cowboy": "moderate depth of field",
    "Medium Full": "moderate depth of field",
    "Full": "deep depth of field",
    "Long": "deep focus",
    "Extreme Long": "deep focus",
}

# Camera-relative angles in degrees (negative = below the subject).
_ELEVATION_DEGREES: dict[str, int] = {
    "Eye Level": 0,
    "Low Angle": -20,
    "High Angle": 45,
    "Top Down": 90,
    "Worm's Eye": -60,
}

# Subject-relative azimuth in degrees (0 = dead front, sign by chosen side).
_AZIMUTH_DEGREES: dict[str, int] = {
    "Front": 0,
    "3/4 Front": 45,
    "Profile": 90,
    "3/4 Back": 135,
    "Back": 180,
}

_ROLL_DEGREES: dict[str, int] = {
    "None": 0,
    "Slight": 8,
    "Strong": 20,
}

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


# Regions a directly-above camera cannot see (head and shoulders block them).
# Any angle at elevation 90 — including custom wildcard angles — inherits
# these, so overhead shots never prompt front-facing features.
_TOP_DOWN_HIDES: frozenset[str] = frozenset({"face", "neck", "chest", "breasts", "navel", "skin"})

# How many body regions each angle/view keeps hidden from the frame.  These
# tables are the single source of geometry: the built-in space builds records
# from them, and wildcard option files override them per option.
_ANGLE_HIDES: dict[str, frozenset[str]] = {
    "Eye Level": frozenset(),
    "Low Angle": frozenset(),
    "High Angle": frozenset(),
    "Top Down": _TOP_DOWN_HIDES,
    "Worm's Eye": frozenset({"hair"}),
}

_VIEW_HIDES: dict[str, frozenset[str]] = {
    "Front": frozenset({"back", "buttocks"}),
    "3/4 Front": frozenset({"back", "buttocks"}),
    "Profile": frozenset({"back", "buttocks", "chest", "breasts", "navel"}),
    "3/4 Back": frozenset({"face", "chest", "breasts", "navel", "skin"}),
    "Back": frozenset({"face", "chest", "breasts", "navel", "skin"}),
}

# Shortcut groups per axis (the frontend's one-tap buttons).  Mirrors
# js/camera.js; wildcard option files may re-assign membership via #@shortcuts.
_BASE_SHORTCUTS: dict[str, dict[str, tuple[str, ...]]] = {
    "sizes": {
        "Close-ups": ("Extreme Close-Up", "Close-Up", "Medium Close-Up"),
        "Fulls": ("Full", "Long", "Extreme Long"),
    },
    "angles": {
        "Below": ("Low Angle", "Worm's Eye"),
        "Above": ("High Angle", "Top Down"),
    },
    "views": {
        "Facing": ("Front", "3/4 Front"),
        "Away": ("Back", "3/4 Back"),
    },
    "movements": {
        "Static": ("Static",),
        "Motion": ("Pan", "Tilt", "Tracking", "Handheld"),
    },
    "tilts": {
        "Level": ("None",),
        "Dutch": ("Slight", "Strong"),
    },
    "looks": {
        "Film": (
            "Hasselblad 500C/M",
            "Rolleiflex 2.8F",
            "Mamiya RZ67 Pro II",
            "Leica M6",
            "Nikon F3",
            "Canon AE-1 Program",
            "Pentax K1000",
            "Contax T2",
        ),
        "Digital": (
            "Fujifilm X100V",
            "Sony A7R V",
            "Leica M11",
            "Canon EOS R5",
            "RED Komodo 6K",
            "ARRI Alexa Mini",
            "iPhone 15 Pro",
        ),
    },
}


def face_visible(angle: str, view: str) -> bool:
    """Return whether the subject's face is in frame for the geometry pair.

    A top-down camera hides the face; views from behind (``Back``,
    ``3/4 Back``) hide it because the camera decides the subject's facing.

    Args:
        angle: The camera angle axis value.
        view: The view axis value.

    Returns:
        ``True`` when the face (and therefore eyes, facial skin) is visible.
    """
    space = _builtin_space()
    hidden = space["angles"][angle]["hides"] | space["views"][view]["hides"]
    return "face" not in hidden


def visible_regions(size: str, angle: str, view: str) -> list[str]:
    """Return the visible body regions for a shot combination.

    Starts from the shot size's potential set and strips every region the
    angle and view hide (see :data:`_ANGLE_HIDES` / :data:`_VIEW_HIDES`).

    Args:
        size: The shot size axis value.
        angle: The camera angle axis value.
        view: The view axis value.

    Returns:
        The visible region names, ordered as in the size's base list.
    """
    space = _builtin_space()
    base = list(space["sizes"][size]["regions"])
    hidden = space["angles"][angle]["hides"] | space["views"][view]["hides"]
    return [region for region in base if region not in hidden]


def _orientation(width: int, height: int) -> str:
    """Return the aspect-ratio orientation bucket for *width* × *height*."""
    ratio = width / height if height > 0 else 1.0
    if ratio < 0.9:
        return "portrait"
    if ratio > 1.1:
        return "landscape"
    return "square"


# ---------------------------------------------------------------------------
# Prose templates
# ---------------------------------------------------------------------------

_SHOT_PHRASES: dict[str, list[str]] = {
    "Extreme Close-Up": ["An extreme close-up", "A tight extreme close-up"],
    "Close-Up": ["A close-up", "An intimate close-up"],
    "Medium Close-Up": ["A medium close-up", "A warm medium close-up"],
    "Medium": ["A medium shot", "A waist-up shot"],
    "Cowboy": ["A cowboy shot", "A mid-thigh framing"],
    "Medium Full": ["A medium full shot", "A three-quarter-length shot"],
    "Full": ["A full-body shot", "A full-length shot"],
    "Long": ["A long shot", "A wide long shot"],
    "Extreme Long": ["An extreme long shot", "A vast extreme long shot"],
}

_ANGLE_PHRASES: dict[str, list[str]] = {
    "Eye Level": ["shot at eye level", "captured from eye level"],
    "Low Angle": [
        "shot from a low angle with the camera at chest height",
        "captured from a low angle, the camera tilted up from below the subject",
    ],
    "High Angle": [
        "shot from a high angle with the camera looking down",
        "captured from an elevated position looking down on the subject",
    ],
    "Top Down": ["shot directly from above", "captured from a top-down bird's-eye perspective"],
    "Worm's Eye": [
        "shot from a worm's-eye perspective, the camera low to the ground and angled steeply upward",
        "captured from ground level, the camera aimed steeply upward at the subject",
    ],
}

_VIEW_PHRASES: dict[str, list[str]] = {
    "Front": ["the subject facing the camera squarely", "the subject turned head-on to the lens"],
    "3/4 Front": [
        "the subject caught in three-quarter view from the {side}",
        "the subject in three-quarter front, angled toward the {side}",
    ],
    "Profile": [
        "the subject in full profile, {side} side toward the camera",
        "the subject seen in profile, facing {side}",
    ],
    "3/4 Back": [
        "the subject turned mostly away, three-quarter back toward the {side}",
        "the subject in three-quarter back view, angled away to the {side}",
    ],
    "Back": ["the subject seen from behind", "the subject with their back to the camera"],
}

_MOVEMENT_PHRASES: dict[str, dict[str, list[str]]] = {
    "Static": {
        "close": ["the camera holding perfectly still", "the camera locked off in a static frame"],
        "wide": ["the camera holding perfectly still", "the camera locked off in a static frame"],
    },
    "Pan": {
        "close": ["a slow shutter pan drawing soft motion blur across the frame"],
        "wide": [
            "a slow shutter pan streaking the background into motion blur",
            "a long-exposure pan trailing the scene into soft motion blur",
        ],
    },
    "Tilt": {
        "close": ["a slow vertical pan with soft motion blur across the frame"],
        "wide": [
            "a slow vertical pan streaking the background into motion blur",
            "a long-exposure vertical pan carrying the frame into soft blur",
        ],
    },
    "Tracking": {
        "close": ["an action pan holding the subject sharp against a motion-blurred background"],
        "wide": [
            "an action pan holding the subject sharp while the background streaks with motion blur",
            "a panning shot with the subject frozen against a motion-blurred background",
        ],
    },
    "Handheld": {
        "close": [
            "a subtle handheld sway keeping the frame alive",
            "a handheld shot with faint natural camera shake",
        ],
        "wide": [
            "a subtle handheld sway keeping the frame alive",
            "a handheld shot with faint natural camera shake",
        ],
    },
}

_MOVEMENT_KEYWORDS: dict[str, str] = {
    "Static": "",
    "Pan": "Slow Shutter, Motion Blur, Panning Shot",
    "Tilt": "Slow Shutter, Motion Blur, Vertical Pan",
    "Tracking": "Motion Blur, Panning Shot, Action Shot",
    "Handheld": "Handheld Shot, Slight Camera Shake",
}

_TILT_PHRASES: dict[str, list[str]] = {
    "None": [""],
    "Slight": [
        ", framed with a slight dutch angle",
        ", a subtle dutch angle giving the frame a gentle lean",
    ],
    "Strong": [
        ", framed with a pronounced dutch angle",
        ", a bold dutch angle driving the composition",
    ],
}

_TILT_KEYWORDS: dict[str, str] = {
    "None": "",
    "Slight": "Slight Dutch Angle",
    "Strong": "Strong Dutch Angle",
}

_COMPOSITION_PHRASES: dict[str, str] = {
    "portrait": "a vertical composition with generous headroom above the subject",
    "square": "a balanced square composition with the subject centered",
    "landscape": "a wide horizontal composition with breathing room on either side",
}

# Close framings fill the frame with the face; headroom language is wrong here.
_COMPOSITION_CLOSE: dict[str, str] = {
    "portrait": "a vertical composition framing the subject's face",
    "square": "a balanced square composition framing the subject's face",
    "landscape": "a wide horizontal composition framing the subject's face",
}

# Long framings place the subject small within the scene.
_COMPOSITION_LONG: dict[str, str] = {
    "portrait": "a vertical composition with the subject placed small within the frame",
    "square": "a balanced square composition with the subject placed small within the frame",
    "landscape": "a wide horizontal composition with the subject placed small within the frame",
}

# Directly-above framings have no headroom; headroom language is meaningless.
_COMPOSITION_TOP_DOWN: dict[str, str] = {
    "portrait": "a vertical composition looking directly down onto the subject",
    "square": "a balanced square composition looking directly down onto the subject",
    "landscape": "a wide horizontal composition looking directly down onto the subject",
}

# Sizes whose framing leaves the subject small inside a larger scene.
_LONG_SIZES: frozenset[str] = frozenset({"Long", "Extreme Long"})

# Sizes whose framing fills the frame with the subject's head and shoulders;
# movement and composition phrases must scale down to these framings.
_CLOSE_SIZES: frozenset[str] = frozenset({"Extreme Close-Up", "Close-Up", "Medium Close-Up"})


# ---------------------------------------------------------------------------
# Option space (built-in records + wildcard customization)
# ---------------------------------------------------------------------------
#
# Every axis is an *option space*: a dict of option name → record.  The
# built-in space is derived from the module tables above.  A ``wildcards/camera/``
# tree (one .txt file per option, ``#@`` directives for metadata) replaces the
# space per-axis; the built-in space remains the fallback when the tree or an
# axis folder is missing.  Records carry everything the engine needs, so a
# custom option with ``#@based_on`` inherits the geometry and text of an
# existing option and overrides only what its file spells out.

_CAMERA_DIR_NAME: str = "camera"
_AXIS_DIRS: tuple[str, ...] = ("sizes", "angles", "views", "movements", "tilts", "looks")

_DIRECTIVE_RE = re.compile(r"^#@([A-Za-z][A-Za-z0-9_]*):\s*(.*)$")
_BLOCK_RE = re.compile(r"^#@([A-Za-z][A-Za-z0-9_]*)\s*$")

_BUILTIN_SPACE: dict[str, dict[str, dict[str, Any]]] | None = None


def _builtin_space() -> dict[str, dict[str, dict[str, Any]]]:
    """Return the built-in option space derived from the module tables."""
    global _BUILTIN_SPACE
    if _BUILTIN_SPACE is not None:
        return _BUILTIN_SPACE

    def groups(axis: str, name: str) -> frozenset[str]:
        return frozenset(group for group, members in _BASE_SHORTCUTS[axis].items() if name in members)

    sizes: dict[str, dict[str, Any]] = {}
    for name in SHOT_SIZES:
        sizes[name] = {
            "name": name,
            "regions": tuple(_REGIONS_BY_SIZE[name]),
            "lens": _LENS_BY_SIZE[name],
            "depth": _DEPTH_BY_SIZE[name],
            "close": name in _CLOSE_SIZES,
            "long": name in _LONG_SIZES,
            "keyword": _SIZE_KEYWORDS[name],
            "phrases": tuple(_SHOT_PHRASES[name]),
            "shortcuts": groups("sizes", name),
        }
    angles: dict[str, dict[str, Any]] = {}
    for name in ANGLES:
        angles[name] = {
            "name": name,
            "elevation": _ELEVATION_DEGREES[name],
            "hides": _ANGLE_HIDES[name],
            "keyword": _ANGLE_KEYWORDS[name],
            "phrases": tuple(_ANGLE_PHRASES[name]),
            "shortcuts": groups("angles", name),
        }
    views: dict[str, dict[str, Any]] = {}
    for name in VIEWS:
        views[name] = {
            "name": name,
            "azimuth": _AZIMUTH_DEGREES[name],
            "hides": _VIEW_HIDES[name],
            "keyword": _VIEW_KEYWORDS[name],
            "phrases": tuple(_VIEW_PHRASES[name]),
            "shortcuts": groups("views", name),
        }
    movements: dict[str, dict[str, Any]] = {}
    for name in MOVEMENTS:
        movements[name] = {
            "name": name,
            "close": tuple(_MOVEMENT_PHRASES[name]["close"]),
            "wide": tuple(_MOVEMENT_PHRASES[name]["wide"]),
            "keyword": _MOVEMENT_KEYWORDS[name],
            "shortcuts": groups("movements", name),
        }
    tilts: dict[str, dict[str, Any]] = {}
    for name in TILTS:
        tilts[name] = {
            "name": name,
            "roll": _ROLL_DEGREES[name],
            "keyword": _TILT_KEYWORDS[name],
            "phrases": tuple(phrase.strip().lstrip(", ") for phrase in _TILT_PHRASES[name]),
            "shortcuts": groups("tilts", name),
        }
    looks: dict[str, dict[str, Any]] = {}
    for name in LOOKS:
        family = "film" if name in _LOOK_FAMILIES["film"] else "digital"
        looks[name] = {
            "name": name,
            "family": family,
            "keywords": _LOOK_KEYWORDS[name],
            "phrases": tuple(_LOOK_PHRASES[name]),
            "shortcuts": frozenset({"Film" if family == "film" else "Digital"}),
        }
    _BUILTIN_SPACE = {
        "sizes": sizes,
        "angles": angles,
        "views": views,
        "movements": movements,
        "tilts": tilts,
        "looks": looks,
    }
    return _BUILTIN_SPACE


def _parse_int(value: str, fallback: int | None) -> int | None:
    try:
        return int(value)
    except ValueError:
        return fallback


def _parse_option_file(path: str) -> dict[str, Any]:
    """Parse one camera-option wildcard file into directive + phrase data.

    Directives are ``#@key: value`` lines; section markers are ``#@close`` and
    ``#@wide`` (movements only).  Everything else is a phrase line collected
    into the active section (``phrases`` by default).
    """
    result: dict[str, Any] = {
        "name": None,
        "based_on": None,
        "keyword": None,
        "shortcuts": None,
        "lens": None,
        "depth": None,
        "close": None,
        "regions": None,
        "hides": None,
        "elevation": None,
        "azimuth": None,
        "roll": None,
        "family": None,
        "phrases": [],
        "close_phrases": [],
        "wide_phrases": [],
    }
    section: str = "phrases"
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            match = _DIRECTIVE_RE.match(line)
            if match is not None:
                key, value = match.group(1), match.group(2).strip()
                if key == "name":
                    result["name"] = value
                elif key == "based_on":
                    result["based_on"] = value
                elif key == "keyword":
                    result["keyword"] = value
                elif key == "shortcuts":
                    result["shortcuts"] = frozenset(part.strip() for part in value.split(",") if part.strip())
                elif key == "lens":
                    result["lens"] = value
                elif key == "depth":
                    result["depth"] = value
                elif key == "close":
                    result["close"] = value.lower() in ("true", "1", "yes")
                elif key == "regions":
                    result["regions"] = tuple(part.strip().lower() for part in value.split(",") if part.strip())
                elif key == "hides":
                    result["hides"] = frozenset(part.strip().lower() for part in value.split(",") if part.strip())
                elif key == "elevation":
                    result["elevation"] = _parse_int(value, result["elevation"])
                elif key == "azimuth":
                    result["azimuth"] = _parse_int(value, result["azimuth"])
                elif key == "roll":
                    result["roll"] = _parse_int(value, result["roll"])
                elif key == "family":
                    result["family"] = value.lower()
                continue
            block = _BLOCK_RE.match(line)
            if block is not None:
                if block.group(1) in ("close", "wide"):
                    section = block.group(1)
                continue
            if line.startswith("#"):
                continue
            if section == "close":
                result["close_phrases"].append(line)
            elif section == "wide":
                result["wide_phrases"].append(line)
            else:
                result["phrases"].append(line)
    return result


def _resolve_option(axis: str, name: str, parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a parsed option file against the built-in space.

    The base record is the built-in option with the same name, or the built-in
    named by ``#@based_on``; anything the file spells out overrides the base.
    Returns ``None`` when no base exists (an option the engine cannot reason
    about geometrically).
    """
    base_name = name if name in _builtin_space()[axis] else parsed["based_on"]
    base = _builtin_space()[axis].get(base_name or "")
    if base is None:
        return None
    record = dict(base)
    if parsed["phrases"]:
        record["phrases"] = tuple(parsed["phrases"])
    if parsed["close_phrases"]:
        record["close"] = tuple(parsed["close_phrases"])
    if parsed["wide_phrases"]:
        record["wide"] = tuple(parsed["wide_phrases"])
    for field in ("keyword", "lens", "depth", "family"):
        if parsed[field] and not (axis == "looks" and field == "keyword"):
            record[field] = parsed[field]
    if axis == "looks" and parsed["keyword"]:
        record["keywords"] = parsed["keyword"]
    for field in ("elevation", "azimuth", "roll"):
        if parsed[field] is not None:
            record[field] = parsed[field]
    if parsed["close"] is not None:
        record["close"] = parsed["close"]
    if parsed["regions"] is not None:
        record["regions"] = parsed["regions"]
    if parsed["hides"] is not None:
        record["hides"] = parsed["hides"]
    if parsed["shortcuts"] is not None:
        record["shortcuts"] = parsed["shortcuts"]
    record["name"] = name
    return record


def load_option_space(wildcards_dir: str) -> dict[str, dict[str, dict[str, Any]]] | None:
    """Load the option space from ``wildcards_dir/camera/<axis>/*.txt``.

    Each axis folder replaces that axis's built-in options (a missing or
    empty axis folder falls back to the built-ins).  Files starting with ``.``
    or ``_`` are ignored.  Options that cannot resolve to a base (no built-in
    of that name and no ``#@based_on``) are skipped.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.

    Returns:
        The per-axis option space, or ``None`` when the camera tree is absent.
    """
    root = os.path.join(wildcards_dir, _CAMERA_DIR_NAME)
    if not os.path.isdir(root):
        return None
    builtin = _builtin_space()
    space: dict[str, dict[str, dict[str, Any]]] = {}
    for axis in _AXIS_DIRS:
        axis_dir = os.path.join(root, axis)
        if not os.path.isdir(axis_dir):
            space[axis] = dict(builtin[axis])
            continue
        records: dict[str, dict[str, Any]] = {}
        for entry in sorted(os.listdir(axis_dir)):
            if not entry.endswith(".txt") or entry.startswith((".", "_")):
                continue
            parsed = _parse_option_file(os.path.join(axis_dir, entry))
            name = parsed["name"] or os.path.splitext(entry)[0]
            if name in records:
                continue
            record = _resolve_option(axis, name, parsed)
            if record is None:
                continue
            records[name] = record
        space[axis] = records if records else dict(builtin[axis])
    return space


def option_shortcuts(space: dict[str, dict[str, dict[str, Any]]], axis: str) -> list[tuple[str, list[str]]]:
    """Return the shortcut groups of an axis as ``(group, members)`` pairs.

    Groups are ordered by first appearance across the axis options (in space
    order); members follow the space order.
    """
    ordered: list[str] = []
    members: dict[str, list[str]] = {}
    for name, record in space[axis].items():
        for group in sorted(record["shortcuts"]):
            if group not in members:
                members[group] = []
                ordered.append(group)
            members[group].append(name)
    return [(group, members[group]) for group in ordered]


# Keyword overrides: the tokens that actually reach the model.  These may
# differ from the axis option names (which stay a js/config contract) so the
# prompt carries model-friendly tags while the UI keeps its vocabulary.
_SIZE_KEYWORDS: dict[str, str] = {
    "Extreme Close-Up": "Extreme Close-Up",
    "Close-Up": "Close-Up",
    "Medium Close-Up": "Medium Close-Up Shot",
    "Medium": "Medium Shot",
    "Cowboy": "Cowboy Shot",
    "Medium Full": "Medium Full Shot",
    "Full": "Full Body Shot",
    "Long": "Long Shot",
    "Extreme Long": "Extreme Long Shot",
}

_ANGLE_KEYWORDS: dict[str, str] = {
    "Eye Level": "Eye Level Shot",
    "Low Angle": "Low Angle",
    "High Angle": "High Angle",
    "Top Down": "Overhead Shot, Bird's Eye View",
    "Worm's Eye": "Worm's Eye View",
}

_VIEW_KEYWORDS: dict[str, str] = {
    "Front": "Front View",
    "3/4 Front": "Three-Quarter Front View",
    "Profile": "Profile View",
    "3/4 Back": "Three-Quarter Back View",
    "Back": "Back View",
}


def _pick_view_phrase(rng: random.Random, phrases: tuple[str, ...], side: str) -> str:
    """Pick a view phrase, filling the ``{side}`` placeholder when present.

    Phrases using ``{side}`` are only sensible for views the camera sees from
    one side (three-quarter and profile framings); when *side* is empty such
    phrases are skipped in favour of plain phrasing, or the placeholder is
    neutralised to ``the camera`` when no plain phrasing exists.
    """
    if not side:
        plain = [phrase for phrase in phrases if "{side}" not in phrase]
        if plain:
            return rng.choice(plain)
    phrase = rng.choice(phrases)
    if "{side}" not in phrase:
        return phrase
    if not side:
        return phrase.replace("the {side}", "the camera").replace("{side}", "camera")
    return phrase.format(side=side)


def _compose_description(
    rng: random.Random,
    size_rec: dict[str, Any],
    angle_rec: dict[str, Any],
    view_rec: dict[str, Any],
    movement_rec: dict[str, Any],
    tilt_rec: dict[str, Any],
    side: str,
    orientation: str,
    look_rec: dict[str, Any],
) -> str:
    """Assemble the natural-language shot description from the resolved axes."""
    if angle_rec["elevation"] == 90:
        view_text = rng.choice(
            [
                "the subject seen from directly overhead",
                "the crown of the subject's head toward the lens",
            ]
        )
    else:
        view_text = _pick_view_phrase(rng, view_rec["phrases"], side)

    parts = [
        rng.choice(size_rec["phrases"]),
        rng.choice(angle_rec["phrases"]),
        view_text,
        rng.choice(movement_rec["close" if size_rec["close"] else "wide"]),
    ]
    tilt_text = rng.choice(tilt_rec["phrases"])
    if tilt_text:
        parts.append(tilt_text)

    sentence_one = ", ".join(parts) + "."

    lens = size_rec["lens"]
    depth = size_rec["depth"]
    composition = _composition_for(size_rec, orientation, angle_rec)

    return f"{sentence_one} {lens} with {depth}, {composition}. {rng.choice(look_rec['phrases'])}"


def _composition_for(size_rec: dict[str, Any], orientation: str, angle_rec: dict[str, Any]) -> str:
    """Return the composition phrase matching a shot's framing and angle."""
    if angle_rec["elevation"] == 90:
        return _COMPOSITION_TOP_DOWN[orientation]
    if size_rec["close"]:
        return _COMPOSITION_CLOSE[orientation]
    if size_rec["long"]:
        return _COMPOSITION_LONG[orientation]
    return _COMPOSITION_PHRASES[orientation]


def _compose_keywords(
    size_rec: dict[str, Any],
    angle_rec: dict[str, Any],
    view_rec: dict[str, Any],
    movement_rec: dict[str, Any],
    tilt_rec: dict[str, Any],
    look_rec: dict[str, Any],
) -> str:
    """Assemble the comma-separated keyword list for prompt injection."""
    parts: list[str] = [size_rec["keyword"], angle_rec["keyword"], view_rec["keyword"]]
    movement_keyword = movement_rec["keyword"]
    if movement_keyword:
        parts.append(movement_keyword)
    tilt_keyword = tilt_rec["keyword"]
    if tilt_keyword:
        parts.append(tilt_keyword)
    parts.append(size_rec["lens"])
    parts.append(size_rec["depth"])
    parts.append(look_rec["keywords"])
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

_AXIS_OPTIONS: dict[str, list[str]] = {
    "sizes": SHOT_SIZES,
    "angles": ANGLES,
    "views": VIEWS,
    "movements": MOVEMENTS,
    "tilts": TILTS,
    "looks": LOOKS,
}

DEFAULT_CONFIG_JSON: str = json.dumps({key: list(values) for key, values in _AXIS_OPTIONS.items()})


def parse_config(config_json: str, option_space: dict[str, dict[str, dict[str, Any]]] | None = None) -> dict[str, list[str]]:
    """Parse a Camera Config JSON string into active option lists per axis.

    Unknown keys and unknown option values are dropped; malformed JSON and
    empty per-axis lists fall back to the full option list for that axis.

    Args:
        config_json: JSON string with keys ``sizes``, ``angles``, ``views``,
            ``movements``, ``tilts``, ``looks``, each a list of option names.
        option_space: The option space to validate against (defaults to the
            built-in space).

    Returns:
        A dict mapping each axis key to its active option list.
    """
    space = option_space if option_space is not None else _builtin_space()
    try:
        raw: dict[str, Any] = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        raw = {}

    active: dict[str, list[str]] = {}
    for key, _options in _AXIS_OPTIONS.items():
        chosen = raw.get(key)
        if isinstance(chosen, list):
            valid: list[str] = []
            for option in chosen:
                if isinstance(option, str) and option in space[key] and option not in valid:
                    valid.append(option)
            if valid:
                active[key] = valid
                continue
        active[key] = list(space[key])
    return active


def axis_product(config: dict[str, list[str]]) -> int:
    """Return the number of combinations in the active option space."""
    total = 1
    for values in config.values():
        total *= len(values)
    return total


# ---------------------------------------------------------------------------
# No-repeat shuffle bag (session-scoped)
# ---------------------------------------------------------------------------


class ShotBag:
    """A seeded, session-scoped shuffle bag over all active axis combinations.

    Draws are sequential and never repeat until the deck is exhausted, at
    which point it reshuffles (with a fresh seed derived from the draw
    round) and cycles again.
    """

    def __init__(self, seed: int, config: dict[str, list[str]]) -> None:
        self._seed = seed
        self._keys: tuple[str, ...] = tuple(config)
        self._deck: list[tuple[str, ...]] = [combo for combo in product(*(config[k] for k in self._keys))]
        self._round: int = 0
        self._index: int = 0
        self._shuffle()

    def _shuffle(self) -> None:
        rng = random.Random(self._seed + self._round * 1_000_003)
        rng.shuffle(self._deck)
        self._round += 1
        self._index = 0

    def draw(self) -> dict[str, str]:
        """Return the next axis combination as an ``{axis: value}`` dict."""
        if self._index >= len(self._deck):
            self._shuffle()
        combo = self._deck[self._index]
        self._index += 1
        return dict(zip(self._keys, combo, strict=True))


# Registry keyed by (seed, config fingerprint) so the same bag is shared
# across executions for the lifetime of the process (session-scoped).
_BAGS: dict[tuple[int, str], ShotBag] = {}


def _get_bag(seed: int, config: dict[str, list[str]]) -> ShotBag:
    fingerprint = json.dumps(config, sort_keys=True)
    key = (seed, fingerprint)
    bag = _BAGS.get(key)
    if bag is None:
        bag = ShotBag(seed, config)
        _BAGS[key] = bag
    return bag


def _variant_rng(seed: int, combo: tuple[str, ...]) -> random.Random:
    """Return a deterministic per-combination RNG for prose phrasing picks."""
    digest = zlib.crc32("|".join(combo).encode("utf-8"))
    return random.Random((seed * 1_000_003) ^ digest)


# ---------------------------------------------------------------------------
# Shot builder
# ---------------------------------------------------------------------------

DETERMINISTIC_MODE: str = "Deterministic (Seed)"
FULL_AUTO_MODE: str = "Full Auto"
NO_REPEAT_MODE: str = "Random (No Repeat)"


def build_shot(
    config_json: str,
    mode: str,
    seed: int,
    width: int,
    height: int,
    wildcards_dir: str | None = None,
    option_space: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a fully coherent camera-shot object and its phrases.

    Args:
        config_json: The Camera Config JSON string (see :func:`parse_config`).
        mode: One of the three selection modes.
        seed: Seed for deterministic selection.
        width: Image width in pixels (used for the composition).
        height: Image height in pixels (used for the composition).
        wildcards_dir: Absolute path to the wildcards root directory; when
            given, the ``camera/`` tree under it supplies the option space.
        option_space: A pre-loaded option space (mainly for tests); takes
            precedence over *wildcards_dir*.

    Returns:
        The camera object dict (see the Camera node docs for the full shape).
    """
    space = option_space
    if space is None and wildcards_dir is not None:
        space = load_option_space(wildcards_dir)
    if space is None:
        space = _builtin_space()
    config = parse_config(config_json, space)

    if mode == NO_REPEAT_MODE:
        bag = _get_bag(seed, config)
        combo = bag.draw()
        combo_tuple = tuple(combo[k] for k in _AXIS_DIRS)
        rng = _variant_rng(seed, combo_tuple)
        size = combo["sizes"]
        angle = combo["angles"]
        view = combo["views"]
        movement = combo["movements"]
        tilt = combo["tilts"]
        look = combo["looks"]
    else:
        if mode == FULL_AUTO_MODE:
            config = {key: list(values) for key, values in space.items()}
        rng = random.Random(seed)
        size = rng.choice(config["sizes"])
        angle = rng.choice(config["angles"])
        view = rng.choice(config["views"])
        movement = rng.choice(config["movements"])
        tilt = rng.choice(config["tilts"])
        look = rng.choice(config["looks"])

    size_rec = space["sizes"][size]
    angle_rec = space["angles"][angle]
    view_rec = space["views"][view]
    movement_rec = space["movements"][movement]
    tilt_rec = space["tilts"][tilt]
    look_rec = space["looks"][look]

    side = rng.choice(["left", "right"]) if view_rec["azimuth"] not in (0, 180) else ""

    hidden = angle_rec["hides"] | view_rec["hides"]
    if angle_rec["elevation"] == 90:
        hidden |= _TOP_DOWN_HIDES
    fv = "face" not in hidden
    regions = [region for region in size_rec["regions"] if region not in hidden]
    orientation = _orientation(width, height)

    azimuth = view_rec["azimuth"] * (-1 if side == "left" else 1)
    elevation = angle_rec["elevation"]
    roll = tilt_rec["roll"]

    description = _compose_description(rng, size_rec, angle_rec, view_rec, movement_rec, tilt_rec, side, orientation, look_rec)
    keywords = _compose_keywords(size_rec, angle_rec, view_rec, movement_rec, tilt_rec, look_rec)
    composition = _composition_for(size_rec, orientation, angle_rec)

    return {
        "type": "camera",
        "shot_size": size,
        "angle": angle,
        "view": view,
        "movement": movement,
        "tilt": tilt,
        "look": look,
        "side": side,
        "lens": size_rec["lens"],
        "depth_of_field": size_rec["depth"],
        "orientation": orientation,
        "azimuth": azimuth,
        "elevation": elevation,
        "roll": roll,
        "face_visible": fv,
        "regions": regions,
        "composition": composition,
        "description": description,
        "keywords": keywords,
        "width": width,
        "height": height,
    }


__all__: list[str] = [
    "SHOT_SIZES",
    "ANGLES",
    "VIEWS",
    "MOVEMENTS",
    "TILTS",
    "LOOKS",
    "face_visible",
    "visible_regions",
    "parse_config",
    "axis_product",
    "ShotBag",
    "build_shot",
    "load_option_space",
    "option_shortcuts",
    "DEFAULT_CONFIG_JSON",
    "DETERMINISTIC_MODE",
    "FULL_AUTO_MODE",
    "NO_REPEAT_MODE",
]
