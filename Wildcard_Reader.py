"""Wildcard Reader node for ComfyUI.

Provides :class:`WildcardReader`, which resolves ``__wildcard__`` placeholder
tokens in text by randomly selecting lines from matching ``.txt`` files in the
``wildcards/`` directory.

Key features:

* Three selection modes: deterministic (seed-based), full random, and no-repeat deck
* Nested wildcard resolution — wildcard files may themselves contain ``__tags__``
  (up to :data:`_MAX_WILDCARD_ITERATIONS` levels deep)
* ``{option1|option2|option3}`` inline choice syntax (pipe-separated)
* Mtime-based file content cache to avoid redundant disk reads (see DECISIONS.md D4)
* Path-traversal protection — wildcard names are resolved only within the
  ``wildcards/`` directory
* Prepend / Append text inputs combined with a configurable delimiter

See ``wildcards/README.md`` for the wildcard file naming scheme and examples.
"""

import logging
import os
import random
import re
from typing import Any

logger: logging.Logger = logging.getLogger("ThatAIGod")

# Matches __tag__ tokens; allows letters, digits, underscores, hyphens, slashes,
# backslashes, and dots so that subdirectory paths work (e.g. __autowildcards/colors__).
_WILDCARD_PATTERN: re.Pattern[str] = re.compile(r"__([a-zA-Z0-9_\-\/\\\\.]+)__")
# Matches {choice1|choice2|...} inline choice blocks (pipe-separated).
_CHOICE_PATTERN: re.Pattern[str] = re.compile(r"\{([^}]+)\}")
# Maximum number of nested wildcard resolution passes to prevent infinite loops.
_MAX_WILDCARD_ITERATIONS: int = 50
# Maximum number of file-content cache entries before FIFO eviction (see DECISIONS.md D4).
_MAX_CONTENT_CACHE_SIZE: int = 100


