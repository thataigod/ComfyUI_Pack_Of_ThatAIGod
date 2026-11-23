"""Pure character engine v2 for ComfyUI_Pack_Of_ThatAIGod.

Provides :func:`build_character`, the frame-consistent character builder
consumed by the ``Character`` node.  The engine has no ComfyUI dependencies.

Pipeline (lewdity-band era — the state axis is gone):

1. **Persona** — ``wildcards/characters/<persona>/`` holds the character-
   specific descriptors (never shared): ``gender.txt``, ``measurements.txt``
   (six fit zones), ``subject_intro.txt`` (universal lines plus
   ``#@occasion:`` blocks), ``profile.txt``, ``pose.txt``, ``trigger.txt``,
   one file per visible body region, and ``lewdity.txt`` (the character's
   band, e.g. ``15-85``; a bare number means ``0-N``).
2. **Stripping** — the CAMERA object's ``regions`` decide which attribute
   files resolve; hidden regions stay empty.  Profile views substitute
   ``profile.txt`` for ``face.txt``.
3. **Wardrobe** — three source modes:
   * *Use External Wardrobe* (default): the shared common wardrobe
     (``characters/<gender>/wardrobe``, slot-decomposed, one-piece forced
     when tops/bottoms are absent), lewdity-band gated, with the persona's
     own wardrobe as the fallback.
   * *Use Internal Wardrobe*: only the persona's own curated wardrobe (no
     band — her clothes).
   * *Use Complete Wardrobe*: the common wardrobe with lewdity ignored.
   A custom persona without ``lewdity.txt`` sticks to her own wardrobe.
4. **Extras** — jewellery 30% / accessories 20% / brands 10%, capped at
   two pieces per build, drawn from the shared pools.
5. **Background** — ``locations/female_<category>_matching_locations``
   picks a location taxonomy file which resolves under the optional
   time/domain context.  The background is returned as its own string,
   never inside the description.
6. **Outputs** — the description carries the prose; ``keywords`` is the
   camera-style token list: ``Solo`` plus authored ``#@keyword:`` tokens
   from every picked attribute and garment line, plus Title Case tokens
   derived from the realized inline-tag values (the shade actually picked).
   The trigger stays a separate field.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from _wildcard_core import _DIRECTIVE_PATTERN, WildcardResolver

logger: logging.Logger = logging.getLogger("ThatAIGod")

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Every physical attribute a character can have, in canonical head-to-toe
# order (intro first).  This is the schema contract for the CHARACTER
# object's ``attributes`` key: the key set is fixed, values are "" when the
# attribute is stripped, missing from the persona, or unfilled.
_ALL_ATTRIBUTES: tuple[str, ...] = (
    "intro",
    "face",
    "hair",
    "neck",
    "shoulders",
    "back",
    "body",
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
    "profile",
    "pose",
)

# CAMERA region name → persona attribute file name.  The camera calls the
# torso "chest"; the persona files call it "body".
_REGION_TO_ATTRIBUTE: dict[str, str] = {
    "face": "face",
    "hair": "hair",
    "neck": "neck",
    "shoulders": "shoulders",
    "chest": "body",
    "back": "back",
    "breasts": "breasts",
    "navel": "navel",
    "arms": "arms",
    "hands": "hands",
    "waist": "waist",
    "hips": "hips",
    "buttocks": "buttocks",
    "thighs": "thighs",
    "legs": "legs",
    "feet": "feet",
    "skin": "skin",
}

# Every CAMERA region, in canonical order (the Camera node's region
# vocabulary).  Used when no camera object is available (no stripping).
_ALL_CAMERA_REGIONS: tuple[str, ...] = tuple(_REGION_TO_ATTRIBUTE)

# Subject resolution order (camera region order, mapped to attribute names).
_SUBJECT_ORDER: tuple[str, ...] = (
    "face",
    "hair",
    "neck",
    "shoulders",
    "body",
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
)

# Garment slots and the camera regions that make them visible.  Accessories
# are NOT a wardrobe slot any more — they arrive via the shared extras pools.
_GARMENT_SLOTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("tops", frozenset({"shoulders", "chest", "waist", "arms"})),
    ("bottoms", frozenset({"hips", "legs"})),
    ("shoes", frozenset({"feet"})),
)
_ONE_PIECE_SLOT: str = "one-piece"
_ONE_PIECE_PROBABILITY: float = 0.5

_DEFAULT_GENDER: str = "female"
_DEFAULT_PERSONA: str = "female"
_UNRESTRICTED_OCCASION: str = ""
_PROFILE_VIEW: str = "Profile"

# Camera view → pose ``#@facing`` directive vocabulary.  The camera owns the
# facing; the pose file can only ever agree with it.
_VIEW_TO_FACING: dict[str, str] = {
    "Front": "front",
    "3/4 Front": "three-quarter",
    "Profile": "profile",
    "3/4 Back": "back three-quarter",
    "Back": "back",
}

# Sentinel asserted for the ``gaze`` directive key when the face is not in
# frame: no authored gaze value can intersect it, so gaze-tagged pose lines
# are excluded from back-facing and top-down shots.
_GAZE_BLOCKED: str = "unavailable"

# ---------------------------------------------------------------------------
# Fit prose (garment ↔ body interaction)
# ---------------------------------------------------------------------------

# Persona measurement adjectives: ``measurements.txt`` declares one adjective
# per zone via directives (``#@bust: generous``); garments declare which
# zones they interact with via ``#@fit: bust, waist, hips, back, shoulders,
# thighs`` on their slot lines; the engine composes a seeded fit clause per
# visible zone.  All six zones are live.
_MEASUREMENT_ZONES: tuple[str, ...] = ("bust", "waist", "hips", "back", "shoulders", "thighs")

_DEFAULT_MEASUREMENTS: dict[str, str] = {
    "bust": "full",
    "waist": "slim",
    "hips": "curved",
    "back": "smooth",
    "shoulders": "graceful",
    "thighs": "toned",
}

# Fit zone → camera region that must be visible for the clause to appear.
_FIT_ZONE_REGIONS: dict[str, str] = {
    "bust": "breasts",
    "waist": "waist",
    "hips": "hips",
    "back": "back",
    "shoulders": "shoulders",
    "thighs": "thighs",
}

# Fit zone word per gender (a man's bust is a chest).
_FIT_ZONE_WORDS: dict[str, dict[str, str]] = {
    "female": {"bust": "bust", "waist": "waist", "hips": "hips", "back": "back", "shoulders": "shoulders", "thighs": "thighs"},
    "male": {"bust": "chest", "waist": "waist", "hips": "hips", "back": "back", "shoulders": "shoulders", "thighs": "thighs"},
}

_FIT_STYLES: dict[str, str] = {
    "snug": "fitting snugly over {pronoun} {adj} {zone}",
    "loose": "loose over {pronoun} {adj} {zone}",
    "flowing": "flowing softly over {pronoun} {adj} {zone}",
    "balanced": "fitting comfortably over {pronoun} {adj} {zone}",
}

# ---------------------------------------------------------------------------
# Lewdity band (per-character dress range, both edges binding)
# ---------------------------------------------------------------------------

# Wardrobe source modes (the node's Wardrobe Source dropdown).
WARDROBE_EXTERNAL: str = "Use External Wardrobe"
WARDROBE_INTERNAL: str = "Use Internal Wardrobe"
WARDROBE_COMPLETE: str = "Use Complete Wardrobe"
WARDROBE_MODES: tuple[str, ...] = (WARDROBE_EXTERNAL, WARDROBE_INTERNAL, WARDROBE_COMPLETE)

# Extras: one independent probability roll per pool, capped per build.
_EXTRA_PROBABILITIES: dict[str, float] = {
    "jewellery": 0.30,
    "accessories": 0.20,
    "brands": 0.10,
}
_EXTRA_CAP: int = 2

# Categories whose extras pools use a different base name than the folder.
_EXTRA_POOL_NAMES: dict[str, str] = {"sarees": "saree"}

# Category → brand deck (shared pools; unmatched categories fall back to the
# western highstreet deck).
_BRAND_DECKS: dict[str, str] = {
    "athletic": "brands/female_sport_brands",
    "swimwear": "brands/female_sport_brands",
    "micro_swimwear": "brands/female_sport_brands",
    "dancewear": "brands/female_sport_brands",
    "lingerie": "brands/female_lingerie_brands",
    "lingerie_bridal": "brands/female_lingerie_brands",
    "lingerie_latex": "brands/female_lingerie_brands",
    "lingerie_stockings": "brands/female_lingerie_brands",
    "boudoir_wear": "brands/female_lingerie_brands",
    "bdsm": "brands/female_lingerie_brands",
    "fetish_wear": "brands/female_lingerie_brands",
    "traditional": "brands/female_traditional_designers",
    "anarkali": "brands/female_traditional_designers",
    "kurti_sets": "brands/female_traditional_designers",
    "lehenga_choli": "brands/female_traditional_designers",
    "mekhela_chador": "brands/female_traditional_designers",
    "nauvari_dhoti_saree": "brands/female_traditional_designers",
    "patiala_suit": "brands/female_traditional_designers",
    "salwar_suits": "brands/female_traditional_designers",
    "sarees": "brands/female_traditional_designers",
    "sharara_gharara": "brands/female_traditional_designers",
    "formal": "brands/female_luxury_accessory_brands",
    "bridal": "brands/female_luxury_accessory_brands",
    "party": "brands/female_luxury_accessory_brands",
}
_DEFAULT_BRAND_DECK: str = "brands/female_western_highstreet"

# Outfit category → matching-locations file candidates (the outfit pool's
# naming has both shapes, e.g. female_swimwear_matching_locations and
# female_casual_outfits_matching_locations).
_MATCHING_LOCATIONS_CANDIDATES: tuple[str, ...] = (
    "locations/female_{category}_matching_locations",
    "locations/female_{category}_outfits_matching_locations",
)

# Matches a line that is exactly one __tag__ (catalog category lines).
_TAG_ONLY_PATTERN: re.Pattern[str] = re.compile(r"^__([a-zA-Z0-9_\-\/\\\\. ]+)__$")


def _safe_persona(persona: str) -> str:
    """Sanitise a persona name into a safe single folder name.

    Path separators, traversal sequences and empty names are rejected; an
    empty result falls back to :data:`_DEFAULT_PERSONA`.
    """
    cleaned = str(persona or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned or cleaned.startswith("."):
        return _DEFAULT_PERSONA
    return cleaned


def _tag_basename(line: str) -> str:
    """Return the final path segment of a tag-only line, else ``""``."""
    match = _TAG_ONLY_PATTERN.match(line.strip() if line else "")
    if match is None:
        return ""
    return match.group(1).split("/")[-1].split("\\")[-1]


def _read_gender(persona_dir: str) -> str:
    """Read the persona's ``gender.txt`` (first non-comment line)."""
    path = os.path.join(persona_dir, "gender.txt")
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                value = line.strip().lower()
                if value and not value.startswith("#"):
                    return value
    except OSError:
        pass
    return _DEFAULT_GENDER


