"""LLM Fallback Switch node for ComfyUI.

Provides :class:`LLM_Fallback_Node`, a simple routing node that passes the
LLM-generated text through when generation succeeded, or falls back to the
original input text when it did not.

This is useful in workflows where the LLM node is optional — connect the
Fallback Switch between the LLM node and downstream nodes so the workflow
continues cleanly even if the LLM call fails.
"""

from typing import Any


class LLM_Fallback_Node:
    """Routes between LLM output and a fallback input based on the LLM status flag.

    If the LLM node's ``Status (Boolean)`` output is ``True`` *and* the generated
    text is non-empty, the generated text is returned.  Otherwise the
    ``Original Input`` is returned unchanged.
    """

    DESCRIPTION = (
        "Routes between the original input and the generated LLM output based on the status boolean from the LLM node."
    )

    RETURN_TYPES: tuple[str, ...] = ("STRING",)
    RETURN_NAMES: tuple[str, ...] = ("Final Text",)
    FUNCTION: str = "switch"
    CATEGORY: str = "ThatAIGod/LLM"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Original Input": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "The fallback text returned when the LLM did not produce a result.",
                    },
                ),
            },
            "optional": {
                "Generated Text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Connect to the 'Generated Text' output of an LLM Chat node.",
                    },
                ),
                "Status (Boolean)": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Connect to the 'Status (Boolean)' output of an LLM Chat node.",
                    },
                ),
            },
        }

    def switch(self, **kwargs: Any) -> tuple[str, ...]:
        """Return the LLM output if successful, otherwise the original input.

        The LLM output is used only when *both* of the following are true:

        * ``Status (Boolean)`` is ``True`` (the LLM generation succeeded).
        * ``Generated Text`` is non-empty after stripping whitespace.

        If either condition is not met, ``Original Input`` is returned.

        Args:
            **kwargs: ComfyUI widget values.  Expected keys: ``"Original Input"``,
                ``"Generated Text"`` (optional), ``"Status (Boolean)"`` (optional).

        Returns:
            A 1-tuple containing the selected text string.
        """
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


NODE_CLASS_MAPPINGS = {
    "LLM_Fallback_Node": LLM_Fallback_Node,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LLM_Fallback_Node": "LLM Fallback Switch",
}

__all__: list[str] = ["LLM_Fallback_Node", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
