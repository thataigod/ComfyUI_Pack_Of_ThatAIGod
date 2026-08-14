"""Pure character engine for ComfyUI_Pack_Of_ThatAIGod.

Provides :func:`build_character`, the frame-consistent character builder
consumed by the ``Character`` node.  The engine has no ComfyUI dependencies.

Pipeline:

1. **Persona** — a folder under ``wildcards/characters/<persona>/`` holding
   one file per physical attribute (``face``, ``hair``, ``body``, ...), plus
   optional ``subject_intro.txt``, ``pose.txt``, ``profile.txt``,
   ``gender.txt`` and a per-persona ``wardrobe/``.
2. **Stripping** — the CAMERA object's ``regions`` decide which attribute
   files are resolved; hidden regions stay empty.  Profile views substitute
   ``profile.txt`` for ``face.txt``.
3. **Pose** — ``pose.txt`` supplies body pose only; it never decides facing
   (the camera view does).
4. **Wardrobe** — the persona's own ``wardrobe/`` catalog is preferred; when
   allowed (and the persona has none, or lacks an eligible category) the
   common wardrobe ``wildcards/wardrobe/<gender>/`` is consulted, with the
   gender read from the persona's ``gender.txt`` (default ``"female"``).
   Garment slots are filled only for visible regions, and persona pieces
   without inline wildcard tags may receive a shared garment-style modifier.
"""

from __future__ import annotations

import os
import random
import re
from typing import Any

from _wildcard_core import _DIRECTIVE_PATTERN, WildcardResolver

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

# Garment slots and the camera regions that make them visible.
_GARMENT_SLOTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("tops", frozenset({"shoulders", "chest", "waist", "arms"})),
    ("bottoms", frozenset({"hips", "legs"})),
    ("shoes", frozenset({"feet"})),
    ("accessories", frozenset({"face", "neck", "arms", "hands"})),
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
# (``#@gaze: into the lens`` and friends) are excluded from back-facing and
# top-down shots.  When the face is visible the key is not asserted at all,
# so every authored gaze value stays eligible.
_GAZE_BLOCKED: str = "unavailable"

# ---------------------------------------------------------------------------
# Fit prose (garment ↔ body interaction)
# ---------------------------------------------------------------------------

# Persona measurement adjectives: ``measurements.txt`` declares one adjective
# per body zone via directives (``#@bust: generous``); garments declare which
# zones they interact with via ``#@fit: bust, waist, hips`` on their slot
# lines; the engine composes a seeded fit clause per visible zone.
_MEASUREMENT_ZONES: tuple[str, ...] = ("bust", "waist", "hips")

