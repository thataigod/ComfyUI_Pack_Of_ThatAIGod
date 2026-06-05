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

_import_errors: list[str] = []

_modules: list[str] = [
    "Dynamic_Resolution_Picker",
    "Image_Saver_Plus",
    "Wildcard_Reader",
    "Sequential_Image_Loader",
    "Truncate_LLM_Thinking",
    "Upscale_By_Max_Side",
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
        logger.warning("ComfyUI-Pack-Of-ThatAIGod: failed to import %s", err)

WEB_DIRECTORY: str = "./js"

__all__: list[str] = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