def _parse_lewdity_value(value: str) -> tuple[int, int] | None:
    """Parse one lewdity band value: ``"15-85"`` or a bare number (``0-N``).

    The scale is open-ended above 100 for future concepts; negative values
    are clamped away.  ``None`` is returned for unparseable input.
    """
    parts = [part.strip() for part in value.replace("–", "-").split("-") if part.strip()]
    try:
        if len(parts) == 1:
            return (0, max(int(parts[0]), 0))
        if len(parts) >= 2:
            low, high = int(parts[0]), int(parts[1])
            if low > high:
                low, high = high, low
            return (max(low, 0), max(high, 0))
    except ValueError:
        return None
    return None


def _read_lewdity_file(persona_dir: str) -> tuple[int, int] | None:
    """Read the persona's ``lewdity.txt`` band (first non-comment line).

    Returns ``None`` when the file is missing or its value is unparseable.
    """
    path = os.path.join(persona_dir, "lewdity.txt")
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                value = line.strip()
                if not value or value.startswith("#"):
                    continue
                band = _parse_lewdity_value(value)
                if band is None:
                    logger.warning("Character: unparseable lewdity.txt value %r in %s; ignoring band", value, persona_dir)
                return band
    except OSError:
        return None
    return None


def _resolve_lewdity(persona_dir: str, min_override: int, max_override: int) -> tuple[int, int] | None:
    """Combine the persona's lewdity band with the node's overrides.

    ``-1`` (or any negative) override means "use the character's file".  A
    band exists when the file provides one or either override is set; a
    single-sided band opens the other edge (a max-only band starts at 0, a
    min-only band has no ceiling).
    """
    low: int | None = None
    high: int | None = None
    file_band = _read_lewdity_file(persona_dir)
    if file_band is not None:
        low, high = file_band
    if min_override is not None and min_override >= 0:
        low = int(min_override)
    if max_override is not None and max_override >= 0:
        high = int(max_override)
    if low is None and high is None:
        return None
    if low is None:
        low = 0
    if high is None:
        high = max(low, 10**6)
    if low > high:
        low, high = high, low
    return (low, high)


