import logging
from typing import Any

from .utils import get_logger, safe_import

__version__: str = "1.1.0"

logger: logging.Logger = get_logger()

NODE_CLASS_MAPPINGS: dict[str, Any] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

_import_errors: list[str] = []

_modules: list[str] = [
    "Dynamic_Resolution_Picker",
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

__all__: list[str] = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