_DEFAULT_MEASUREMENTS: dict[str, str] = {
    "bust": "full",
    "waist": "slim",
    "hips": "curved",
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

_NUDE_STATE: str = "nude"

# State axis: seeded weighted roll when left on Auto.  The occasion gates the
# odds — intimate/boudoir welcome undress, professional settings forbid it.
_STATE_VALUES: tuple[str, ...] = ("dressed", "revealing", "mishap", "slipping", "nude")
_STATE_WEIGHTS_DEFAULT: dict[str, int] = {"dressed": 70, "revealing": 12, "mishap": 8, "slipping": 5, "nude": 5}
_STATE_WEIGHTS_INTIMATE: dict[str, int] = {"dressed": 30, "revealing": 20, "mishap": 15, "slipping": 15, "nude": 20}
_STATE_WEIGHTS_PROFESSIONAL: dict[str, int] = {"dressed": 95, "revealing": 3, "mishap": 2, "slipping": 0, "nude": 0}
_INTIMATE_OCCASIONS: frozenset[str] = frozenset({"intimate", "boudoir"})
_PROFESSIONAL_OCCASIONS: frozenset[str] = frozenset({"office", "formal", "wedding"})

# Per-garment condition (wet/sweaty/clinging) roll probability.
_CONDITION_PROBABILITY: float = 0.25

# Matches a line that is exactly one __tag__ (wardrobe catalog category lines).
_TAG_ONLY_PATTERN: re.Pattern[str] = re.compile(r"^__([a-zA-Z0-9_\-\/\\\\. ]+)__$")


def _safe_persona(persona: str) -> str:
    """Sanitise a persona name into a safe single folder name.

    Path separators, traversal sequences and empty names are rejected; an
    empty result falls back to :data:`_DEFAULT_PERSONA`.

    Args:
        persona: The raw persona name.

    Returns:
        A safe folder name under ``wildcards/characters/``.
    """
    cleaned = str(persona or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned or cleaned.startswith("."):
        return _DEFAULT_PERSONA
    return cleaned


def _tag_basename(line: str) -> str:
    """Return the final path segment of a tag-only line, else ``""``.

    Args:
        line: A wardrobe catalog line.

    Returns:
        The category name (e.g. ``"signature"`` from
        ``__characters/Rohini Smirnova/wardrobe/signature__``), or ``""``
        when the line is not a pure tag.
    """
    match = _TAG_ONLY_PATTERN.match(line.strip() if line else "")
    if match is None:
        return ""
    return match.group(1).split("/")[-1].split("\\")[-1]


def _read_gender(persona_dir: str) -> str:
    """Read the persona's ``gender.txt`` (first non-comment line).

    Args:
        persona_dir: Absolute path to the persona folder.

    Returns:
        The lowercase gender token, defaulting to :data:`_DEFAULT_GENDER`.
    """
    path = os.path.join(persona_dir, "gender.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                value = line.strip().lower()
                if value and not value.startswith("#"):
                    return value
    except OSError:
        pass
    return _DEFAULT_GENDER


def _regions_from_camera(camera: dict[str, Any] | None) -> tuple[list[str], bool, str]:
    """Extract the visible regions, face visibility and view from a CAMERA object.

    A ``None`` camera or a missing/invalid ``regions`` list means every
    region is visible (no stripping).

    Args:
        camera: The CAMERA object dict from the Camera node, or ``None``.

    Returns:
        A ``(regions, face_visible, view)`` tuple with the regions ordered as
        in :data:`_ALL_CAMERA_REGIONS`.
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

    Args:
        occasion: Active occasion value, or :data:`_UNRESTRICTED_OCCASION`.
        regions: The visible camera regions.

    Returns:
        A context dict; the ``occasion`` key is omitted when unrestricted.
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

    Args:
        context: The base resolution context.
        view: The camera view axis value (``""`` = no constraint).
        face_visible: Whether the camera can see the subject's face.

    Returns:
        A copy of *context* with ``facing`` and optionally ``gaze`` asserted.
    """
    pose_context = dict(context)
    if view in _VIEW_TO_FACING:
        pose_context["facing"] = {_VIEW_TO_FACING[view]}
    if not face_visible:
        pose_context["gaze"] = {_GAZE_BLOCKED}
    return pose_context


def _resolve_attribute(
    resolver: WildcardResolver,
    persona_base: str,
    attribute: str,
    context: dict[str, set[str]],
) -> str:
    """Resolve one persona attribute file to a string (or ``""``).

    Args:
        resolver: The section resolver.
        persona_base: ``characters/<persona>`` relative path.
        attribute: Attribute file name without extension.
        context: The active filter context.

    Returns:
        The resolved, expanded text, or ``""`` when the file is missing or
        resolves empty.
    """
    if not resolver.file_exists(f"{persona_base}/{attribute}"):
        return ""
    return resolver.resolve(f"__{persona_base}/{attribute}__", context)


def _read_measurements(persona_dir: str) -> dict[str, str]:
    """Read the persona's ``measurements.txt`` zone adjectives.

    Each ``#@zone: adjective`` directive contributes one adjective; missing
    zones and a missing file fall back to :data:`_DEFAULT_MEASUREMENTS`.

    Args:
        persona_dir: Absolute path to the persona folder.

    Returns:
        A zone → adjective mapping for every measurement zone.
    """
    measurements: dict[str, str] = dict(_DEFAULT_MEASUREMENTS)
    path = os.path.join(persona_dir, "measurements.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = _DIRECTIVE_PATTERN.match(line.strip())
                if match is not None and match.group(1) in measurements:
                    values = [part.strip() for part in match.group(2).split(",") if part.strip()]
                    if values:
                        measurements[match.group(1)] = values[0]
    except OSError:
        pass
    return measurements


def _compose_fit(
    rng: random.Random,
    zones: frozenset[str],
    measurements: dict[str, str],
    visible: set[str],
    gender: str,
) -> str:
    """Compose the seeded fit clause for one garment's declared zones.

    Each declared zone whose camera region is visible gets one seeded fit
    style; the clause reads e.g. ``fitting snugly over her generous bust``.

    Args:
        rng: The resolver's RNG (draws happen after all resolution).
        zones: The garment's declared ``#@fit`` zones.
        measurements: The persona's zone adjectives.
        visible: The visible camera regions.
        gender: The persona's gender (pronoun + zone wording).

    Returns:
        The comma-joined fit clauses, or ``""`` when nothing applies.
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


def _resolve_nude(resolver: WildcardResolver, persona_base: str, context: dict[str, set[str]]) -> str:
    """Resolve the persona's region-tagged ``nude.txt`` (one pick per block).

    Args:
        resolver: The section resolver.
        persona_base: ``characters/<persona>`` relative path.
        context: The active filter context (regions gate each block).

    Returns:
        The joined block picks, or ``""`` when the file is missing.
    """
    if not resolver.file_exists(f"{persona_base}/nude"):
        return ""
    return resolver.pick_line_per_block(f"{persona_base}/nude", context)


def _resolve_state(
    rng: random.Random,
    state: str,
    state_options: list[str] | None,
    occasion: str,
) -> str:
    """Resolve the state axis to a concrete state value.

    ``""``/``"auto"`` rolls the seeded occasion-weighted table, or uniformly
    within *state_options* when a proper subset was selected.

    Args:
        rng: The resolver's RNG.
        state: The requested state (``""``/``"auto"`` = roll).
        state_options: Explicit subset to roll within (or ``None``).
        occasion: The active occasion (gates the Auto weights).

    Returns:
        One of :data:`_STATE_VALUES`.
    """
    if state not in ("", "auto") and state in _STATE_VALUES:
        return state
    if state_options:
        return rng.choice(state_options)
    if occasion in _INTIMATE_OCCASIONS:
        table = _STATE_WEIGHTS_INTIMATE
    elif occasion in _PROFESSIONAL_OCCASIONS:
        table = _STATE_WEIGHTS_PROFESSIONAL
    else:
        table = _STATE_WEIGHTS_DEFAULT
    values = tuple(table)
    return rng.choices(values, weights=tuple(table[value] for value in values), k=1)[0]


def _pick_state_phrase(
    resolver: WildcardResolver,
    piece_directives: list[dict[str, set[str]]],
    key: str,
    context: dict[str, set[str]],
) -> str:
    """Pick a garment's own ``#@key`` phrase, else the generic state deck.

    Args:
        resolver: The section resolver.
        piece_directives: Per-piece accumulated directives in piece order.
        key: The directive key (``"mishap"`` or ``"slip"``).
        context: The active filter context (for the fallback deck).

    Returns:
        The phrase, or ``""`` when nothing is available.
    """
    for directives in piece_directives:
        values = directives.get(key)
        if values:
            return resolver.rng.choice(tuple(sorted(values)))
    return resolver.pick_line(f"shared/state-{key}", context)


def _compose_state_clauses(
    resolver: WildcardResolver,
    state: str,
    piece_directives: list[dict[str, set[str]]],
    context: dict[str, set[str]],
) -> list[str]:
    """Compose the state clauses that ride on the outfit (revealing, mishap,
    slipping, and per-garment conditions).

    Args:
        resolver: The section resolver.
        state: The resolved state value.
        piece_directives: Per-piece accumulated directives in piece order.
        context: The active filter context.

    Returns:
        The clause list (possibly empty), appended after the outfit.
    """
    clauses: list[str] = []
    if state == "revealing":
        clause = resolver.pick_line("shared/state-revealing", context)
        if clause:
            clauses.append(clause)
    elif state == "mishap":
        phrase = _pick_state_phrase(resolver, piece_directives, "mishap", context)
        if phrase:
            clauses.append(f"with {phrase}")
    elif state == "slipping":
        phrase = _pick_state_phrase(resolver, piece_directives, "slip", context)
        if phrase:
            clauses.append(f"with {phrase}")
    for directives in piece_directives:
        conditions = directives.get("condition")
        if not conditions:
            continue
        if resolver.rng.random() >= _CONDITION_PROBABILITY:
            continue
        condition = resolver.rng.choice(tuple(sorted(conditions)))
        condition_context = dict(context)
        condition_context["condition"] = {condition}
        clause = resolver.pick_line("shared/state-condition", condition_context)
        if clause:
            clauses.append(clause)
    return clauses


def _wardrobe_base(resolver: WildcardResolver, persona_base: str, gender: str, use_common_wardrobe: bool) -> str | None:
    """Decide which wardrobe root to use for the persona.

    The persona's own ``wardrobe/`` wins when it has a catalog; otherwise the
    default wardrobe of the matching default persona
    (``characters/<gender>/wardrobe``) is used only when allowed.

    Args:
        resolver: The section resolver (used for existence checks).
        persona_base: ``characters/<persona>`` relative path.
        gender: The persona's gender (default wardrobe lookup).
        use_common_wardrobe: Whether default wardrobe access is allowed.

    Returns:
        The wardrobe base relative path, or ``None`` when no wardrobe applies.
    """
    if resolver.file_exists(f"{persona_base}/wardrobe/catalog"):
        return f"{persona_base}/wardrobe"
    if use_common_wardrobe:
        return f"characters/{gender}/wardrobe"
    return None


def _occasion_headers(path: str) -> set[str]:
    """Return the occasions declared by a category file's ``#@occasion`` headers.

    Args:
        path: Absolute path to the wildcard category file.

    Returns:
        The lowercase occasion values, possibly empty.
    """
    values: set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = _DIRECTIVE_PATTERN.match(line.strip())
                if match is not None and match.group(1) == "occasion":
                    values.update(v.strip().lower() for v in match.group(2).split(","))
    except OSError:
        return set()
    return values


def _occasion_coverage(wildcards_dir: str, wardrobe_base: str | None) -> set[str] | None:
    """Return the occasions the wardrobe's category files declare coverage for.

    Two wardrobe shapes are recognised:

    * **Common wardrobe** — flat ``<category>.txt`` files directly under the
      root; the category file is the occasion carrier and its slot folders
      inherit the category's occasion, so only the root files are scanned.
    * **Persona wardrobe** — category folders under the root; the folder tag
      cannot be deep-filtered, so occasion filtering happens in the garment
      slot files, which are scanned recursively.

    ``catalog.txt`` is an index, not a garment source, and is skipped.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        wardrobe_base: The wardrobe root relative path (``None`` = no wardrobe).

    Returns:
        The set of covered occasions, or ``None`` when the wardrobe is
        occasion-agnostic (no wardrobe, or any garment source without
        ``#@occasion`` headers) — a roll is then meaningless because the
        outfit cannot change with the occasion.
    """
    if wardrobe_base is None:
        return None
    root = os.path.join(wildcards_dir, wardrobe_base)
    try:
        names = os.listdir(root)
    except OSError:
        return None
    covered: set[str] = set()
    untagged_source = False
    flat_files = sorted(name for name in names if name.endswith(".txt") and name != "catalog.txt")

    def visit(directory: str) -> None:
        nonlocal covered, untagged_source
        try:
            entries = os.listdir(directory)
        except OSError:
            untagged_source = True
            return
        for entry in entries:
            if entry == "catalog.txt":
                continue
            path = os.path.join(directory, entry)
            if os.path.isdir(path):
                visit(path)
            elif entry.endswith(".txt"):
                values = _occasion_headers(path)
                if values:
                    covered |= values
                else:
                    untagged_source = True

    if flat_files:
        for name in flat_files:
            values = _occasion_headers(os.path.join(root, name))
            if values:
                covered |= values
            else:
                untagged_source = True
    else:
        for name in names:
            path = os.path.join(root, name)
            if os.path.isdir(path):
                visit(path)
    if untagged_source or not covered:
        return None
    return covered


def _roll_occasion(
    resolver: WildcardResolver,
    wildcards_dir: str,
    wardrobe_base: str | None,
    options: list[str],
) -> str:
    """Pick a seeded random occasion the wardrobe can actually dress for.

    The candidate set is the wardrobe's covered occasions intersected with
    *options*.  Returns :data:`_UNRESTRICTED_OCCASION` when the wardrobe is
    occasion-agnostic (no coverage) or when nothing covered is in *options*
    — the character stays undressed-by-occasion rather than rolling an
    occasion no garment can match.

    Args:
        resolver: The section resolver (its RNG draws the pick).
        wildcards_dir: Absolute path to the wildcards root directory.
        wardrobe_base: The wardrobe root relative path (``None`` = no wardrobe).
        options: The occasion choices (``shared/occasions.txt`` lines).

    Returns:
        The chosen occasion, or ``""`` when nothing is usable.
    """
    coverage = _occasion_coverage(wildcards_dir, wardrobe_base)
    if coverage is None:
        return _UNRESTRICTED_OCCASION
    eligible = sorted(coverage & set(options))
    if not eligible:
        return _UNRESTRICTED_OCCASION
    return resolver.rng.choice(eligible)


def _pick_category(resolver: WildcardResolver, wardrobe_base: str, context: dict[str, set[str]]) -> str:
    """Pick a wardrobe category eligible under the context.

    The catalog's tag-only lines are deep-filtered by the resolver (an
    occasion-restricted category never appears under a conflicting occasion).
    Falls back to a random eligible category file when the catalog yields no
    tag.

    Args:
        resolver: The section resolver.
        wardrobe_base: The wardrobe root relative path.
        context: The active filter context.

    Returns:
        The category folder name, or ``""`` when nothing is eligible.
    """
    catalog_line = resolver.pick_line(f"{wardrobe_base}/catalog", context)
    category = _tag_basename(catalog_line)
    if category:
        return category
    picked = resolver.pick_file(wardrobe_base, context, exclude={"catalog.txt"})
    if picked is None:
        return ""
    return os.path.basename(picked[0])


def _fill_slots(
    resolver: WildcardResolver,
    context: dict[str, set[str]],
    wardrobe_base: str,
    category: str,
    regions: list[str],
    use_shared_modifiers: bool,
    piece_directives: list[dict[str, set[str]]] | None = None,
) -> list[str]:
    """Fill the visible garment slots for a wardrobe category.

    A category-level ``one-piece`` file substitutes for tops + bottoms with
    probability :data:`_ONE_PIECE_PROBABILITY`.  Slots whose regions are not
    visible are skipped (e.g. bottoms vanish when the legs are stripped).
    Garment slots (tops, bottoms, one-piece — not shoes or accessories) whose
    pieces carry no inline wildcard tags receive a shared garment-style
    modifier when enabled.  When *piece_directives* is given, each piece's
    accumulated directives are appended to it in piece order (used by
    :func:`build_character` for fit/state prose; ``None`` keeps the
    historical string-list behaviour).

    Args:
        resolver: The section resolver (shares its RNG with the category pick).
        context: The active filter context.
        wardrobe_base: The wardrobe root relative path.
        category: The category folder name.
        regions: The visible camera regions.
        use_shared_modifiers: Whether to append shared garment-style phrases.
        piece_directives: Optional collector for each piece's directives.

    Returns:
        The resolved garment pieces (possibly empty).
    """
    pieces: list[str] = []
    region_set = set(regions)
    slot_base = f"{wardrobe_base}/{category}"
    if piece_directives is not None:
        piece_directives.clear()
    category_modifiers = _category_modifiers(resolver, wardrobe_base, category)

    use_one_piece = resolver.file_exists(f"{slot_base}/{_ONE_PIECE_SLOT}") and resolver.rng.random() < _ONE_PIECE_PROBABILITY
    active_slots = list(_GARMENT_SLOTS)
    if use_one_piece:
        piece, directives = _resolve_slot(resolver, context, slot_base, _ONE_PIECE_SLOT, use_shared_modifiers, category_modifiers)
        if piece:
            pieces.append(piece)
            if piece_directives is not None:
                piece_directives.append(directives)
        active_slots = [slot for slot in active_slots if slot[0] in ("shoes", "accessories")]
    for slot, required in active_slots:
        if not (required & region_set):
            continue
        piece, directives = _resolve_slot(resolver, context, slot_base, slot, use_shared_modifiers, category_modifiers)
        if piece:
            pieces.append(piece)
            if piece_directives is not None:
                piece_directives.append(directives)
    return pieces


_MODIFIER_SLOTS: frozenset[str] = frozenset({"tops", "bottoms", _ONE_PIECE_SLOT})

# The append-phrase modifier dimensions applied to tagless garments, in
# default prose order.  Categories may narrow the list via a #@modifiers
# directive on their category file; garments may override (#@modifiers:),
# subtract (#@no_modifiers:) or opt out entirely (#@fixed: true).
_MODIFIER_DIMENSIONS: tuple[str, ...] = ("color", "pattern", "fabric", "design")

# Source decks per dimension and the prose template used to append a line.
# All decks are phrase-ready; color lines are bare nouns wrapped by the
# template.
_MODIFIER_DECKS: dict[str, str] = {
    "color": "shared/colors",
    "pattern": "shared/pattern",
    "design": "shared/design",
}
_MODIFIER_TEMPLATES: dict[str, str] = {
    "color": "in {value}",
    "pattern": "{value}",
    "fabric": "{value}",
    "design": "{value}",
}

# Category-specific fabric decks keep fabric sensible per category (athletic
# wear never gets silk chiffon); they win over the shared decks.  The plain
# fabric deck is the user-facing source; the legacy garment-style deck is the
# last-resort fallback.
def _fabric_deck(resolver: WildcardResolver, category: str) -> str:
    category_deck = f"shared/garment-style-{category}"
    if resolver.file_exists(category_deck):
        return category_deck
    if resolver.file_exists("shared/fabric"):
        return "shared/fabric"
    return "shared/garment-style"

# Words that make a garment self-describing on a dimension: a garment that
# names its colour or fabric must not receive a random one (denim stays
# denim), but the remaining dimensions still vary.  Explicit #@fixed: true
# remains for pieces whose whole identity is fixed (a classic black tuxedo).
_COLOR_WORDS: frozenset[str] = frozenset({
    "black", "white", "navy", "charcoal", "ivory", "cream", "beige", "burgundy", "maroon", "teal", "blush",
    "champagne", "gold", "silver", "slate", "grey", "gray", "plum", "mauve", "sage", "emerald", "olive",
    "brown", "tan", "oat", "amber", "rose", "pink", "indigo", "violet", "lavender", "crimson", "scarlet",
    "mustard", "copper", "midnight", "iridescent", "metallic",
})
_FABRIC_WORDS: frozenset[str] = frozenset({
    "silk", "denim", "velvet", "linen", "cotton", "leather", "wool", "chiffon", "satin", "cashmere",
    "jersey", "lace", "organza", "tulle", "tweed", "corduroy", "suede", "mesh", "poplin", "gabardine",
    "microfibre", "spandex", "charmeuse",
})
_PATTERN_WORDS: frozenset[str] = frozenset({
    "floral", "print", "pinstripe", "houndstooth", "plaid", "gingham", "polka", "stripe", "striped",
    "chevron", "herringbone", "paisley", "tie-dye", "batik", "ikat", "camouflage", "camo", "marble",
    "ombre", "color-blocked", "geometric", "abstract", "embroidered", "embroidery",
})


def _names_dimension(low: str, words: frozenset[str]) -> bool:
    """Return whether the text names a word from the dimension vocabulary."""
    tokens = set(low.split())
    return bool(tokens & words)


def _category_modifiers(
    resolver: WildcardResolver,
    wardrobe_base: str,
    category: str,
    default: tuple[str, ...] = _MODIFIER_DIMENSIONS,
) -> tuple[str, ...]:
    """Read the category file's ``#@modifiers`` list (falls back to *default*)."""
    path = os.path.join(resolver.wildcards_dir, f"{wardrobe_base}/{category}.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = _DIRECTIVE_PATTERN.match(line.strip())
                if match is not None and match.group(1) == "modifiers":
                    values = tuple(part.strip() for part in match.group(2).split(",") if part.strip())
                    if values:
                        return values
    except OSError:
        pass
    return default


def _append_modifiers(
    resolver: WildcardResolver,
    context: dict[str, set[str]],
    piece: str,
    directives: dict[str, set[str]],
    category_modifiers: tuple[str, ...],
    category: str,
) -> str:
    """Append the garment's modifier clauses (color, pattern, fabric, design).

    The effective list is the garment's ``#@modifiers`` override, else the
    category list minus the garment's ``#@no_modifiers``; ``#@fixed: true``
    opts the garment out entirely.  Dimensions whose deck is unavailable are
    skipped.

    Args:
        resolver: The section resolver.
        context: The active filter context.
        piece: The resolved garment text so far.
        directives: The garment line's accumulated directives.
        category_modifiers: The category's declared modifier list.
        category: The category folder name (fabric deck selection).

    Returns:
        The piece with the modifier clauses appended.
    """
    if "true" in directives.get("fixed", ()):
        return piece
    if directives.get("modifiers"):
        effective = tuple(sorted(directives["modifiers"]))
    else:
        excluded = directives.get("no_modifiers", ())
        effective = tuple(dimension for dimension in category_modifiers if dimension not in excluded)
    low = piece.lower()
    for dimension in effective:
        if dimension == "color" and _names_dimension(low, _COLOR_WORDS):
            continue
        if dimension == "fabric" and _names_dimension(low, _FABRIC_WORDS):
            continue
        if dimension == "pattern" and _names_dimension(low, _PATTERN_WORDS):
            continue
        if dimension == "fabric":
            deck: str | None = _fabric_deck(resolver, category)
            template: str = _MODIFIER_TEMPLATES["fabric"]
        else:
            deck = _MODIFIER_DECKS.get(dimension)
            template = _MODIFIER_TEMPLATES.get(dimension, "{value}")
        if deck is None:
            continue
        value = resolver.pick_line(deck, context)
        if value:
            piece = f"{piece}, {template.format(value=value)}"
    return piece


def _resolve_slot(
    resolver: WildcardResolver,
    context: dict[str, set[str]],
    slot_base: str,
    slot: str,
    use_shared_modifiers: bool,
    category_modifiers: tuple[str, ...] = _MODIFIER_DIMENSIONS,
) -> tuple[str, dict[str, set[str]]]:
    """Resolve one garment slot to a piece string and its directives.

    Args:
        resolver: The section resolver.
        context: The active filter context.
        slot_base: The wardrobe category relative path.
        slot: The slot file name without extension.
        use_shared_modifiers: Whether to append the modifier pipeline.
        category_modifiers: The category's declared modifier list.

    Returns:
        A ``(piece, directives)`` tuple; ``("", {})`` when the file is
        missing or filters out.
    """
    if not resolver.file_exists(f"{slot_base}/{slot}"):
        return "", {}
    raw, directives = resolver.pick_line_with_directives(f"{slot_base}/{slot}", context)
    if not raw:
        return "", {}
    piece = raw
    if use_shared_modifiers and slot in _MODIFIER_SLOTS and "__" not in raw:
        category = os.path.basename(slot_base)
        piece = _append_modifiers(resolver, context, raw, directives, category_modifiers, category)
    return resolver.resolve(piece, context), directives


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
    use_common_wardrobe: bool,
    use_shared_modifiers: bool,
    mode: str,
    seed: int,
    resolver: WildcardResolver | None = None,
    occasion_options: list[str] | None = None,
    state: str = "",
    state_options: list[str] | None = None,
) -> dict[str, Any]:
    """Build a frame-consistent CHARACTER object for a persona.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        persona: The persona folder name under ``wildcards/characters/``.
        camera: The CAMERA object dict from the Camera node (``None`` = no
            stripping, all regions visible).
        occasion: Active occasion value (``""`` = unrestricted).
        use_common_wardrobe: Allow fallback to the default wardrobe of the
            matching default persona (``characters/<gender>/wardrobe``).
        use_shared_modifiers: Append shared garment-style phrases to persona
            wardrobe pieces without inline tags.
        mode: Wildcard selection mode (``"Deterministic (Seed)"`` or
            ``"Random (No Repeat)"``).
        seed: Seed for deterministic selection.
        resolver: Optional pre-built resolver (mainly for tests).
        occasion_options: Occasion choices; when *occasion* is unrestricted
            and this is provided, a seeded random occasion is rolled — only
            when the active wardrobe declares ``#@occasion`` coverage, so the
            outfit always honours the rolled occasion (an occasion-agnostic
            wardrobe stays unrestricted).
        state: State axis value (``""``/``"auto"`` = occasion-weighted roll;
            ``"dressed"``/``"revealing"``/``"mishap"``/``"slipping"``/
            ``"nude"`` forces the state; ``"nude"`` replaces the outfit with
            the persona's region-tagged ``nude.txt``).
        state_options: Explicit state subset to roll within when *state* is
            on auto (``None`` = the full weighted table).

    Returns:
        The CHARACTER object dict (see the Character node docs for the shape).
    """
    persona = _safe_persona(persona)
    persona_base = f"characters/{persona}"
    persona_dir = os.path.join(wildcards_dir, "characters", persona)

    if resolver is None:
        resolver = WildcardResolver(wildcards_dir, mode=mode, seed=seed)

    gender = _read_gender(persona_dir)
    wardrobe_base = _wardrobe_base(resolver, persona_base, gender, use_common_wardrobe)
    if occasion == "" and occasion_options:
        occasion = _roll_occasion(resolver, wildcards_dir, wardrobe_base, occasion_options)

    regions, face_visible, view = _regions_from_camera(camera)
    context = _context(occasion, regions)

    # Pick the outfit category first so its name joins the resolution context:
    # attribute files (hair.txt and friends) can then gate variants on the
    # active category via #@outfit directives.
    outfit_category = ""
    if wardrobe_base is not None:
        outfit_category = _pick_category(resolver, wardrobe_base, context)
    if outfit_category:
        context = dict(context)
        context["outfit"] = {outfit_category}

    attributes: dict[str, str] = {key: "" for key in _ALL_ATTRIBUTES}
    attributes["intro"] = _resolve_attribute(resolver, persona_base, "subject_intro", context)

    face_attribute = "profile" if view == _PROFILE_VIEW else "face"
    for region in regions:
        attribute = _REGION_TO_ATTRIBUTE[region]
        if attribute == "face":
            attribute = face_attribute
        attributes[attribute] = _resolve_attribute(resolver, persona_base, attribute, context)

    pose = _resolve_attribute(resolver, persona_base, "pose", _pose_context(context, view, face_visible))
    if not pose:
        # Graceful degradation: a persona with no pose line for this facing
        # still gets a pose rather than none.  The gaze block stays asserted
        # so face-hidden shots never degrade into "meeting the camera".
        fallback_context = dict(context)
        if not face_visible:
            fallback_context["gaze"] = {_GAZE_BLOCKED}
        pose = _resolve_attribute(resolver, persona_base, "pose", fallback_context)
    attributes["pose"] = pose

    # Identity trigger phrase (e.g. a Lora trigger token).  Resolved as a
    # plain seeded pick, carried on the object only — never part of the
    # description or keywords, so downstream nodes can extract it explicitly.
    trigger = resolver.pick_line(f"{persona_base}/trigger", None)

    outfit_pieces: list[str] = []
    piece_directives: list[dict[str, set[str]]] = []
    if outfit_category and wardrobe_base is not None:
        outfit_pieces = _fill_slots(
            resolver, context, wardrobe_base, outfit_category, regions, use_shared_modifiers, piece_directives=piece_directives
        )

    state = _resolve_state(resolver.rng, state, state_options, occasion)

    measurements = _read_measurements(persona_dir)
    visible = set(regions)
    outfit_parts: list[str] = []
    for piece, directives in zip(outfit_pieces, piece_directives, strict=False):
        fit_zones = frozenset(directives.get("fit", ()))
        fit_clause = _compose_fit(resolver.rng, fit_zones, measurements, visible, gender)
        outfit_parts.append(f"{piece}, {fit_clause}" if fit_clause else piece)

    if state == _NUDE_STATE:
        outfit_category = _NUDE_STATE
        nude_text = _resolve_nude(resolver, persona_base, context)
        if nude_text:
            outfit_parts = [nude_text]
    else:
        state_clauses = _compose_state_clauses(resolver, state, piece_directives, context)
        if state_clauses:
            # State clauses describe the garment, so they follow the first
            # outfit piece rather than trailing the accessories.
            joined = ", ".join(state_clauses)
            if outfit_parts:
                outfit_parts.insert(1, joined)
            else:
                outfit_parts.append(joined)

    subject_order = [face_attribute if key == "face" else key for key in _SUBJECT_ORDER]
    subject_parts = [attributes["intro"]] + [attributes[key] for key in subject_order]
    subject = ", ".join(part for part in subject_parts if part)

    outfit = ", ".join(outfit_parts)

    description_parts = [part for part in (subject, pose, outfit) if part]
    description = ", ".join(description_parts)

    keyword_parts = _dedupe(
        [attributes["intro"]] + [attributes[key] for key in subject_order] + [pose] + outfit_parts
    )
    keywords = ", ".join(keyword_parts)

    return {
        "type": "character",
        "persona": persona,
        "trigger": trigger,
        "state": state,
        "occasion": occasion,
        "regions": regions,
        "face_visible": face_visible,
        "attributes": attributes,
        "pose": pose,
        "outfit_category": outfit_category,
        "outfit": outfit,
        "subject": subject,
        "description": description,
        "keywords": keywords,
    }


__all__: list[str] = [
    "_ALL_ATTRIBUTES",
    "_ALL_CAMERA_REGIONS",
    "_REGION_TO_ATTRIBUTE",
    "_SUBJECT_ORDER",
    "_GARMENT_SLOTS",
    "_MODIFIER_SLOTS",
    "build_character",
    "_safe_persona",
    "_read_gender",
    "_tag_basename",
    "_regions_from_camera",
    "_context",
    "_wardrobe_base",
    "_pick_category",
    "_fill_slots",
    "_resolve_slot",
    "_occasion_headers",
    "_occasion_coverage",
    "_roll_occasion",
]