def _read_measurements(persona_dir: str) -> dict[str, str]:
    """Read the persona's ``measurements.txt`` zone adjectives.

    Each ``#@zone: adjective`` directive contributes one adjective; missing
    zones and a missing file fall back to :data:`_DEFAULT_MEASUREMENTS`.
    All six zones (bust, waist, hips, back, shoulders, thighs) are live.
    """
    measurements: dict[str, str] = dict(_DEFAULT_MEASUREMENTS)
    path = os.path.join(persona_dir, "measurements.txt")
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                match = _DIRECTIVE_PATTERN.match(line.strip())
                if match is not None and match.group(1) in measurements:
                    values = [part.strip() for part in match.group(2).split(",") if part.strip()]
                    if values:
                        measurements[match.group(1)] = values[0]
    except OSError:
        pass
    return measurements


def _regions_from_camera(camera: dict[str, Any] | None) -> tuple[list[str], bool, str]:
    """Extract the visible regions, face visibility and view from a CAMERA object.

    A ``None`` camera or a missing/invalid ``regions`` list means every
    region is visible (no stripping).
    """
    if not isinstance(camera, dict):
        return list(_ALL_CAMERA_REGIONS), True, "Front"
    raw = camera.get("regions")
    valid = {name for name in raw} if isinstance(raw, list) else set()
    regions = [name for name in _ALL_CAMERA_REGIONS if name in valid]
    if not regions:
        return list(_ALL_CAMERA_REGIONS), True, "Front"
    face_visible = bool(camera.get("face_visible", True))
    view = str(camera.get("view", "Front") or "Front")
    return regions, face_visible, view


