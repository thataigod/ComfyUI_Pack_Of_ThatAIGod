"""Pure scene-composition engine for the Scene node (``Scene.py``).

Composes the scene component of the director pipeline: a directive-coherent
location, a time of day and an optional film look.  The Scene node no longer
combines components — the character and camera prose are emitted by their own
nodes and reordered downstream — so this engine builds the SCENE object's
location/time/film prose only.

Coherence rules
---------------
* **Occasion** — scene files carry ``#@occasion`` directives; the active
  occasion restricts which locations are eligible.
* **Time of day** — ``wildcards/shared/time-of-day.txt`` declares
  ``#@time`` values; an explicit time both filters locations carrying the
  matching directive and picks the corresponding phrase.  Scene files are
  stacked directive blocks (``#@time`` + ``#@setting`` per block, like the
  time-of-day file), so each block resolves its own prose.
* **Outfit context** — when a CHARACTER object is wired in, its
  ``outfit_category`` joins the context (``#@outfit``), so a location never
  clashes with the wardrobe (e.g. no beach scene for lingerie).
* **State gating** — a non-dressed character state (``nude``, ``slipping``,
  ``revealing``, ``mishap``) is asserted into the context and additionally
  restricts eligible locations to scenes that declare the state (``#@state:``)
  plus universal (directive-less) scenes such as the studio.  Public scenes
  can never host a non-dressed character.
* An explicit (non-Auto) location overrides filtering entirely.

Scene blocks own fixtures, furniture, mood and place nouns only; every
light/sky/shadow quality lives in the time-of-day phrase, so a scene never
contradicts the picked time.
"""

from __future__ import annotations

import os
import random
import re
from typing import Any

from _wildcard_core import _DIRECTIVE_PATTERN, WildcardResolver

_SCENES_DIR: str = "scenes"
_CATALOG_EXCLUDE: frozenset[str] = frozenset({"catalog.txt"})
_TIME_FILE: str = "shared/time-of-day"
_FILM_FILE: str = "styles/film-look"

# Directive keys that constrain scene selection; a scene carrying none of
# these is a universal fallback (e.g. the studio).
_SELECTION_KEYS: frozenset[str] = frozenset({"occasion", "outfit", "time", "state"})

# The character state that imposes no location restriction.  Every other
# state (nude, slipping, revealing, mishap) gates the location space.
_DRESSED_STATE: str = "dressed"

AUTO_LOCATION: str = "Auto"
ALL_TIMES: str = "All"
DEFAULT_LOCATION: str = AUTO_LOCATION
DEFAULT_TIME: str = ALL_TIMES
DEFAULT_OCCASION: str = "casual"
AUTO_OCCASION: str = "auto"
ALL_OCCASIONS: str = "All (unrestricted)"

# Matches "#@time: value, value" directive lines in time-of-day files.
_TIME_DIRECTIVE_PATTERN: re.Pattern[str] = re.compile(r"^#@\s*time\s*:\s*(.+?)\s*$")
# Matches "#@setting: value" directive lines in scene files.
_SETTING_DIRECTIVE_PATTERN: re.Pattern[str] = re.compile(r"^#@\s*setting\s*:\s*(.+?)\s*$")


def _scene_options(wildcards_dir: str) -> list[str]:
    """Return the scene dropdown options from ``wildcards/scenes/``.

    Scans the scenes directory at startup (mirroring the persona dropdown
    pattern); new scene files appear after a ComfyUI restart.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.

    Returns:
        A sorted list of scene names (without the ``.txt`` extension).
    """
    scenes_dir = os.path.join(wildcards_dir, _SCENES_DIR)
    if not os.path.isdir(scenes_dir):
        return []
    return sorted(f[:-4] for f in os.listdir(scenes_dir) if f.endswith(".txt") and f not in _CATALOG_EXCLUDE)