class WildcardReader:
    """Resolves __wildcard__ tokens in text with random lines from matching .txt files.

    Supports deterministic (seed-based), full random, and no-repeat deck modes.
    Files are cached by mtime for performance (see DECISIONS.md D4).
    """

    DESCRIPTION = "Replaces __wildcard__ tokens in text with random lines from matching text files in the wildcards directory. Supports deterministic (seed-based), full random, and no-repeat deck modes."

    # Class-level caches shared across all instances (ComfyUI uses singletons).
    # _file_index_cache: wildcards_dir → {filename → [relative_paths]}
    _file_index_cache: dict[str, dict[str, list[str]]] = {}
    # _file_mtimes: wildcards_dir → {absolute_path → mtime}
    _file_mtimes: dict[str, dict[str, float]] = {}
    # _file_content_cache: absolute_path → (mtime, lines)
    _file_content_cache: dict[str, tuple[float, list[str]]] = {}
    # _deck_cache: absolute_path → (mtime, shuffled_deck_list)
    _deck_cache: dict[str, tuple[float, list[str]]] = {}

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node.

        Scans the ``wildcards/`` directory at startup to populate the dropdown.
        """
        current_dir: str = os.path.dirname(os.path.realpath(__file__))
        wildcards_dir: str = os.path.join(current_dir, "wildcards")

        wildcard_files: list[str] = []

        if os.path.exists(wildcards_dir):
            root_files: list[str] = [
                f"__{f.replace('.txt', '')}__"
                for f in os.listdir(wildcards_dir)
                if os.path.isfile(os.path.join(wildcards_dir, f)) and f.endswith(".txt")
            ]
            wildcard_files.extend(sorted(root_files))

            sub_entries: list[str] = []
            for root, dirs, files in os.walk(wildcards_dir):
                dirs.sort()
                rel_path: str = os.path.relpath(root, wildcards_dir)
                if rel_path == ".":
                    continue
                for f in files:
                    if f.endswith(".txt"):
                        sub_path: str = os.path.join(rel_path, f).replace("\\", "/")
                        entry: str = f"__{sub_path.replace('.txt', '')}__"
                        sub_entries.append(entry)

            wildcard_files.extend(sorted(sub_entries))

        options_list: list[str] = ["Select a file from the wildcards directory"] + wildcard_files

        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamic": True,
                        "placeholder": "Text in this field is evaluated for wildcards. Example: 'A woman wearing a __colors__ top'",
                        "tooltip": (
                            "Text containing __wildcard__ tokens and/or {choice1|choice2} inline choices. "
                            "Wildcards are resolved recursively up to 50 levels deep."
                        ),
                    },
                ),
                "Select to add Wildcard": (
                    options_list,
                    {"tooltip": "Select a wildcard file to append its tag to the text field above."},
                ),
                "mode": (
                    ["Deterministic (Seed)", "Full Random", "Random (No Repeat)"],
                    {
                        "default": "Deterministic (Seed)",
                        "tooltip": (
                            "Deterministic: same seed always produces the same output. "
                            "Full Random: new random choice every run. "
                            "Random (No Repeat): shuffles and draws without replacement."
                        ),
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "tooltip": "Seed for Deterministic mode. Ignored in Full Random and Random (No Repeat) modes.",
                    },
                ),
                "delimiter": (
                    "STRING",
                    {
                        "default": ", ",
                        "tooltip": "Separator inserted between Prependable Text, the resolved text, and Appendable Text.",
                    },
                ),
            },
            "optional": {
                "Prependable Text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Text added before the resolved wildcard text, separated by the delimiter.",
                    },
                ),
                "Appendable Text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Text added after the resolved wildcard text, separated by the delimiter.",
                    },
                ),
            },
        }

    RETURN_TYPES: tuple[str, ...] = ("STRING",)
    RETURN_NAMES: tuple[str, ...] = ("Text",)
    FUNCTION: str = "process"
    CATEGORY: str = "ThatAIGod/Text Utils"

    @classmethod
    def IS_CHANGED(cls, text: str, mode: str, seed: int, delimiter: str, **kwargs: Any) -> float | int:
        """Tell ComfyUI when to re-execute this node.

        Returns ``float("nan")`` for non-deterministic modes, which causes ComfyUI
        to treat the node as always changed and re-execute it on every run.
        For Deterministic mode the seed value is returned; the node is only
        re-executed when the seed changes.
        """
        if mode != "Deterministic (Seed)":
            return float("nan")
        return seed

    def _build_file_index(self, wildcards_dir: str) -> dict[str, list[str]]:
        """Build or return a cached index mapping basename → list of relative paths.

        The index maps each ``.txt`` basename (e.g. ``"colors.txt"``) to the list of
        relative paths (from *wildcards_dir*) where a file with that name exists.
        This supports subdirectory files while still allowing short ``__tag__`` syntax
        that resolves to the first matching file.

        The cache is keyed by *wildcards_dir* and is invalidated if any ``.txt`` file's
        mtime has changed since the last build (see DECISIONS.md D4 and D8).

        Args:
            wildcards_dir: Absolute path to the wildcards root directory.

        Returns:
            A dict mapping filename basename (``"foo.txt"``) to a sorted list of
            relative paths (``["foo.txt", "autowildcards/foo.txt"]``).
        """
        cache_key: str = wildcards_dir
        needs_refresh = cache_key not in self._file_index_cache

        if not needs_refresh:
            cached_mtimes = self._file_mtimes.get(cache_key, {})
            for root, dirs, files in os.walk(wildcards_dir):
                for f in files:
                    if f.endswith(".txt"):
                        abs_path = os.path.join(root, f)
                        current_mtime = os.path.getmtime(abs_path)
                        # Rebuild index if any file was modified since last cache
                        if abs_path not in cached_mtimes or cached_mtimes[abs_path] != current_mtime:
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
                    rel_path: str = os.path.relpath(abs_path, wildcards_dir).replace("\\", "/")
                    file_index[f].append(rel_path)
                    mtimes[abs_path] = os.path.getmtime(abs_path)

        self._file_index_cache[cache_key] = file_index
        self._file_mtimes[cache_key] = mtimes
        return file_index

    def _get_file_lines(self, file_path: str) -> list[str] | None:
        """Return the non-empty, non-comment lines of *file_path* from the content cache.

        The cache entry is keyed by absolute path and stores ``(mtime, lines)``.
        If the file's mtime has changed the cached entry is replaced.  When the cache
        reaches :data:`_MAX_CONTENT_CACHE_SIZE` entries the oldest entry is evicted
        (FIFO — see DECISIONS.md D4).

        Lines starting with ``#`` are treated as comments and excluded.  Blank lines
        are also excluded.

        Args:
            file_path: Absolute path to the wildcard ``.txt`` file.

        Returns:
            A list of stripped non-empty, non-comment lines, or ``None`` if the
            file cannot be read (``OSError`` or ``UnicodeDecodeError``).
        """
        try:
            current_mtime = os.path.getmtime(file_path)
        except OSError:
            return None

        cached = WildcardReader._file_content_cache.get(file_path)
        if cached is not None:
            cached_mtime, cached_lines = cached
            if cached_mtime == current_mtime:
                return cached_lines

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            if len(WildcardReader._file_content_cache) >= _MAX_CONTENT_CACHE_SIZE:
                WildcardReader._file_content_cache.pop(next(iter(WildcardReader._file_content_cache)))
            WildcardReader._file_content_cache[file_path] = (current_mtime, lines)
            return lines
        except (OSError, UnicodeDecodeError):
            logger.warning("Failed to read wildcard file: %s", file_path)
            return None

    def _get_line_from_file(
        self, wildcard_tag: str, file_index: dict[str, list[str]], wildcards_dir: str, mode: str, rng: random.Random
    ) -> str:
        """Resolve a single wildcard tag to a randomly selected line from its file.

        Resolution strategy:

        1. Strip surrounding underscores and normalise path separators.
        2. Look for an exact file at ``wildcards_dir / tag.txt``.
        3. If not found, fall back to the file index by basename.
        4. Apply a path-traversal check — the resolved path must be inside
           *wildcards_dir* to prevent reading arbitrary files.
        5. Select a line according to *mode*:
           - ``"Random (No Repeat)"`` — use the deck cache (shuffle-then-pop).
           - ``"Deterministic (Seed)"`` — sort lines then pick with ``rng.choice``.
           - ``"Full Random"`` — pick with ``rng.choice`` (unsorted).

        Returns the original ``__tag__`` string unchanged if the file cannot be
        found or read, so that unresolved wildcards are visible in the output.

        Args:
            wildcard_tag: The tag string between the double underscores (e.g.
                ``"colors"`` or ``"autowildcards/neutral_colors_male"``).
            file_index: Index dict from :meth:`_build_file_index`.
            wildcards_dir: Absolute path to the wildcards root directory.
            mode: One of ``"Deterministic (Seed)"``, ``"Full Random"``,
                ``"Random (No Repeat)"``.
            rng: Seeded (or unseeded for random modes) :class:`random.Random` instance.

        Returns:
            A randomly selected line from the file, or the original
            ``"__tag__"`` string if the file could not be resolved.
        """
        clean_tag: str = wildcard_tag.strip("_").replace("\\", "/")

        if not clean_tag.endswith(".txt"):
            search_filename: str = clean_tag + ".txt"
        else:
            search_filename = clean_tag

        direct_path: str = os.path.join(wildcards_dir, search_filename)
        final_path: str | None = None

        if os.path.exists(direct_path):
            final_path = direct_path
        else:
            base_name: str = os.path.basename(search_filename)
            if base_name in file_index:
                candidate_rel_path: str = file_index[base_name][0]
                final_path = os.path.join(wildcards_dir, candidate_rel_path)
            else:
                return f"__{wildcard_tag}__"

        real_wildcards: str = os.path.realpath(wildcards_dir)
        real_final: str = os.path.realpath(final_path)
        # Prevent path traversal: resolved path must be within wildcards directory
        if not real_final.startswith(real_wildcards + os.sep) and real_final != real_wildcards:
            return f"__{wildcard_tag}__"

        if mode == "Random (No Repeat)":
            deck = WildcardReader._deck_cache
            try:
                current_mtime = os.path.getmtime(final_path)
            except OSError:
                return f"__{wildcard_tag}__"
            cached = deck.get(final_path)
            if cached is None or cached[0] != current_mtime or len(cached[1]) == 0:
                lines = self._get_file_lines(final_path)
                if lines is None:
                    return f"__{wildcard_tag}__"
                if not lines:
                    return ""
                shuffled = list(lines)
                rng.shuffle(shuffled)
                deck[final_path] = (current_mtime, shuffled)
                cached = deck[final_path]
            return cached[1].pop(0)
        else:
            lines = self._get_file_lines(final_path)
            if lines is None:
                return f"__{wildcard_tag}__"
            if not lines:
                return ""
            if mode == "Deterministic (Seed)":
                return rng.choice(sorted(lines))
            else:
                return rng.choice(lines)

    def process(self, text: str, mode: str, seed: int, delimiter: str, **kwargs: Any) -> tuple[str]:
        """Resolve all wildcard tokens in *text* and return the final string.

        Processing steps:

        1. Initialise the RNG: seeded with *seed* for Deterministic mode, unseeded
           for the two random modes.
        2. Build (or return cached) file index for the wildcards directory.
        3. Iteratively resolve ``__wildcard__`` tokens up to
           :data:`_MAX_WILDCARD_ITERATIONS` times.  Each pass resolves one unique
           tag at a time (sorted for determinism) until no resolvable tags remain
           or the iteration cap is hit.
        4. Resolve ``{choice1|choice2|...}`` inline choices with :data:`_CHOICE_PATTERN`
           (processed after all wildcard expansion, so wildcard values can themselves
           contain inline choices).
        5. Strip leading/trailing whitespace.
        6. Join Prependable Text, the resolved text, and Appendable Text with
           *delimiter*.

        Args:
            text: Input text containing ``__wildcard__`` tags and/or ``{a|b}`` choices.
            mode: Selection mode — ``"Deterministic (Seed)"``, ``"Full Random"``,
                or ``"Random (No Repeat)"``.
            seed: RNG seed (used in Deterministic mode only).
            delimiter: Separator string for prepend/append joining.
            **kwargs: Optional ``"Prependable Text"`` and ``"Appendable Text"`` strings.

        Returns:
            A 1-tuple ``(resolved_text,)`` containing the fully resolved string.
        """
        prepend_text: str = kwargs.get("Prependable Text", "")
        append_text: str = kwargs.get("Appendable Text", "")

        if mode == "Deterministic (Seed)":
            rng: random.Random = random.Random(seed)
        else:
            rng = random.Random()

        current_dir: str = os.path.dirname(os.path.realpath(__file__))
        wildcards_dir: str = os.path.join(current_dir, "wildcards")

        if not os.path.exists(wildcards_dir):
            os.makedirs(wildcards_dir, exist_ok=True)

        file_index = self._build_file_index(wildcards_dir)

        processed_text: str = text if text else ""

        iteration: int = 0
        max_iterations: int = _MAX_WILDCARD_ITERATIONS

        while iteration < max_iterations:
            matches: list[str] = list(set(_WILDCARD_PATTERN.findall(processed_text)))
            if not matches:
                break

            matches.sort()

            found_replacement: bool = False
            for match in matches:
                replacement: str = self._get_line_from_file(match, file_index, wildcards_dir, mode, rng)
                tag_str: str = f"__{match}__"
                if replacement == tag_str:
                    continue
                if tag_str in processed_text:
                    processed_text = processed_text.replace(tag_str, replacement, 1)
                    found_replacement = True
                    break

            if not found_replacement:
                break
            iteration += 1

        def _choice_replacer(m: re.Match[str]) -> str:
            inner = m.group(1)
            options = [s.strip() for s in inner.split("|") if s.strip()]
            return rng.choice(options) if options else m.group(0)

        processed_text = _CHOICE_PATTERN.sub(_choice_replacer, processed_text)

        processed_text = processed_text.strip()

        parts: list[str] = []
        if prepend_text and prepend_text.strip():
            parts.append(prepend_text.strip())
        if processed_text:
            parts.append(processed_text)
        if append_text and append_text.strip():
            parts.append(append_text.strip())

        final_output: str = delimiter.join(parts)

        return (final_output,)


NODE_CLASS_MAPPINGS = {
    "WildcardReader": WildcardReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WildcardReader": "Wildcard Reader",
}

__all__: list[str] = ["WildcardReader", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
