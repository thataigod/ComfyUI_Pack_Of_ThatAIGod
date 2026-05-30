# Architectural Decisions

This document records significant architectural and tooling decisions to prevent rework and provide context for future contributors.

## Decision Log

### D1: mypy CI Step Uses `/tmp` Copy Workaround

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** The repository directory is named `ComfyUI-Pack-Of-ThatAIGod`, containing hyphens. Python/mypy treats directories with `__init__.py` as packages, and hyphens are invalid in Python package names. Running `mypy *.py` from the project root fails with: `ComfyUI-Pack-Of-ThatAIGod contains __init__.py but is not a valid Python package name`.

**Decision:** Copy `.py` files to `/tmp/thatnode/` (a valid package name) before running mypy.

**Alternatives Considered:**
- `--explicit-package-bases` flag: Breaks glob expansion on some platforms.
- Renaming the repo directory: Not possible (GitHub repo name is fixed).
- `--namespace-packages`: Doesn't resolve the invalid package name error.

**Consequences:**
- CI step is 4 lines instead of 1, but it works reliably.
- Type stubs or local imports won't resolve in CI (mitigated by `--follow-imports=skip`).
- This approach was validated in the original codebase and has been reverted to after attempted simplification failed.

**Do NOT change this without testing on Ubuntu CI first.**

---

### D2: Retry Logic Uses `asyncio.sleep` Not `time.sleep`

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** The LLM streaming code bridges async `aiohttp` to sync via `_run_async_stream`. Retry logic in `_async_fetch_stream` (the async function) uses `await asyncio.sleep()` for backoff, not `time.sleep()`.

**Decision:** Use `asyncio.sleep` in the async context. Do NOT add `import time`.

**Consequences:**
- `import time` was added then removed because ruff flagged it as unused.
- Retry backoff is non-blocking within the event loop.

---

### D3: Response Cache Uses `OrderedDict` (Not `dict`)

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** `LLM_Node._response_cache` needs LRU eviction. Python 3.7+ `dict` preserves insertion order but lacks `move_to_end()`.

**Decision:** Use `collections.OrderedDict` for the LRU cache with `move_to_end()` on access and `popitem(last=False)` for eviction.

---

### D4: Wildcard File Content Cache Keyed by Path + mtime (with FIFO Eviction)

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** `WildcardReader` reads `.txt` files from disk on every `process()` call. File contents don't change often, but the index cache (which files exist) doesn't cache the actual content.

**Decision:** Add `_file_content_cache: dict[str, tuple[float, list[str]]]` mapping file path to `(mtime, lines)`. Cache invalidates when mtime changes.

**Cache eviction:** Bounded to `_MAX_CONTENT_CACHE_SIZE = 100` entries via FIFO eviction (`pop(next(iter(...)))`). 100 entries is sufficient for typical wildcard directories and prevents unbounded memory growth.

**Consequences:**
- Eliminates redundant disk reads for repeated wildcard resolution.
- On Windows, mtime granularity may be 1 second — tests use `os.utime()` to force mtime changes.
- Oldest entries are evicted first when the 100-entry limit is reached.

---

### D5: LLM_Node Uses Class-Level Mutable State

**Date:** 2026-05-30  
**Status:** Accepted (technical debt)  
**Context:** `LLM_Node._model_cache`, `_response_cache`, `_config_builder`, `_streamer` are class-level attributes shared across all instances.

**Decision:** Keep as-is. ComfyUI instantiates nodes as singletons, so class-level state works. Moving to instance state would require changes to how ComfyUI manages node lifecycles.

**Risks:**
- If ComfyUI ever instantiates multiple `LLM_Node` objects, caches would be shared unexpectedly.
- Mitigated by the fact that `_response_cache` is small (max 10) and `_model_cache` is read-only after first fetch.

---

### D6: Dependency Version Pins Use Range Constraints

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** Dependencies were unpinned (`>=` only), risking breakage with major version bumps.

**Decision:** Pin upper bounds: `Pillow<12`, `numpy<3`, `torch<3`, `aiohttp<4`.

**Consequences:**
- Prevents silent breakage from breaking changes in major versions.
- Users on very new versions may need to update pins.
- Major version bumps in these libraries often have breaking API changes.

---

### D7: Test Coverage Enforced at 100% Source

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** All 10 source (production) modules achieve 100% line coverage. The only uncovered lines are in test files (`if __name__ == "__main__"` guards), which is standard and expected.

**Decision:** Every source module must maintain 100% line coverage. Any new production code must include corresponding tests.

**Enforcement:** `pytest --cov-fail-under=100` runs in CI. The global total includes test files, so a 99% result is acceptable as long as all source modules show 100%.

---

### D8: `os.walk` on Every Call (M3) — Accepted

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** `WildcardReader._build_file_index` calls `os.walk()` on every `process()` call, even though mtime caching prevents re-reading file contents.

