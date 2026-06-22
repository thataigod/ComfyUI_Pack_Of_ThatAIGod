"""Package entry point for ComfyUI_Pack_Of_ThatAIGod.

This module is loaded by ComfyUI's custom-node loader.  It:

1. Inserts the node directory into ``sys.path`` so that sibling module imports
   (e.g. ``from _utils import ...``) resolve correctly.  See DECISIONS.md D11
   for the full explanation of why this is necessary.
2. Imports each node module via :func:`_utils.safe_import` so that a single
   broken node does not prevent the rest of the pack from loading.
3. Aggregates ``NODE_CLASS_MAPPINGS`` and ``NODE_DISPLAY_NAME_MAPPINGS`` from
   every successfully loaded module and exposes them to ComfyUI.
4. Exposes ``WEB_DIRECTORY`` so ComfyUI serves the ``js/`` folder as frontend
   JavaScript extensions (e.g. streaming preview widgets).
"""

import logging
import os
import sys
from typing import Any

# ComfyUI uses importlib with filesystem-path module names, so the
# package directory is NOT on sys.path by default.  Insert it so that
# sibling imports (from _utils, importlib.import_module) can resolve.
_node_dir: str = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _node_dir)

from _utils import safe_import  # noqa: E402

logger: logging.Logger = logging.getLogger("ThatAIGod")


__version__: str = "1.3.0"

NODE_CLASS_MAPPINGS: dict[str, Any] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

# Accumulates module names that failed to import; logged after the loop.
_import_errors: list[str] = []

_modules: list[str] = [
    "Dynamic_Resolution_Picker",
    "Image_Saver_Plus",
    "Resolution_Selector",
    "Sequential_Image_Loader",
    "Truncate_LLM_Thinking",
    "Upscale_By_Max_Side",
    "Wildcard_Reader",
    "LLM_Node",
    "LLM_Fallback_Node",
]

for mod_name in _modules:
    mod = safe_import(mod_name)
    if mod is not None:
        if hasattr(mod, "NODE_CLASS_MAPPINGS"):
            NODE_CLASS_MAPPINGS.update(mod.NODE_CLASS_MAPPINGS)
            NODE_DISPLAY_NAME_MAPPINGS.update(mod.NODE_DISPLAY_NAME_MAPPINGS)
    else:
        _import_errors.append(mod_name)

if _import_errors:
    for err in _import_errors:
        logger.warning("ComfyUI_Pack_Of_ThatAIGod: failed to import %s", err)

# Tells ComfyUI to serve files in ./js/ as frontend JavaScript extensions.
# The extension file js/dynamic_display.js registers streaming preview widgets,
# dynamic output labels, and wildcard dropdown auto-insert behaviour.
WEB_DIRECTORY: str = "./js"

__all__: list[str] = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
