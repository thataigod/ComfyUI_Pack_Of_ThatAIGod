from typing import Any
from .Dynamic_Resolution_Picker import NODE_CLASS_MAPPINGS as DYN_CLASS, NODE_DISPLAY_NAME_MAPPINGS as DYN_DISPLAY
from .Wildcard_Reader import NODE_CLASS_MAPPINGS as WILD_CLASS, NODE_DISPLAY_NAME_MAPPINGS as WILD_DISPLAY
from .LLM_Node import LLM_Node
from .LLM_Fallback_Node import LLM_Fallback_Node
from .Sequential_Image_Loader import NODE_CLASS_MAPPINGS as SEQ_CLASS, NODE_DISPLAY_NAME_MAPPINGS as SEQ_DISPLAY
from .Truncate_LLM_Thinking import NODE_CLASS_MAPPINGS as TRUNC_CLASS, NODE_DISPLAY_NAME_MAPPINGS as TRUNC_DISPLAY
from .Upscale_By_Max_Side import NODE_CLASS_MAPPINGS as UP_CLASS, NODE_DISPLAY_NAME_MAPPINGS as UP_DISPLAY

LLM_CLASS: dict[str, Any] = {
    "LLM_Node": LLM_Node,
    "LLM_Fallback_Node": LLM_Fallback_Node
}
LLM_DISPLAY: dict[str, str] = {
    "LLM_Node": "LLM Chat (OpenRouter/Local)",
    "LLM_Fallback_Node": "LLM Fallback Switch"
}

NODE_CLASS_MAPPINGS: dict[str, Any] = {
    **DYN_CLASS, **WILD_CLASS, **LLM_CLASS, **SEQ_CLASS, **TRUNC_CLASS, **UP_CLASS
}

NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {
    **DYN_DISPLAY, **WILD_DISPLAY, **LLM_DISPLAY, **SEQ_DISPLAY, **TRUNC_DISPLAY, **UP_DISPLAY
}

WEB_DIRECTORY: str = "./js"

__all__: list[str] = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

print("------------------------------------")
print("✅ ComfyUI-Pack-Of-ThatAIGod loaded.")
print("------------------------------------")