import re
from typing import Any


class TruncateThinking:
    DESCRIPTION = "Removes thinking/reasoning blocks (e.g. <think>...</think>) from LLM output. Returns cleaned text and the extracted thinking content separately."

    RETURN_TYPES: tuple[str, ...] = ("STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Cleaned Text", "Thinking Content")
    FUNCTION: str = "truncate"
    CATEGORY: str = "ThatAIGod/Text Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Text": ("STRING", {"forceInput": True}),
                "Start Token": (
                    "STRING",
                    {"default": "<think>", "multiline": False},
                ),
                "End Token": (
                    "STRING",
                    {"default": "</think>", "multiline": False},
                ),
            }
        }

    @staticmethod
    def _truncate_long_text(
        text: str, start_token: str, end_token: str, max_length: int = 100000
    ) -> str:
        if len(text) <= max_length:
            return text

        safe_end = max_length
        last_end = text.rfind(end_token, 0, max_length)
        if last_end != -1:
            safe_end = last_end + len(end_token)
        # Ensure we don't cut in the middle of a thinking block

        search_start = last_end + len(end_token) if last_end != -1 else 0
        next_start = text.find(start_token, search_start, max_length)
        if next_start != -1:
            safe_end = next_start

        return text[:safe_end]

    def truncate(self, **kwargs: Any) -> tuple[str, str]:
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
