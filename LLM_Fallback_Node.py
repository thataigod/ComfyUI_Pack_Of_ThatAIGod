from typing import Any


class LLM_Fallback_Node:
    RETURN_TYPES: tuple[str, ...] = ("STRING",)
    RETURN_NAMES: tuple[str, ...] = ("Final Text",)
    FUNCTION: str = "switch"
    CATEGORY: str = "ThatAIGod/LLM"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Original Input": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "Generated Text": ("STRING", {"forceInput": True}),
                "Status (Boolean)": ("BOOLEAN", {"default": False}),
            }
        }

    def switch(self, **kwargs: Any) -> tuple[str]:
        generated_text = kwargs.get("Generated Text", "")
        original_input = kwargs.get("Original Input", "")
        status = kwargs.get("Status (Boolean)", False)

        if generated_text is None:
            generated_text = ""
        if status is None:
            status = False

        if status and generated_text and generated_text.strip():
            return (generated_text,)
        return (original_input,)