def _context(occasion: str, regions: list[str]) -> dict[str, set[str]]:
    """Build the directive filter context for resolution.

    The ``occasion`` key is omitted when unrestricted so occasion-tagged
    attribute lines stay eligible only under an explicit occasion.
    """
    context: dict[str, set[str]] = {"regions": set(regions)}
    if occasion:
        context["occasion"] = {occasion}
    return context


def _pose_context(
    context: dict[str, set[str]],
    view: str,
    face_visible: bool,
) -> dict[str, set[str]]:
    """Extend the resolution context for the pose attribute.

    The camera owns facing, so the pose file's ``#@facing`` directives must
    agree with the active view; gaze-tagged pose lines are blocked whenever
    the face is out of frame (see :data:`_GAZE_BLOCKED`).
    """
    pose_context = dict(context)
    if view in _VIEW_TO_FACING:
        pose_context["facing"] = {_VIEW_TO_FACING[view]}
    if not face_visible:
        pose_context["gaze"] = {_GAZE_BLOCKED}
    return pose_context


def _tag_path(line: str) -> str:
    """Return the full tag content of a tag-only line (e.g. ``locations/x``), else ``""``."""
    stripped = line.strip()
    if stripped.startswith("__") and stripped.endswith("__") and len(stripped) > 4:
        return stripped[2:-2]
    return ""


def _split_tokens(raw: str) -> list[str]:
    """Split a raw ``#@keyword:`` value into trimmed comma-separated tokens."""
    return [token.strip() for token in raw.split(",") if token.strip()]


def _parse_keyword_directives(path: str) -> tuple[list[str], dict[str, str]]:
    """Return ``(file_default_tokens, {line_text: raw_keyword_value})``.

    Mirrors the Camera option files: a ``#@keyword:`` directive placed
    before the first content line is the file's default token list; later
    directives override the list for the next content line only (block
    semantics).  I/O errors degrade to no keywords.
    """
    default_raw = ""
    mapping: dict[str, str] = {}
    current = ""
    seen_content = False
    try:
        with open(path, encoding="utf-8-sig") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                match = _DIRECTIVE_PATTERN.match(line)
                if match is not None:
                    if match.group(1) == "keyword":
                        current = match.group(2).strip()
                        if not seen_content and not default_raw:
                            default_raw = current
                            current = ""
                    continue
                if line.startswith("#"):
                    continue
                seen_content = True
                if current and line not in mapping:
                    mapping[line] = current
                current = ""
    except OSError:
        return [], {}
    return _split_tokens(default_raw), mapping


def _tag_tokens(values: list[str]) -> list[str]:
    """Convert realized inline-tag values into Title Case prompt tokens.

    ``"Deep merlot"`` (the shade actually picked from a color deck) becomes
    ``Deep Merlot``.  Values that are empty, still contain nested tags or
    choices, or are prose-length are skipped.
    """
    tokens: list[str] = []
    for value in values:
        text = value.strip()
        if not text or "__" in text or "{" in text or "}" in text:
            continue
        lowered = text.lower()
        for article in ("a ", "an ", "the "):
            if lowered.startswith(article):
                text = text[len(article):]
                break
        text = text.rstrip(" .,;:")
        if not text or len(text) > 40:
            continue
        words = [word for word in re.split(r"\s+", text) if word]
        words = [
            "-".join(part[:1].upper() + part[1:] for part in word.split("-"))
            for word in words
        ]
        tokens.append(" ".join(words))
    return tokens


def _resolve_attribute(
    resolver: WildcardResolver,
    persona_base: str,
    attribute: str,
    context: dict[str, set[str]],
) -> tuple[str, list[str]]:
    """Resolve one persona attribute file into text plus prompt keywords.

    When the context asserts an occasion, lines tagged with a matching
    ``#@occasion:`` value win exclusively (the anti-skew contract for
    per-occasion ``subject_intro`` variants and friends); untagged lines
    serve as the fallback pool.  Keywords come from the picked line's
    ``#@keyword:`` override, else the file's top-of-file default.
    """
    file_rel = f"{persona_base}/{attribute}"
    if not resolver.file_exists(file_rel):
        return "", []
    raw, _directives = resolver.pick_line_preferred(file_rel, context, "occasion")
    if not raw:
        return "", []
    default_tokens, mapping = _parse_keyword_directives(
        os.path.join(resolver.wildcards_dir, file_rel + ".txt")
    )
    tokens = _split_tokens(mapping[raw]) if raw in mapping else default_tokens
    resolved, tag_values = resolver.resolve_with_values(raw, context)
    return resolved, list(tokens) + _tag_tokens(tag_values)