def _time_options(wildcards_dir: str) -> list[str]:
    """Return the time-of-day dropdown options from ``shared/time-of-day.txt``.

    The distinct ``#@time`` directive values in file order, with
    :data:`ALL_TIMES` first.  A missing or unreadable file yields just the
    unrestricted entry.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.

    Returns:
        A list of time values (with the unrestricted entry first).
    """
    options: list[str] = [ALL_TIMES]
    path = os.path.join(wildcards_dir, _TIME_FILE + ".txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = _TIME_DIRECTIVE_PATTERN.match(line.strip())
                if match is None:
                    continue
                for value in (v.strip().lower() for v in match.group(1).split(",") if v.strip()):
                    if value not in options:
                        options.append(value)
    except OSError:
        pass
    return options


def _context(occasion: str, time: str, outfit: str, state: str = "") -> dict[str, set[str]]:
    """Build the directive filter context for scene resolution.

    Unset dimensions are omitted (directives can only restrict, never
    expand, selection).  A non-dressed character state is asserted so blocks
    declaring it become eligible; ``"dressed"`` and empty states leave the
    dimension unasserted (no restriction).

    Args:
        occasion: Active occasion value, or ``""`` when unrestricted.
        time: Active time value, or ``""`` when unrestricted.
        outfit: The character's outfit category, or ``""``.
        state: The character's state, or ``""``.

    Returns:
        A context dict mapping active dimension keys to their values.
    """
    context: dict[str, set[str]] = {}
    if occasion:
        context["occasion"] = {occasion}
    if time:
        context["time"] = {time}
    if outfit:
        context["outfit"] = {outfit}
    if state and state != _DRESSED_STATE:
        context["state"] = {state}
    return context


def _has_selection_directive(path: str) -> bool:
    """Return whether a scene file declares any selection directive.

    Args:
        path: Absolute path to the scene file.

    Returns:
        ``True`` when the file carries an ``#@occasion``, ``#@outfit``,
        ``#@time`` or ``#@state`` directive line; ``#@setting`` alone does
        not count.
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = _DIRECTIVE_PATTERN.match(line.strip())
                if match is not None and match.group(1) in _SELECTION_KEYS:
                    return True
    except OSError:
        return False
    return False


def _untagged_scenes(wildcards_dir: str) -> set[str]:
    """Return the filenames of scenes with no selection directives.

    These scenes are universal fallbacks (always eligible under any
    context); auto-picking prefers directive-tagged scenes over them.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.

    Returns:
        A set of file names (e.g. ``{"studio.txt"}``), possibly empty.
    """
    scenes_dir = os.path.join(wildcards_dir, _SCENES_DIR)
    try:
        names = os.listdir(scenes_dir)
    except OSError:
        return set()
    return {
        name
        for name in names
        if name.endswith(".txt")
        and name not in _CATALOG_EXCLUDE
        and not _has_selection_directive(os.path.join(scenes_dir, name))
    }


def _state_scenes(wildcards_dir: str, state: str) -> set[str]:
    """Return the filenames of scenes declaring a given state.

    A scene declares a state when its file carries an ``#@state:`` directive
    containing the value; these are the private scenes that may host a
    non-dressed character.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        state: The state value (lowercase).

    Returns:
        A set of file names (e.g. ``{"bedroom.txt", "boudoir.txt"}``),
        possibly empty.
    """
    scenes_dir = os.path.join(wildcards_dir, _SCENES_DIR)
    try:
        names = os.listdir(scenes_dir)
    except OSError:
        return set()
    found: set[str] = set()
    for name in names:
        if not name.endswith(".txt") or name in _CATALOG_EXCLUDE:
            continue
        path = os.path.join(scenes_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    match = _DIRECTIVE_PATTERN.match(line.strip())
                    if match is not None and match.group(1) == "state":
                        if state in {v.strip().lower() for v in match.group(2).split(",")}:
                            found.add(name)
                            break
        except OSError:
            continue
    return found


def _state_blocked_scenes(wildcards_dir: str, state: str) -> set[str]:
    """Return tagged scene files that cannot host a non-dressed state.

    When a character state is active, every scene that carries selection
    directives but does not declare the state is ineligible — public scenes
    (park, office, street cafe, city, gym, beach...) can never host a
    nude/slipping/revealing/mishap character.  Universal (directive-less)
    scenes such as the studio stay eligible.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        state: The active state value (lowercase).

    Returns:
        A set of file names (possibly empty).
    """
    scenes_dir = os.path.join(wildcards_dir, _SCENES_DIR)
    try:
        names = os.listdir(scenes_dir)
    except OSError:
        return set()
    allowed = _state_scenes(wildcards_dir, state)
    return {
        name
        for name in names
        if name.endswith(".txt")
        and name not in _CATALOG_EXCLUDE
        and name not in allowed
        and _has_selection_directive(os.path.join(scenes_dir, name))
    }


def _pick_location(
    resolver: WildcardResolver,
    location: str,
    context: dict[str, set[str]],
    state: str = "",
) -> tuple[str, str]:
    """Pick the scene location and its prose.

    ``Auto`` selects any directive-eligible scene file; an explicit name
    ignores filtering (user override) and yields ``("", "")`` when the file
    is missing or resolves empty.

    When the context asserts any dimension, directive-tagged scenes are
    preferred: universal fallback scenes (no ``#@occasion``/``#@outfit``/
    ``#@time``/``#@state`` directives, e.g. the studio) are only used when
    nothing tagged is eligible, so the location stays tied to the occasion.

    A non-dressed character state is a hard gate: tagged scenes that do not
    declare the state (``#@state:``) are excluded even from the fallback, so
    public scenes can never host a non-dressed character.

    Args:
        resolver: The section resolver.
        location: ``AUTO_LOCATION`` or an explicit scene name.
        context: The active filter context.
        state: The character's state (``""``/``"dressed"`` = no gate).

    Returns:
        A ``(key, prose)`` tuple; ``("", "")`` when nothing is eligible.
    """
    if location == AUTO_LOCATION:
        base_exclude = set(_CATALOG_EXCLUDE)
        exclude = set(base_exclude)
        if context:
            exclude |= _untagged_scenes(resolver.wildcards_dir)
        state_blocked: set[str] = set()
        if state and state != _DRESSED_STATE:
            state_blocked = _state_blocked_scenes(resolver.wildcards_dir, state)
            exclude |= state_blocked
        picked = resolver.pick_file(_SCENES_DIR, context, exclude=exclude)
        if picked is None and exclude != base_exclude:
            picked = resolver.pick_file(_SCENES_DIR, context, exclude=base_exclude | state_blocked)
        if picked is None:
            return "", ""
        key = os.path.basename(picked[0])
        return key, picked[1]
    prose = resolver.pick_line(f"{_SCENES_DIR}/{location}", None)
    if not prose:
        return "", ""
    return location, prose


def _file_setting(wildcards_dir: str, location_key: str) -> str:
    """Read the ``#@setting`` directive (indoor/outdoor) of a scene file.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        location_key: The scene name (file name without extension).

    Returns:
        The setting value (lowercased), or ``""`` when unknown.
    """
    if not location_key:
        return ""
    path = os.path.join(wildcards_dir, _SCENES_DIR, location_key + ".txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = _SETTING_DIRECTIVE_PATTERN.match(line.strip())
                if match is not None:
                    return match.group(1).strip().lower()
    except OSError:
        pass
    return ""


def _pick_time(resolver: WildcardResolver, time: str, setting: str) -> str:
    """Pick the time-of-day phrase.

    An explicit time filters the phrase file by its matching ``#@time``
    directive; :data:`ALL_TIMES` picks from every phrase.  A known location
    setting (``#@setting``) further restricts the phrase to the matching
    indoor/outdoor variant, so a studio never gets an outdoor-sky phrase.

    Args:
        resolver: The section resolver.
        time: The active time value, or ``ALL_TIMES``.
        setting: The picked location's setting, or ``""`` when unknown.

    Returns:
        The chosen phrase, or ``""`` when the file is missing or filters out.
    """
    pick_context: dict[str, set[str]] = {}
    if time != ALL_TIMES:
        pick_context["time"] = {time}
    if setting:
        pick_context["setting"] = {setting}
    return resolver.pick_line(_TIME_FILE, pick_context or None)


def _pick_style(resolver: WildcardResolver, enabled: bool, file_rel: str, context: dict[str, set[str]]) -> str:
    """Pick one photographic style layer (or ``""`` when disabled/missing).

    The picked line is fully resolved (nested ``__tags__`` like the family
    references in ``styles/film-look.txt`` expand to their prose), so the
    node's output is always final text.

    Args:
        resolver: The section resolver.
        enabled: Whether the layer toggle is on.
        file_rel: The style file path relative to the wildcards directory.
        context: The active filter context.

    Returns:
        The chosen style line (resolved), or ``""``.
    """
    if not enabled:
        return ""
    line = resolver.pick_line(file_rel, context)
    if not line:
        return ""
    return resolver.resolve(line)


def _assemble(
    location_prose: str,
    location_key: str,
    time_value: str,
    time_phrase: str,
    film: str,
) -> tuple[str, str]:
    """Assemble the scene description and keywords.

    The description is the location prose, the time phrase and the film
    layer; missing parts vanish.  Keywords dedupe the location key and the
    time value (the unrestricted entry never becomes a keyword).

    Args:
        location_prose: The resolved location line.
        location_key: The location file name (keyword tag).
        time_value: The active time dropdown value (keyword tag).
        time_phrase: The resolved time-of-day phrase.
        film: The film look layer line (``""`` when off).

    Returns:
        A ``(description, keywords)`` tuple.
    """
    scene_prose = ", ".join(part for part in (location_prose, time_phrase) if part)
    description = ", ".join(part for part in (scene_prose, film) if part)

    keyword_parts: list[str] = []
    for part in (location_key, time_value if time_value != ALL_TIMES else ""):
        if part and part not in keyword_parts:
            keyword_parts.append(part)
    keywords = ", ".join(keyword_parts)
    return description, keywords


def _resolve_occasion(
    value: str,
    character: dict[str, Any] | None,
    options: list[str],
    seed: int,
) -> tuple[str, str]:
    """Resolve the Scene's occasion input to a concrete value.

    One occasion drives the whole frame; precedence:

    * ``"auto"`` (default) — the wired CHARACTER object's occasion used
      verbatim (including ``""`` when the character is dressed
      unrestricted), otherwise a seeded random pick from *options* (and
      ``""`` when no options exist).
    * ``""`` or ``"All (unrestricted)"`` — no occasion filtering.
    * Anything else — used verbatim (lowercased), e.g. ``"travel"``.

    Args:
        value: The raw occasion input.
        character: The wired CHARACTER object dict, or ``None``.
        options: The available occasion values (for the random pick).
        seed: Seed for the random pick.

    Returns:
        A ``(occasion, source)`` tuple; *source* is one of ``"character"``,
        ``"random"``, ``"unrestricted"`` or ``"explicit"``.
    """
    raw = (value or "").strip().lower()
    if raw in ("", "all (unrestricted)", "all"):
        return "", "unrestricted"
    if raw == AUTO_OCCASION:
        if isinstance(character, dict):
            character_occasion = str(character.get("occasion", "") or "").strip().lower()
            return character_occasion, "character"
        candidates = [option for option in options if option.strip() and option.strip().lower() != ALL_OCCASIONS.lower()]
        if not candidates:
            return "", "unrestricted"
        rng = random.Random(seed)
        return rng.choice(candidates), "random"
    return raw, "explicit"


def build_scene(
    wildcards_dir: str,
    character: dict[str, Any] | None,
    occasion: str,
    occasion_source: str,
    location: str,
    time: str,
    use_film: bool,
    mode: str,
    seed: int,
    resolver: WildcardResolver | None = None,
) -> dict[str, Any]:
    """Build a frame-consistent SCENE object for the final prompt.

    Args:
        wildcards_dir: Absolute path to the wildcards root directory.
        character: The CHARACTER object dict from the Character node
            (``None`` when unwired); contributes the outfit context and the
            state gate.
        occasion: Active occasion value (``""`` = unrestricted).
        occasion_source: How the occasion was resolved (``"explicit"``,
            ``"character"``, ``"random"`` or ``"unrestricted"``).
        location: ``AUTO_LOCATION`` or an explicit scene name.
        time: Active time value (``ALL_TIMES`` = unrestricted).
        use_film: Include the film look layer.
        mode: Wildcard selection mode (``"Deterministic (Seed)"`` or
            ``"Random (No Repeat)"``).
        seed: Seed for deterministic selection.
        resolver: Optional pre-built resolver (mainly for tests).

    Returns:
        The SCENE object dict (see the Scene node docs for the shape).
    """
    outfit = str(character.get("outfit_category", "") or "") if isinstance(character, dict) else ""
    state = str(character.get("state", "") or "").strip().lower() if isinstance(character, dict) else ""
    if outfit == "nude":
        # The character engine substitutes the sentinel "nude" category for the
        # outfit when the state is nude; it is not a wardrobe category any
        # scene declares, so it must not restrict the location space.
        outfit = ""
    context = _context(occasion, "" if time == ALL_TIMES else time, outfit, state)

    if resolver is None:
        resolver = WildcardResolver(wildcards_dir, mode=mode, seed=seed)

    location_key, location_prose = _pick_location(resolver, location, context, state)
    setting = _file_setting(wildcards_dir, location_key)
    time_phrase = _pick_time(resolver, time, setting)
    film = _pick_style(resolver, use_film, _FILM_FILE, context)

    description, keywords = _assemble(location_prose, location_key, time, time_phrase, film)

    return {
        "type": "scene",
        "occasion": occasion,
        "occasion_source": occasion_source,
        "location": location_prose,
        "location_key": location_key,
        "setting": setting,
        "time_of_day": time_phrase,
        "film_look": film,
        "state": state,
        "description": description,
        "keywords": keywords,
        "mode": mode,
        "seed": seed,
    }


__all__: list[str] = [
    "AUTO_LOCATION",
    "ALL_TIMES",
    "DEFAULT_LOCATION",
    "DEFAULT_TIME",
    "DEFAULT_OCCASION",
    "AUTO_OCCASION",
    "ALL_OCCASIONS",
    "build_scene",
    "_scene_options",
    "_time_options",
    "_context",
    "_pick_location",
    "_pick_time",
    "_pick_style",
    "_file_setting",
    "_resolve_occasion",
    "_assemble",
    "_has_selection_directive",
    "_untagged_scenes",
    "_state_scenes",
    "_state_blocked_scenes",
]
