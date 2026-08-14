"""Shared directive-aware wildcard engine for ComfyUI_Pack_Of_ThatAIGod.

Provides :class:`WildcardResolver`, the resolution engine powering the
Character Director pipeline (``Character_Director.py``).  It extends plain
``__wildcard__`` tag resolution with:

* **``#@`` metadata directives** — comment lines such as
  ``#@occasion: beach, resort`` declare compatibility constraints.  A
  directive applies to every following line in the file; directives of
  different keys accumulate (stacked ``#@outfit`` + ``#@occasion`` headers
  combine), but a repeated key *replaces* its previous value so later
  ``#@scale`` blocks override earlier ones.
* **Context-based eligibility filtering** — :class:`WildcardResolver` methods
  accept a *filter context* (a ``dict[str, set[str]]`` mapping dimension keys
  like ``occasion``/``scale``/``regions``/``outfit``/``setting`` to the set of
  currently active values).  A line whose accumulated directives all intersect
  the context is *eligible*; directive values can only ever restrict, never
  expand, selection.  A directive key the runner does not assert is ignored,
  so files without directives behave as universal.
* **Deep line filtering** — when a candidate line is itself a pure
  ``__tag__`` (e.g. a catalog line pointing at a category file), the
  *referenced* file's directives decide whether the line survives.  This is
  what makes cross-node coherence possible (a wardrobe catalog never offers
  lingerie when the occasion is a public setting).
* **Strict empty resolution** — if every line of a file is filtered out by
  the active context the tag resolves to an empty string (it disappears from
  the output) rather than leaking mismatched content (see DECISIONS.md D12).
* The same three selection modes as the Wildcard Reader node: deterministic
  (seed-based), full random, and no-repeat deck (per-file, per-context decks).

``Wildcard_Reader.py`` deliberately keeps its own self-contained machinery;
see DECISIONS.md D12 for the reasoning.
"""

import logging
import os
import random
import re

logger: logging.Logger = logging.getLogger("ThatAIGod")

# Matches __tag__ tokens; allows letters, digits, underscores, hyphens, slashes,
# backslashes, dots and spaces so that subdirectory paths and display-name folders
# work (e.g. __wardrobe/female/casual__ or __characters/Rohini Smirnova/hair__).
# Matches "__tag__" tokens.  Lazy quantifier: a tag ends at the first closing
# "__", so "a __color1__ and __color2__" line resolves as two tags (spaces are
# allowed inside tags for persona folders like "Rohini Smirnova").
_WILDCARD_PATTERN: re.Pattern[str] = re.compile(r"__([a-zA-Z0-9_\-\/\\\. ]+?)__")
# Matches {choice1|choice2|...} inline choice blocks (pipe-separated).
_CHOICE_PATTERN: re.Pattern[str] = re.compile(r"\{([^}]+)\}")
# Matches a line that is *entirely* one wildcard tag (used for deep filtering).
_TAG_ONLY_PATTERN: re.Pattern[str] = re.compile(r"^__([a-zA-Z0-9_\-\/\\\\. ]+)__$")
# Matches "#@key: value, value" directive comment lines.
_DIRECTIVE_PATTERN: re.Pattern[str] = re.compile(r"^#@\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?)\s*$")
# Maximum number of nested wildcard resolution passes to prevent infinite loops.
_MAX_WILDCARD_ITERATIONS: int = 50
# Maximum number of file-content cache entries before FIFO eviction.
_MAX_CONTENT_CACHE_SIZE: int = 100
# Directive keys recognised by the engine.  Unknown keys are ignored with a warning.
# Beyond the classic scene/outfit dimensions, the character object system asserts
# camera-geometry dimensions (facing, gaze, elevation, awareness) and free-form
# grouping keys (time, location, context, preset) so persona, pose, lighting and
# interaction files can all be directive-filtered.
KNOWN_DIRECTIVE_KEYS: frozenset[str] = frozenset(
    {
        "occasion",
        "scale",
        "regions",
        "outfit",
        "setting",
        "time",
        "location",
        "facing",
        "gaze",
        "elevation",
        "roll",
        "awareness",
        "context",
        "preset",
        "fit",
        "condition",
        "mishap",
        "slip",
        "modifiers",
        "no_modifiers",
        "fixed",
    }
)

