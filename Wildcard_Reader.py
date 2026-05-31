import logging
import os
import random
import re
from typing import Any

logger: logging.Logger = logging.getLogger("ThatAIGod")

_WILDCARD_PATTERN: re.Pattern[str] = re.compile(r"__([a-zA-Z0-9_\-\/\\\.]+)__")
_CHOICE_PATTERN: re.Pattern[str] = re.compile(r"\{([^}]+)\}")
_MAX_WILDCARD_ITERATIONS: int = 50
_MAX_CONTENT_CACHE_SIZE: int = 100


class WildcardReader:
    """Resolves __wildcard__ tokens in text with random lines from matching .txt files.

    Supports deterministic (seed-based), full random, and no-repeat deck modes.
    Files are cached by mtime for performance.
    """

    DESCRIPTION = "Replaces __wildcard__ tokens in text with random lines from matching text files in the wildcards directory. Supports deterministic (seed-based), full random, and no-repeat deck modes."

    _file_index_cache: dict[str, dict[str, list[str]]] = {}
    _file_mtimes: dict[str, dict[str, float]] = {}
    _file_content_cache: dict[str, tuple[float, list[str]]] = {}
    _deck_cache: dict[str, tuple[float, list[str]]] = {}

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
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
                    },
                ),
                "Select to add Wildcard": (options_list,),
                "mode": (
                    ["Deterministic (Seed)", "Full Random", "Random (No Repeat)"],
                    {"default": "Deterministic (Seed)"},
                ),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "delimiter": ("STRING", {"default": ", "}),
            },
            "optional": {
                "Prependable Text": ("STRING", {"forceInput": True}),
                "Appendable Text": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES: tuple[str, ...] = ("STRING",)
    RETURN_NAMES: tuple[str, ...] = ("Text",)
    FUNCTION: str = "process"
    CATEGORY: str = "ThatAIGod/Text Utils"

    @classmethod
    def IS_CHANGED(cls, text: str, mode: str, seed: int, delimiter: str, **kwargs: Any) -> float | int:
        if mode != "Deterministic (Seed)":
            return float("nan")
        return seed

    def _build_file_index(self, wildcards_dir: str) -> dict[str, list[str]]:
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