def _compose_fit(
    rng: Any,
    zones: frozenset[str],
    measurements: dict[str, str],
    visible: set[str],
    gender: str,
) -> str:
    """Compose the seeded fit clause for one garment's declared zones.

    Each declared zone whose camera region is visible gets one seeded fit
    style; the clause reads e.g. ``fitting snugly over her generous bust``.
    """
    pronoun = "his" if gender == "male" else "her"
    words = _FIT_ZONE_WORDS.get(gender, _FIT_ZONE_WORDS["female"])
    clauses: list[str] = []
    for zone in _MEASUREMENT_ZONES:
        if zone not in zones:
            continue
        if _FIT_ZONE_REGIONS.get(zone) not in visible:
            continue
        style = rng.choice(tuple(_FIT_STYLES))
        adjective = measurements.get(zone) or _DEFAULT_MEASUREMENTS.get(zone, "gentle")
        clauses.append(_FIT_STYLES[style].format(pronoun=pronoun, adj=adjective, zone=words.get(zone, zone)))
    return ", ".join(clauses)


# ---------------------------------------------------------------------------
# Wardrobe routing (catalog → category → band-gated slots)
# ---------------------------------------------------------------------------


def _catalog_occasions(resolver: WildcardResolver, wardrobe_base: str) -> set[str]:
    """Return the occasions a wardrobe's catalog declares coverage for."""
    path = os.path.join(resolver.wildcards_dir, wardrobe_base, "catalog.txt")
    values: set[str] = set()
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                match = _DIRECTIVE_PATTERN.match(line.strip())
                if match is not None and match.group(1) == "occasion":
                    values.update(v.strip().lower() for v in match.group(2).split(",") if v.strip())
    except OSError:
        return values
    return values


def _wardrobe_plan(
    resolver: WildcardResolver,
    persona_base: str,
    gender: str,
    mode: str,
    band: tuple[int, int] | None,
) -> list[tuple[str, tuple[int, int] | None]]:
    """Decide which wardrobes to try, in order, and each one's band filter.

    Each entry is ``(wardrobe_base, band_for_base)``; a ``None`` band means
    "no lewdity filtering" (the persona's own clothes are always worn as-is;
    Complete mode ignores lewdity everywhere).  The generic personas (the
    ``female``/``male`` folders) ARE the common wardrobe, so their personal
    wardrobe never appears as a separate source.
    """
    common = f"characters/{gender}/wardrobe"
    personal = f"{persona_base}/wardrobe"
    has_personal = persona_base != f"characters/{gender}" and resolver.file_exists(f"{personal}/catalog")

    if mode == WARDROBE_INTERNAL:
        if has_personal:
            return [(personal, None)]
        return [(common, band)]
    if mode == WARDROBE_COMPLETE:
        plan: list[tuple[str, tuple[int, int] | None]] = [(common, None)]
        if has_personal:
            plan.append((personal, None))
        return plan
    # External (default): the common wardrobe serves within the character's
    # band; without a band a custom persona sticks to her own clothes.
    if has_personal and band is None:
        return [(personal, None)]
    plan = [(common, band)]
    if has_personal:
        plan.append((personal, None))
    return plan


def _roll_occasion(
    resolver: WildcardResolver,
    plan: list[tuple[str, tuple[int, int] | None]],
    options: list[str],
) -> str:
    """Pick a seeded random occasion the active wardrobes can dress for.

    The candidate set is the catalog occasion coverage intersected with
    *options*; an occasion-agnostic or uncovered wardrobe stays unrestricted
    rather than rolling an occasion no category serves.
    """
    covered: set[str] = set()
    for base, _band in plan:
        covered |= _catalog_occasions(resolver, base)
    if not covered:
        return _UNRESTRICTED_OCCASION
    eligible = sorted(covered & set(options))
    if not eligible:
        return _UNRESTRICTED_OCCASION
    return resolver.rng.choice(eligible)


def _pick_category(resolver: WildcardResolver, wardrobe_base: str, context: dict[str, set[str]]) -> str:
    """Pick a wardrobe category eligible under the context via its catalog.

    The catalog's ``#@occasion:`` headers filter its tag lines against the
    active occasion.  When nothing routes for the occasion the catalog is
    retried unrestricted (with a warning) so a routing miss never leaves the
    character undressed.
    """
    line, _directives = resolver.pick_line_with_directives(f"{wardrobe_base}/catalog", context)
    category = _tag_basename(line)
    if category:
        return category
    occasion = next(iter(context.get("occasion", ())), None)
    if occasion:
        line, _directives = resolver.pick_line_with_directives(f"{wardrobe_base}/catalog", None)
        category = _tag_basename(line)
        if category:
            logger.warning(
                "Character: no category in %s covers occasion %r; falling back to %r",
                wardrobe_base,
                occasion,
                category,
            )
    return category