# A filter context maps a dimension key to the set of currently active values.
# None means "no filtering" (plain wildcard behaviour).
FilterContext = dict[str, set[str]] | None


def _context_key(context: FilterContext) -> str:
    """Return a deterministic cache key for a filter context.

    Used to key no-repeat decks so that the same file under different
    contexts gets an independent shuffle.

    Args:
        context: The filter context to serialise.

    Returns:
        A canonical string representation; ``""`` when the context is ``None``
        or empty.
    """
    if not context:
        return ""
    return repr(sorted((k, tuple(sorted(v))) for k, v in context.items()))


class WildcardResolver:
    """Directive-aware wildcard resolver with deterministic/random/deck modes.

    Instances are cheap; the heavy state (file index, content cache, decks)
    lives in class-level caches shared across all instances, keyed by absolute
    file path and invalidated by mtime (mirroring the Wildcard Reader node's
    caching strategy).
    """

    # _file_index_cache: wildcards_dir → {filename → [relative_paths]}
    _file_index_cache: dict[str, dict[str, list[str]]] = {}
    # _file_mtimes: wildcards_dir → {absolute_path → mtime}
    _file_mtimes: dict[str, dict[str, float]] = {}
    # _annotations_cache: absolute_path → (mtime, [(line, accumulated_directives), ...])
    _annotations_cache: dict[str, tuple[float, list[tuple[str, dict[str, set[str]]]]]] = {}
    # _deck_cache: (absolute_path_or_dir, deck_salt, context_key) → (mtime, shuffled_deck)
    _deck_cache: dict[tuple[str, str, str], tuple[float, list[str]]] = {}

    def __init__(self, wildcards_dir: str, mode: str = "Deterministic (Seed)", seed: int = 0) -> None:
        """Initialise the resolver.

        Args:
            wildcards_dir: Absolute path to the wildcards root directory.
            mode: One of ``"Deterministic (Seed)"``, ``"Full Random"`` or
                ``"Random (No Repeat)"``.
            seed: RNG seed; used only in ``"Deterministic (Seed)"`` mode.
        """
        self.wildcards_dir: str = wildcards_dir
        self.mode: str = mode
        self.seed: int = seed
        if mode == "Deterministic (Seed)":
            self.rng: random.Random = random.Random(seed)
        else:
            self.rng = random.Random()

    # ------------------------------------------------------------------
    # File machinery
    # ------------------------------------------------------------------

    def _build_file_index(self, wildcards_dir: str) -> dict[str, list[str]]:
        """Build or return a cached index mapping basename → list of relative paths.

        Mirrors the Wildcard Reader node's index (basename to relative paths
        from *wildcards_dir*), invalidated when any ``.txt`` file's mtime
        changes.  Shared caches are keyed by *wildcards_dir*.

        Args:
            wildcards_dir: Absolute path to the wildcards root directory.

        Returns:
            A dict mapping filename basename (``"foo.txt"``) to a sorted list
            of relative paths (``["foo.txt", "sub/foo.txt"]``).
        """
        cache_key: str = wildcards_dir
        needs_refresh = cache_key not in self._file_index_cache

        if not needs_refresh:
            cached_mtimes = self._file_mtimes.get(cache_key, {})
            for root, _dirs, files in os.walk(wildcards_dir):
                for f in files:
                    if f.endswith(".txt"):
                        abs_path = os.path.join(root, f)
                        if abs_path not in cached_mtimes or cached_mtimes[abs_path] != os.path.getmtime(abs_path):
                            needs_refresh = True
                            break
                if needs_refresh:
                    break

        if not needs_refresh:
            return self._file_index_cache[cache_key]

        file_index: dict[str, list[str]] = {}
        mtimes: dict[str, float] = {}
        for root, dirs, files in os.walk(wildcards_dir):
            dirs.sort()
            files.sort()
            for f in files:
                if f.endswith(".txt"):
                    if f not in file_index:
                        file_index[f] = []
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, wildcards_dir).replace("\\", "/")
                    file_index[f].append(rel_path)
                    mtimes[abs_path] = os.path.getmtime(abs_path)

        self._file_index_cache[cache_key] = file_index
        self._file_mtimes[cache_key] = mtimes
        return file_index

    def _parse_file(self, file_path: str) -> list[tuple[str, dict[str, set[str]]]] | None:
        """Return ``[(line, accumulated_directives), ...]`` for a file from cache.

        Raw lines are stripped.  Directive lines (``#@key: values``) are parsed
        and *accumulate* as the file is scanned, so a directive applies to every
        following line.  Plain comment lines (``#``) and blank lines are
        excluded from the result.  The cache is keyed by absolute path and
        invalidated on mtime change, with FIFO eviction at
        :data:`_MAX_CONTENT_CACHE_SIZE`.

        Args:
            file_path: Absolute path to the wildcard ``.txt`` file.

        Returns:
            A list of ``(line, directives)`` tuples for non-comment lines, or
            ``None`` if the file cannot be read.
        """
        try:
            current_mtime = os.path.getmtime(file_path)
        except OSError:
            return None

        cached = self._annotations_cache.get(file_path)
        if cached is not None and cached[0] == current_mtime:
            return cached[1]

        try:
            with open(file_path, encoding="utf-8") as f:
                raw_lines = [line.strip() for line in f]
        except (OSError, UnicodeDecodeError):
            logger.warning("Failed to read wildcard file: %s", file_path)
            return None

        current_directives: dict[str, set[str]] = {}
        entries: list[tuple[str, dict[str, set[str]]]] = []
        for line in raw_lines:
            if not line:
                continue
            if line.startswith("#@"):
                match = _DIRECTIVE_PATTERN.match(line)
                if match is None:
                    continue
                key, values_raw = match.group(1), match.group(2)
                if key not in KNOWN_DIRECTIVE_KEYS:
                    logger.warning("Unknown wildcard directive key '%s' in %s", key, file_path)
                values = {v.strip().lower() for v in values_raw.split(",") if v.strip()}
                if values:
                    current_directives[key] = values
            elif not line.startswith("#"):
                entries.append((line, dict(current_directives)))

        if len(self._annotations_cache) >= _MAX_CONTENT_CACHE_SIZE:
            self._annotations_cache.pop(next(iter(self._annotations_cache)))
        self._annotations_cache[file_path] = (current_mtime, entries)
        return entries

    def _resolve_tag_path(self, tag: str) -> str | None:
        """Resolve a wildcard tag to an absolute file path (or ``None``).

        Mirrors the Wildcard Reader node's resolution strategy: exact file
        lookup first, then basename fallback via the file index, with a
        path-traversal guard ensuring the resolved path stays inside the
        wildcards directory.

        Args:
            tag: The tag string between the double underscores (e.g.
                ``"colors"`` or ``"wardrobe/female/casual"``).

        Returns:
            The absolute path to the matching ``.txt`` file, or ``None``.
        """
        clean_tag = tag.strip("_").replace("\\", "/")
        search_filename = clean_tag if clean_tag.endswith(".txt") else clean_tag + ".txt"

        direct_path = os.path.join(self.wildcards_dir, search_filename)
        final_path: str | None = None
        if os.path.exists(direct_path):
            final_path = direct_path
        else:
            file_index = self._build_file_index(self.wildcards_dir)
            base_name = os.path.basename(search_filename)
            if base_name in file_index:
                final_path = os.path.join(self.wildcards_dir, file_index[base_name][0])

        if final_path is None:
            return None

        real_wildcards = os.path.realpath(self.wildcards_dir)
        real_final = os.path.realpath(final_path)
        if not real_final.startswith(real_wildcards + os.sep) and real_final != real_wildcards:
            return None
        return real_final.replace("\\", "/")

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------

    @staticmethod
    def _line_eligible(directives: dict[str, set[str]], context: FilterContext) -> bool:
        """Return whether a line's accumulated directives are satisfied by the context.

        A directive key the runner does not assert (absent from *context*) is
        not restrictive, so directive-free lines are always eligible and
        directives can only ever reduce the candidate set.

        Args:
            directives: The line's accumulated ``#@`` directives.
            context: The active filter context (``None`` means no filtering).

        Returns:
            ``True`` when every asserted directive key intersects the context.
        """
        if context is None:
            return True
        for key, values in directives.items():
            active = context.get(key)
            if active is None:
                continue
            if not (values & active):
                return False
        return True

    def _tag_deep_eligible(self, line: str, context: FilterContext, visited: frozenset[str]) -> bool:
        """Deep-check a pure-tag line against the referenced file's directives.

        When *line* is exactly one ``__tag__``, the referenced file is looked
        up and :meth:`_file_has_eligible_lines` decides whether the tag could
        ever resolve under *context*.  *visited* guards against cyclic tag
        references.

        Args:
            line: The candidate line text.
            context: The active filter context.
            visited: Absolute paths already checked in this descent.

        Returns:
            ``True`` when the line is not a pure tag, its referenced file is
            missing, or the referenced file has at least one eligible line.
        """
        match = _TAG_ONLY_PATTERN.match(line)
        if match is None:
            return True
        ref_path = self._resolve_tag_path(match.group(1))
        if ref_path is None:
            return True
        return self._file_has_eligible_lines(ref_path, context, visited)

    def _file_has_eligible_lines(self, file_path: str, context: FilterContext, visited: frozenset[str] = frozenset()) -> bool:
        """Return whether *file_path* has any candidate line eligible under *context*.

        Args:
            file_path: Absolute path to the wildcard file.
            context: The active filter context.
            visited: Absolute paths already checked (cycle guard).

        Returns:
            ``True`` when at least one non-comment line is eligible; ``False``
            when the file is unreadable, empty, or fully filtered out.
        """
        if file_path in visited:
            return True
        visited = visited | {file_path}
        for line, directives in self._parse_file(file_path) or []:
            if not self._line_eligible(directives, context):
                continue
            if self._tag_deep_eligible(line, context, visited):
                return True
        return False

    def _eligible_lines(self, file_path: str, context: FilterContext) -> list[str]:
        """Return the candidate lines of *file_path* eligible under *context*.

        A line is eligible when its accumulated directives are satisfied and,
        for pure-tag lines, the referenced file can resolve under the same
        context.

        Args:
            file_path: Absolute path to the wildcard file.
            context: The active filter context.

        Returns:
            The eligible non-comment lines (possibly empty).
        """
        if context is None:
            return [line for line, _dirs in self._parse_file(file_path) or []]
        result: list[str] = []
        for line, directives in self._parse_file(file_path) or []:
            if self._line_eligible(directives, context) and self._tag_deep_eligible(line, context, frozenset()):
                result.append(line)
        return result

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _pick(self, candidates: list[str], cache_path: str, context: FilterContext, salt: str = "") -> str:
        """Pick one candidate according to the resolver's selection mode.

        ``"Deterministic (Seed)"`` sorts the candidates before choosing so the
        result is stable for a given seed; ``"Full Random"`` chooses from the
        natural file order; ``"Random (No Repeat)"`` draws from a per-file,
        per-context shuffle deck that reshuffles when exhausted or when the
        file's mtime changes.  *salt* separates decks within one file (e.g.
        per directive block in :meth:`pick_line_per_block`).

        Args:
            candidates: Non-empty list of candidate strings.
            cache_path: Absolute path (file or directory) used as the deck key.
            context: The filter context (part of the deck key).
            salt: Extra deck-key discriminator ("" for plain picks).

        Returns:
            The chosen candidate.
        """
        if self.mode == "Random (No Repeat)":
            deck_key = (cache_path, salt, _context_key(context))
            try:
                mtime = os.path.getmtime(cache_path)
            except OSError:
                mtime = 0.0
            entry = self._deck_cache.get(deck_key)
            if entry is None or entry[0] != mtime or not entry[1]:
                shuffled = list(candidates)
                self.rng.shuffle(shuffled)
                self._deck_cache[deck_key] = (mtime, shuffled)
                entry = self._deck_cache[deck_key]
            return entry[1].pop(0)
        if self.mode == "Deterministic (Seed)":
            return self.rng.choice(sorted(candidates))
        return self.rng.choice(candidates)

    def pick_line(self, file_rel: str, context: FilterContext) -> str:
        """Pick a random eligible line from ``wildcards_dir/file_rel.txt``.

        Args:
            file_rel: Path to the wildcard file relative to the wildcards
                directory, without the ``.txt`` extension (e.g.
                ``"shots/camera"``).
            context: The active filter context.

        Returns:
            The chosen line (without nested expansion), or ``""`` when the
            file is missing, empty, or fully filtered out by the context.
        """
        line, _directives = self.pick_line_with_directives(file_rel, context)
        return line

    def pick_line_with_directives(self, file_rel: str, context: FilterContext) -> tuple[str, dict[str, set[str]]]:
        """Pick a random eligible line, returning it with its accumulated directives.

        Args:
            file_rel: Path to the wildcard file relative to the wildcards
                directory, without the ``.txt`` extension.
            context: The active filter context.

        Returns:
            A ``(line, directives)`` tuple; ``("", {})`` when the file is
            missing, empty, or fully filtered out.
        """
        path = os.path.join(self.wildcards_dir, file_rel + ".txt")
        if not os.path.isfile(path):
            return "", {}
        entries = self._parse_file(path) or []
        if not entries:
            return "", {}
        candidates = [
            (line, directives)
            for line, directives in entries
            if self._line_eligible(directives, context) and self._tag_deep_eligible(line, context, frozenset())
        ]
        if not candidates:
            return "", {}
        lines = [line for line, _directives in candidates]
        chosen = self._pick(lines, path, context)
        return candidates[lines.index(chosen)]

    def pick_line_per_block(self, file_rel: str, context: FilterContext) -> str:
        """Pick one eligible line per directive block and join them with commas.

        Consecutive lines sharing identical accumulated directives form a
        block; every block whose directives are satisfied by *context*
        contributes one seeded pick, in file order.  Used for region-tagged
        prose (e.g. a persona's ``nude.txt``) so each visible body zone can
        contribute its own description.

        Args:
            file_rel: Path to the wildcard file relative to the wildcards
                directory, without the ``.txt`` extension.
            context: The active filter context.

        Returns:
            The joined picks, or ``""`` when the file is missing or empty.
        """
        path = os.path.join(self.wildcards_dir, file_rel + ".txt")
        if not os.path.isfile(path):
            return ""
        entries = self._parse_file(path) or []
        if not entries:
            return ""
        blocks: list[list[str]] = []
        block_key: str | None = None
        for line, directives in entries:
            key = _context_key(directives) if directives else ""
            if key != block_key:
                blocks.append([])
                block_key = key
            if self._line_eligible(directives, context) and self._tag_deep_eligible(line, context, frozenset()):
                blocks[-1].append(line)
        picked = [
            self._pick(lines, path, context, salt=str(index))
            for index, lines in enumerate(blocks)
            if lines
        ]
        return ", ".join(picked)

    def file_exists(self, file_rel: str) -> bool:
        """Return whether ``wildcards_dir/file_rel.txt`` exists.

        Args:
            file_rel: Path relative to the wildcards directory (no extension).

        Returns:
            ``True`` if the file exists.
        """
        return os.path.isfile(os.path.join(self.wildcards_dir, file_rel + ".txt"))

    def pick_file(self, dir_rel: str, context: FilterContext, exclude: set[str] | None = None) -> tuple[str, str] | None:
        """Pick a random eligible file from ``wildcards_dir/dir_rel`` and a line from it.

        Files in the directory are filtered by directive eligibility; a random
        eligible file is selected, then a random eligible line is picked from
        it.  Used for scene and (fallback) wardrobe category selection.

        Args:
            dir_rel: Directory path relative to the wildcards directory
                (e.g. ``"scenes"``).
            context: The active filter context.
            exclude: Set of filenames to skip (e.g. ``{"catalog.txt"}``).

        Returns:
            A ``(file_rel_without_ext, line)`` tuple, or ``None`` when the
            directory is missing or no file is eligible.
        """
        base = os.path.join(self.wildcards_dir, dir_rel)
        if not os.path.isdir(base):
            return None
        excluded = exclude or set()
        files = sorted(f for f in os.listdir(base) if f.endswith(".txt") and f not in excluded)
        eligible = [f for f in files if self._file_has_eligible_lines(os.path.join(base, f), context)]
        if not eligible:
            return None
        chosen = self._pick(eligible, base, context)
        file_rel = f"{dir_rel}/{chosen[:-4]}"
        return file_rel, self.pick_line(file_rel, context)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, text: str, context: FilterContext = None) -> str:
        """Resolve all wildcard tags and inline choices in *text* under *context*.

        Iteratively replaces ``__tag__`` tokens (each pass resolving one
        unique tag at a time, sorted for determinism) up to
        :data:`_MAX_WILDCARD_ITERATIONS` passes, then expands
        ``{choice1|choice2}`` blocks.  Tags that cannot be resolved (missing
        file, or fully filtered out) resolve to an empty string and vanish
        from the output.

        Args:
            text: Input text containing ``__wildcard__`` tags and/or choices.
            context: The active filter context (``None`` = no filtering).

        Returns:
            The resolved, whitespace-stripped string.
        """
        processed = text if text else ""
        for _iteration in range(_MAX_WILDCARD_ITERATIONS):
            matches = sorted(set(_WILDCARD_PATTERN.findall(processed)))
            if not matches:
                break
            for match in matches:
                tag = f"__{match}__"
                replacement = self._resolve_tag(match, context)
                if replacement == tag:
                    replacement = ""
                if tag in processed:
                    processed = processed.replace(tag, replacement, 1)
                    break

        def _choice_replacer(m: re.Match[str]) -> str:
            inner = m.group(1)
            options = [s.strip() for s in inner.split("|") if s.strip()]
            return self.rng.choice(options) if options else m.group(0)

        processed = _CHOICE_PATTERN.sub(_choice_replacer, processed)
        return processed.strip()

    def _resolve_tag(self, tag: str, context: FilterContext) -> str:
        """Resolve a single tag to an eligible line (or empty string).

        Args:
            tag: The tag string between the double underscores.
            context: The active filter context.

        Returns:
            A randomly selected eligible line, ``""`` when the file is
            missing/empty/fully filtered, or the literal ``"__tag__"`` string
            when path resolution fails.
        """
        final_path = self._resolve_tag_path(tag)
        if final_path is None:
            return f"__{tag}__"
        candidates = self._eligible_lines(final_path, context)
        if not candidates:
            return ""
        return self._pick(candidates, final_path, context)


__all__: list[str] = [
    "WildcardResolver",
    "FilterContext",
    "KNOWN_DIRECTIVE_KEYS",
    "_WILDCARD_PATTERN",
    "_CHOICE_PATTERN",
    "_MAX_WILDCARD_ITERATIONS",
    "_MAX_CONTENT_CACHE_SIZE",
    "_context_key",
]