**Decision:** Keep as-is. Wildcard directories are small (typically <50 files). The overhead of `os.walk()` on a small directory is negligible (<1ms). The existing mtime-based cache prevents re-reading file contents, which is the expensive operation.

---

### D9: `_MAX_WILDCARD_ITERATIONS = 50` (L1) — Accepted

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** The maximum number of nested wildcard resolutions is hardcoded to 50.

**Decision:** Keep as-is. 50 iterations is generous for nested wildcards. In practice, most wildcard files reference at most 1-2 levels of nesting. Making this configurable adds UI complexity for no practical benefit.

---

### D10: Regex Not Pre-compiled (M4) — Accepted

**Date:** 2026-05-30  
**Status:** Accepted  
**Context:** `Truncate_LLM_Thinking.truncate()` calls `re.compile()` on every invocation.

**Decision:** Keep as-is. The `start_token` and `end_token` are user-configurable inputs, so the pattern changes per call. Python's `re` module caches compiled patterns internally (up to 512), making pre-compilation unnecessary.

---

### D11: Local Module Named `_utils.py` + `sys.path` Workaround

**Date:** 2026-05-30  
**Status:** Accepted (critical)  
**Context:** Two issues:

1. ComfyUI ships with its own `utils/` package at `ComfyUI/utils/__init__.py`. When a custom node directory contains `utils.py`, Python's import system resolves `from utils import ...` to ComfyUI's `utils` package instead of the local file, causing `ImportError: cannot import name 'safe_import' from 'utils'`.

2. ComfyUI loads custom nodes via `importlib.util.spec_from_file_location()` using a filesystem-path-derived module name (e.g. `C:\...\ComfyUI-Pack-Of-ThatAIGod` with dots replaced). The package directory is NOT added to `sys.path`, so sibling imports (`from _utils import ...`, `importlib.import_module("Dynamic_Resolution_Picker")`) fail with `ModuleNotFoundError`.

**Decision:**
- Rename local utility module to `_utils.py` (underscore prefix).
- Insert the node directory at `sys.path[0]` before any sibling imports in `__init__.py`.

**Alternatives Considered:**
- `node_utils.py`: Works but `_utils.py` is shorter and the underscore signals "internal".
- Relative imports (`from ._utils import`): Don't work reliably because ComfyUI doesn't load custom nodes as proper packages (module name is a mangled filesystem path).
- Relying on ComfyUI adding the directory to `sys.path`: Not guaranteed — experience shows it's not on the path.

**Consequences:**
- All imports use `from _utils import ...`.
- `__init__.py` has a `sys.path.insert(0, _node_dir)` before any import, with `# noqa: E402` since ruff flags module-level imports not at the top.
- The `_` prefix follows Python convention for private/internal modules.
- **This naming must NOT be changed back to `utils.py`** — it will break ComfyUI loading.

**Do NOT rename `_utils.py` back to `utils.py`.**

---

### D12: `_run_async` Replaces `_get_loop` + `run_until_complete`

**Date:** 2026-05-30  
**Status:** Accepted (critical)  
**Context:** The original async-to-sync bridge used `_get_loop()` which created a new event loop via `asyncio.new_event_loop()` + `asyncio.set_event_loop()`, cached it in a global `_LOOP`, and called `loop.run_until_complete()`. This fails when ComfyUI's own event loop is already running in the same thread, producing `RuntimeError: Cannot run the event loop while another loop is running`.

**Decision:** Replace with `_run_async(coro)` helper that:
1. Calls `asyncio.get_running_loop()` to detect if a loop is already running.
2. **No running loop:** Uses `asyncio.run(coro)` directly (creates, runs, and closes its own loop).
3. **Running loop present (ComfyUI):** Dispatches `asyncio.run(coro)` to a `ThreadPoolExecutor(max_workers=4)` so the new loop runs in its own thread without colliding.

**Alternatives Considered:**
- `loop.run_until_complete()` on a new loop: Fails when another loop is running in the same thread (the root cause).
- `asyncio.ensure_future()` on the running loop: Requires the calling code to be async-compatible, which ComfyUI node `generate()` methods are not (they are sync).
- `nest_asyncio` patch: External dependency, modifies global runtime behavior.

**Consequences:**
- Removes `_LOOP` global, `_get_loop()`, `_close_loop()`, and the `atexit` import.
- Adds `_EXECUTOR` module-level thread pool (`concurrent.futures.ThreadPoolExecutor`).
- Thread dispatch adds ~1ms overhead per call when ComfyUI's loop is running.
- The thread pool is bounded (max 4 workers), so concurrent LLM calls may queue.
- Tests cover both branches (`test_run_async_no_loop` and `test_run_async_from_loop`).