def _resolve_slot(
    resolver: WildcardResolver,
    context: dict[str, set[str]],
    slot_base: str,
    slot: str,
    band: tuple[int, int] | None,
) -> tuple[str, dict[str, set[str]], list[str]]:
    """Resolve one garment slot to a piece, its directives and its keywords.

    A set *band* filters candidate lines by their lewdity rating (per-line
    override, else the file's top-of-file default, else 0); ``None`` picks
    without lewdity filtering.  Inline ``__colors/...__`` tags expand after
    the pick.  Keywords are the picked line's ``#@keyword:`` override, else
    the file's top-of-file default, plus Title Case tokens derived from the
    realized inline-tag values (the shade actually picked, not the deck name).
    """
    if not resolver.file_exists(f"{slot_base}/{slot}"):
        return "", {}, []
    if band is None:
        raw, directives = resolver.pick_line_with_directives(f"{slot_base}/{slot}", context)
    else:
        raw, directives = resolver.pick_line_in_band(f"{slot_base}/{slot}", context, band[0], band[1])
    if not raw:
        return "", {}, []
    default_tokens, mapping = _parse_keyword_directives(
        os.path.join(resolver.wildcards_dir, f"{slot_base}/{slot}.txt")
    )
    tokens = _split_tokens(mapping[raw]) if raw in mapping else list(default_tokens)
    piece, tag_values = resolver.resolve_with_values(raw, context)
    tokens.extend(_tag_tokens(tag_values))
    return piece, directives, tokens


def _fill_slots(
    resolver: WildcardResolver,
    context: dict[str, set[str]],
    wardrobe_base: str,
    category: str,
    regions: list[str],
    band: tuple[int, int] | None,
) -> tuple[list[str], list[dict[str, set[str]]], list[str]]:
    """Fill the visible garment slots for a wardrobe category.

    A ``one-piece`` file substitutes for tops + bottoms: with probability
    :data:`_ONE_PIECE_PROBABILITY` when the category also has separates, or
    forced when tops/bottoms are absent (dresses, nude-family categories).
    Slots whose regions are not visible are skipped.  Returns the resolved
    pieces, their accumulated directives, and their accumulated keyword
    tokens, in piece order.
    """
    pieces: list[str] = []
    piece_directives: list[dict[str, set[str]]] = []
    piece_keywords: list[str] = []
    region_set = set(regions)
    slot_base = f"{wardrobe_base}/{category}"
    has_tops = resolver.file_exists(f"{slot_base}/tops")
    has_bottoms = resolver.file_exists(f"{slot_base}/bottoms")
    has_one_piece = resolver.file_exists(f"{slot_base}/{_ONE_PIECE_SLOT}")

    use_one_piece = False
    if has_one_piece:
        use_one_piece = not (has_tops and has_bottoms) or resolver.rng.random() < _ONE_PIECE_PROBABILITY
    if use_one_piece:
        piece, directives, tokens = _resolve_slot(
            resolver, context, slot_base, _ONE_PIECE_SLOT, band
        )
        if piece:
            pieces.append(piece)
            piece_directives.append(directives)
            piece_keywords.extend(tokens)
    for slot, required in _GARMENT_SLOTS:
        if use_one_piece and slot in ("tops", "bottoms"):
            continue
        if not (required & region_set):
            continue
        piece, directives, tokens = _resolve_slot(resolver, context, slot_base, slot, band)
        if piece:
            pieces.append(piece)
            piece_directives.append(directives)
            piece_keywords.extend(tokens)
    return pieces, piece_directives, piece_keywords


def _roll_extras(resolver: WildcardResolver, category: str) -> list[str]:
    """Roll the minimal extras for one outfit category.

    Jewellery 30% / accessories 20% / brands 10%, each an independent roll
    against its shared pool, capped at :data:`_EXTRA_CAP` pieces per build.
    Missing pools are skipped silently (not every category has all three).
    """
    if not category:
        return []
    pool_name = _EXTRA_POOL_NAMES.get(category, category)
    rolls: tuple[tuple[str, float], ...] = (
        (f"jewellery/female_{pool_name}_jewellery", _EXTRA_PROBABILITIES["jewellery"]),
        (f"accessories/female_{pool_name}_accessories", _EXTRA_PROBABILITIES["accessories"]),
        (_BRAND_DECKS.get(category, _DEFAULT_BRAND_DECK), _EXTRA_PROBABILITIES["brands"]),
    )
    extras: list[str] = []
    for deck, probability in rolls:
        if len(extras) >= _EXTRA_CAP:
            break
        if resolver.rng.random() >= probability:
            continue
        if not resolver.file_exists(deck):
            continue
        piece = resolver.pick_line(deck, None)
        if piece:
            extras.append(piece)
    return extras


