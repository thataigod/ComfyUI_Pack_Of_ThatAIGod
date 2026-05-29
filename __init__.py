import logging
from typing import Any

__version__: str = "1.0.0"

logger: logging.Logger = logging.getLogger("ThatAIGod")

NODE_CLASS_MAPPINGS: dict[str, Any] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

_import_errors: list[str] = []

def _safe_import(module_name: str, attr: str) -> Any:
    try:
        return __import__(f".{module_name}", globals(), locals(), [attr], level=1)
    except ImportError as e:
        _import_errors.append(f"{module_name}: {e}")
        return None

_dyn = _safe_import("Dynamic_Resolution_Picker", "NODE_CLASS_MAPPINGS")
_wild = _safe_import("Wildcard_Reader", "NODE_CLASS_MAPPINGS")
_seq = _safe_import("Sequential_Image_Loader", "NODE_CLASS_MAPPINGS")
_trunc = _safe_import("Truncate_LLM_Thinking", "NODE_CLASS_MAPPINGS")
_up = _safe_import("Upscale_By_Max_Side", "NODE_CLASS_MAPPINGS")

try:
    from .LLM_Node import LLM_Node
except ImportError as e:
    _import_errors.append(f"LLM_Node: {e}")
    LLM_Node = None

try:
    from .LLM_Fallback_Node import LLM_Fallback_Node
except ImportError as e:
    _import_errors.append(f"LLM_Fallback_Node: {e}")
    LLM_Fallback_Node = None

if _dyn:
    NODE_CLASS_MAPPINGS.update(_dyn.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_dyn.NODE_DISPLAY_NAME_MAPPINGS)
if _wild:
    NODE_CLASS_MAPPINGS.update(_wild.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_wild.NODE_DISPLAY_NAME_MAPPINGS)
if _seq:
    NODE_CLASS_MAPPINGS.update(_seq.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_seq.NODE_DISPLAY_NAME_MAPPINGS)
if _trunc:
    NODE_CLASS_MAPPINGS.update(_trunc.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_trunc.NODE_DISPLAY_NAME_MAPPINGS)
if _up:
    NODE_CLASS_MAPPINGS.update(_up.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_up.NODE_DISPLAY_NAME_MAPPINGS)

if LLM_Node is not None:
    NODE_CLASS_MAPPINGS["LLM_Node"] = LLM_Node
    NODE_DISPLAY_NAME_MAPPINGS["LLM_Node"] = "LLM Chat (OpenRouter/Local)"
if LLM_Fallback_Node is not None:
    NODE_CLASS_MAPPINGS["LLM_Fallback_Node"] = LLM_Fallback_Node
    NODE_DISPLAY_NAME_MAPPINGS["LLM_Fallback_Node"] = "LLM Fallback Switch"

if _import_errors:
    for err in _import_errors:
        logger.warning("ComfyUI-Pack-Of-ThatAIGod: failed to import %s", err)

WEB_DIRECTORY: str = "./js"

__all__: list[str] = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

print("------------------------------------")
print("✅ ComfyUI-Pack-Of-ThatAIGod loaded.")
print("------------------------------------")