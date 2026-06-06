"""Truncate LLM Thinking node for ComfyUI.

Provides :class:`TruncateThinking`, which removes thinking/reasoning blocks from
LLM output text.  The start and end tokens are configurable so the node works with
any model that wraps its reasoning in delimiters (e.g. ``<think>...</think>`` for
DeepSeek-R1 style models, or custom tags for other providers).

Returns both the cleaned text and the extracted thinking content as separate outputs
so downstream nodes can use either or both.
"""

import re
from typing import Any


class TruncateThinking:
    """Removes thinking/reasoning blocks from LLM output using configurable token markers.

    Returns cleaned text and extracted thinking content separately.
    Handles multiple thinking blocks per response (joined with ``\\n\\n``).
    """

    DESCRIPTION = "Removes thinking/reasoning blocks (e.g. <think>...</think>) from LLM output. Returns cleaned text and the extracted thinking content separately."

    RETURN_TYPES: tuple[str, ...] = ("STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Cleaned Text", "Thinking Content")
    FUNCTION: str = "truncate"
    CATEGORY: str = "ThatAIGod/Text Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        """Return the ComfyUI input schema for this node."""
        return {
            "required": {
                "Text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "LLM output text that may contain thinking/reasoning blocks.",
                    },
                ),
                "Start Token": (
                    "STRING",
                    {
                        "default": "<think>",
                        "multiline": False,
                        "tooltip": "Opening delimiter of thinking blocks (default: <think>).",
                    },
                ),
                "End Token": (
                    "STRING",
                    {
                        "default": "</think>",
                        "multiline": False,
                        "tooltip": "Closing delimiter of thinking blocks (default: </think>).",
                    },
                ),
            }
        }

    @staticmethod
    def _truncate_long_text(text: str, start_token: str, end_token: str, max_length: int = 100000) -> str:
        """Safely truncate *text* to at most *max_length* characters.

        Simple character-count truncation risks cutting in the middle of a thinking
        block, which would cause the regex in :meth:`truncate` to match an unclosed
        block and corrupt the output.  This method instead finds a safe truncation
        point:

        1. If the text is within *max_length*, return it unchanged.
        2. Find the last complete ``end_token`` at or before *max_length* characters.
           Truncate just after it so the final block is always closed.
        3. If there is a ``start_token`` between the last ``end_token`` and
           *max_length*, truncate just before that start token to avoid including a
           partial (unclosed) thinking block.

        Args:
            text: The raw LLM output string.
            start_token: The opening delimiter (e.g. ``"<think>"``).
            end_token: The closing delimiter (e.g. ``"</think>"``).
            max_length: Maximum number of characters to retain.

        Returns:
            The truncated text, guaranteed not to contain a partial thinking block
            that starts but does not close within the returned slice.
        """
        if len(text) <= max_length:
            return text

        safe_end = max_length
        last_end = text.rfind(end_token, 0, max_length)
        if last_end != -1:
            safe_end = last_end + len(end_token)

        # If there is a new opening token between the last closing token and max_length,
        # truncate just before it to avoid an unclosed thinking block.
        search_start = last_end + len(end_token) if last_end != -1 else 0
        next_start = text.find(start_token, search_start, max_length)
        if next_start != -1:
            safe_end = next_start

        return text[:safe_end]

    def truncate(self, **kwargs: Any) -> tuple[str, str]:
        """Remove all thinking blocks from *text* and return cleaned and extracted content.

        Processing steps:

        1. Long inputs (> 100,000 characters) are safely truncated by
           :meth:`_truncate_long_text` to avoid catastrophic regex backtracking.
        2. A regex matching ``start_token ... end_token`` (dotall) extracts all
           thinking blocks.
        3. The extracted blocks are joined with ``"\\n\\n"`` to form the
           ``Thinking Content`` output.
        4. All thinking blocks are removed from the text to produce ``Cleaned Text``.

        .. note::
            The regex is compiled on every call because ``start_token`` and
            ``end_token`` are user-configurable.  Python's ``re`` module caches
            up to 512 compiled patterns internally, so this has negligible overhead.
            See DECISIONS.md D10.

        Args:
            **kwargs: ComfyUI widget values.  Expected keys: ``"Text"``,
                ``"Start Token"``, ``"End Token"``.

        Returns:
            A 2-tuple ``(cleaned_text, thinking_content)``:

            * ``cleaned_text`` — the input with all thinking blocks removed and
              leading/trailing whitespace stripped.
            * ``thinking_content`` — the concatenated content of all thinking
              blocks (without delimiters), joined by ``"\\n\\n"``.  Empty string
              if no blocks were found.
        """
        text: str = kwargs.get("Text", "")
        start_token: str = kwargs.get("Start Token", "<think>")
        end_token: str = kwargs.get("End Token", "</think>")

        if not text:
            return ("", "")

        text = self._truncate_long_text(text, start_token, end_token)

        pattern = re.compile(
            re.escape(start_token) + r"(.*?)" + re.escape(end_token),
            flags=re.DOTALL,
        )

        thoughts_found: list[str] = pattern.findall(text)
        thinking_content: str = "\n\n".join(thoughts_found).strip()

        cleaned_text: str = pattern.sub("", text).strip()

        return (cleaned_text, thinking_content)


NODE_CLASS_MAPPINGS = {
    "TruncateThinking": TruncateThinking,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TruncateThinking": "Truncate LLM Thinking",
}

__all__: list[str] = ["TruncateThinking", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