def _background(resolver: WildcardResolver, category: str, time_of_day: str, domain: str) -> str:
    """Resolve the background for an outfit category via matching locations.

    The matching-locations file picks one location taxonomy tag, which then
    resolves under the optional domain context.  When a time filter is set
    the taxonomy's time-tagged lines win over its universal lines (a night
    request must not coin-flip into a noon description).  Categories
    without a matching file yield ``""`` with a warning — never a random
    location walk.
    """
    if not category:
        return ""
    domain_context: dict[str, set[str]] | None = {"domain": {domain}} if domain else None
    for template in _MATCHING_LOCATIONS_CANDIDATES:
        rel = template.format(category=category)
        if not resolver.file_exists(rel):
            continue
        tag_line = resolver.pick_line(rel, None)
        if not tag_line:
            return ""
        tag = _tag_path(tag_line)
        if not tag:
            return ""
        if time_of_day:
            context = dict(domain_context or {})
            context["time"] = {time_of_day}
            line, _directives = resolver.pick_line_preferred(tag, context, "time")
            return line.strip()
        return resolver.resolve(tag_line, domain_context).strip()
    logger.warning("Character: no matching-locations file for outfit category %r; background left empty", category)
    return ""


def _dedupe(items: list[str]) -> list[str]:
    """Return *items* with duplicates removed, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_character(
    wildcards_dir: str,
    persona: str,
    camera: dict[str, Any] | None,
    occasion: str,
    wardrobe_mode: str,
    mode: str,
    seed: int,
    resolver: WildcardResolver | None = None,
    occasion_options: list[str] | None = None,
    lewdity_min: int = -1,
    lewdity_max: int = -1,
    time_of_day: str = "",
    domain: str = "",
) -> dict[str, Any]:
    """Build a frame-consistent CHARACTER object for a persona.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        persona: The persona folder name under ``wildcards/characters/``.
        camera: The CAMERA object dict from the Camera node (``None`` = no
            stripping, all regions visible).
        occasion: Active occasion value (``""`` = roll/auto).
        wardrobe_mode: One of :data:`WARDROBE_MODES`.
        mode: Wildcard selection mode (``"Deterministic (Seed)"`` or
            ``"Random (No Repeat)"``).
        seed: Seed for deterministic selection.
        resolver: Optional pre-built resolver (mainly for tests).
        occasion_options: Occasion choices; when *occasion* is unrestricted
            and this is provided, a seeded random occasion is rolled from
            the active wardrobes' catalog coverage.
        lewdity_min: Node override for the band's lower edge (``-1`` = use
            the persona's ``lewdity.txt``).
        lewdity_max: Node override for the band's upper edge (``-1`` = use
            the persona's ``lewdity.txt``).
        time_of_day: Optional time filter for the background (``""`` = any).
        domain: Optional location-domain filter for the background
            (``""`` = any).

    Returns:
        The CHARACTER object dict (see the Character node docs for the
        shape), including the ``background`` string as its own field.
    """
    persona = _safe_persona(persona)
    persona_base = f"characters/{persona}"
    persona_dir = os.path.join(wildcards_dir, "characters", persona)

    if resolver is None:
        resolver = WildcardResolver(wildcards_dir, mode=mode, seed=seed)

    gender = _read_gender(persona_dir)
    band = _resolve_lewdity(persona_dir, lewdity_min, lewdity_max)
    plan = _wardrobe_plan(resolver, persona_base, gender, wardrobe_mode, band)

    if occasion == "" and occasion_options:
        occasion = _roll_occasion(resolver, plan, occasion_options)

    regions, face_visible, view = _regions_from_camera(camera)
    context = _context(occasion, regions)

    # Pick the outfit: the first wardrobe in the plan that routes a
    # category AND yields at least one visible piece wins.  A category with
    # no visible slots (e.g. a face close-up hides every garment region) is
    # a normal camera outcome, not a failure.
    outfit_category = ""
    outfit_base = ""
    outfit_pieces: list[str] = []
    piece_directives: list[dict[str, set[str]]] = []
    outfit_keywords: list[str] = []
    category_routed = False
    for base, base_band in plan:
        category = _pick_category(resolver, base, context)
        if not category:
            continue
        category_routed = True
        pieces, directives, keywords_found = _fill_slots(
            resolver, context, base, category, regions, base_band
        )
        if not pieces:
            continue
        outfit_category = category
        outfit_base = base
        outfit_pieces = pieces
        piece_directives = list(directives)
        outfit_keywords = list(keywords_found)
        break
    if not category_routed:
        logger.warning(
            "Character: no wardrobe category routed for persona %r (mode %r, occasion %r)",
            persona,
            wardrobe_mode,
            occasion,
        )
    if outfit_category:
        context = dict(context)
        context["outfit"] = {outfit_category}

    attributes: dict[str, str] = {key: "" for key in _ALL_ATTRIBUTES}
    attributes["intro"], intro_keywords = _resolve_attribute(
        resolver, persona_base, "subject_intro", context
    )

    attribute_keywords: list[str] = []
    face_attribute = "profile" if view == _PROFILE_VIEW else "face"
    for region in regions:
        attribute = _REGION_TO_ATTRIBUTE[region]
        if attribute == "face":
            attribute = face_attribute
        attributes[attribute], tokens = _resolve_attribute(
            resolver, persona_base, attribute, context
        )
        attribute_keywords.extend(tokens)

    pose, pose_keywords = _resolve_attribute(
        resolver, persona_base, "pose", _pose_context(context, view, face_visible)
    )
    if not pose:
        # Graceful degradation: a persona with no pose line for this facing
        # still gets a pose rather than none.  The gaze block stays asserted
        # so face-hidden shots never degrade into "meeting the camera".
        fallback_context = dict(context)
        if not face_visible:
            fallback_context["gaze"] = {_GAZE_BLOCKED}
        pose, pose_keywords = _resolve_attribute(
            resolver, persona_base, "pose", fallback_context
        )
    attributes["pose"] = pose

    # Identity trigger phrase (e.g. a Lora trigger token).  Resolved as a
    # plain seeded pick, carried on the object only — never part of the
    # description or keywords, so downstream nodes can extract it explicitly.
    trigger = resolver.pick_line(f"{persona_base}/trigger", None)

    measurements = _read_measurements(persona_dir)
    visible = set(regions)
    outfit_parts: list[str] = []
    for piece, piece_directive in zip(outfit_pieces, piece_directives, strict=False):
        fit_zones = frozenset(piece_directive.get("fit", ()))
        fit_clause = _compose_fit(resolver.rng, fit_zones, measurements, visible, gender)
        outfit_parts.append(f"{piece}, {fit_clause}" if fit_clause else piece)
    outfit_parts.extend(_roll_extras(resolver, outfit_category))

    background = _background(resolver, outfit_category, time_of_day, domain)
    outfit = ", ".join(outfit_parts)

    subject_order = [face_attribute if key == "face" else key for key in _SUBJECT_ORDER]
    subject_parts = [attributes["intro"]] + [attributes[key] for key in subject_order]
    subject = ", ".join(part for part in subject_parts if part)

    description_parts = [part for part in (subject, pose, outfit) if part]
    description = ", ".join(description_parts)

    # Keywords are camera-style prompt tokens, not prose: the description
    # already carries the natural-language content, so Keywords contributes
    # the authored ``#@keyword:`` tokens of every picked attribute and
    # garment line, the inline color/pattern tokens, and a leading ``Solo``.
    # The trigger stays a separate output so it can be placed deliberately.
    keyword_parts = _dedupe(
        [
            "Solo",
            *intro_keywords,
            *attribute_keywords,
            *pose_keywords,
            *outfit_keywords,
        ]
    )
    keywords = ", ".join(keyword_parts)

    return {
        "type": "character",
        "persona": persona,
        "trigger": trigger,
        "occasion": occasion,
        "wardrobe_mode": wardrobe_mode,
        "wardrobe_base": outfit_base,
        "lewdity": band,
        "regions": regions,
        "face_visible": face_visible,
        "attributes": attributes,
        "pose": pose,
        "outfit_category": outfit_category,
        "outfit": outfit,
        "background": background,
        "subject": subject,
        "description": description,
        "keywords": keywords,
    }


__all__: list[str] = [
    "WARDROBE_EXTERNAL",
    "WARDROBE_INTERNAL",
    "WARDROBE_COMPLETE",
    "WARDROBE_MODES",
    "_ALL_ATTRIBUTES",
    "_ALL_CAMERA_REGIONS",
    "_REGION_TO_ATTRIBUTE",
    "_SUBJECT_ORDER",
    "_GARMENT_SLOTS",
    "_MEASUREMENT_ZONES",
    "_EXTRA_PROBABILITIES",
    "_EXTRA_CAP",
    "build_character",
    "_safe_persona",
    "_read_gender",
    "_parse_lewdity_value",
    "_read_lewdity_file",
    "_resolve_lewdity",
    "_read_measurements",
    "_tag_basename",
    "_tag_path",
    "_split_tokens",
    "_parse_keyword_directives",
    "_tag_tokens",
    "_regions_from_camera",
    "_context",
    "_compose_fit",
    "_catalog_occasions",
    "_wardrobe_plan",
    "_roll_occasion",
    "_pick_category",
    "_resolve_slot",
    "_fill_slots",
    "_roll_extras",
    "_background",
]
