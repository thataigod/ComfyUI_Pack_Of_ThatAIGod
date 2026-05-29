from typing import Any

__version__: str = "1.0.0"

# Lazy-loaded — ComfyUI triggers these only at runtime; CI imports modules directly
NODE_CLASS_MAPPINGS: dict[str, Any] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

try:
    from .Dynamic_Resolution_Picker import NODE_CLASS_MAPPINGS as _dyn_c, NODE_DISPLAY_NAME_MAPPINGS as _dyn_d
    from .Wildcard_Reader import NODE_CLASS_MAPPINGS as _wild_c, NODE_DISPLAY_NAME_MAPPINGS as _wild_d
    from .LLM_Node import LLM_Node
    from .LLM_Fallback_Node import LLM_Fallback_Node
    from .Sequential_Image_Loader import NODE_CLASS_MAPPINGS as _seq_c, NODE_DISPLAY_NAME_MAPPINGS as _seq_d
    from .Truncate_LLM_Thinking import NODE_CLASS_MAPPINGS as _trunc_c, NODE_DISPLAY_NAME_MAPPINGS as _trunc_d
    from .Upscale_By_Max_Side import NODE_CLASS_MAPPINGS as _up_c, NODE_DISPLAY_NAME_MAPPINGS as _up_d

    _llm_class: dict[str, Any] = {
        "LLM_Node": LLM_Node,
        "LLM_Fallback_Node": LLM_Fallback_Node
    }
    _llm_display: dict[str, str] = {
        "LLM_Node": "LLM Chat (OpenRouter/Local)",
        "LLM_Fallback_Node": "LLM Fallback Switch"
    }

    NODE_CLASS_MAPPINGS = {**_dyn_c, **_wild_c, **_llm_class, **_seq_c, **_trunc_c, **_up_c}
    NODE_DISPLAY_NAME_MAPPINGS = {**_dyn_d, **_wild_d, **_llm_display, **_seq_d, **_trunc_d, **_up_d}
except ImportError:
    pass

WEB_DIRECTORY: str = "./js"

__all__: list[str] = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

print("------------------------------------")
print("✅ ComfyUI-Pack-Of-ThatAIGod loaded.")
print("------------------------------------")