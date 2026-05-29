import re
from typing import Any


class TruncateThinking:
    RETURN_TYPES: tuple[str, ...] = ("STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Cleaned Text", "Thinking Content")
    FUNCTION: str = "truncate"
    CATEGORY: str = "ThatAIGod/Text Utils"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "Text": ("STRING", {"forceInput": True}),
                "Start Token": ("STRING", {"default": "<think>", "multiline": False}),
                "End Token": ("STRING", {"default": "</think>", "multiline": False}),
            }
        }

    def truncate(self, **kwargs: Any) -> tuple[str, str]:
        text: str = kwargs.get("Text", "")
        start_token: str = kwargs.get("Start Token", "<think>")
        end_token: str = kwargs.get("End Token", "</think>")

        if not text:
            return ("", "")

        max_length: int = 100000
        if len(text) > max_length:
            safe_end: int = max_length
            end_escaped: str = re.escape(end_token)
            last_complete_end: int = text.rfind(end_token, 0, max_length)
            if last_complete_end != -1:
                safe_end = last_complete_end + len(end_token)
            start_escaped_for_check: str = re.escape(start_token)
            incomplete_start: int = text.rfind(start_token, 0, max_length)
            if incomplete_start != -1 and incomplete_start > text.rfind(end_token, 0, max_length):
                safe_end = incomplete_start
            text = text[:safe_end]

        pattern = re.compile(
            re.escape(start_token) + r"(.*?)" + re.escape(end_token),
            flags=re.DOTALL
        )

        thoughts_found: list[str] = pattern.findall(text)
        thinking_content: str = "\n\n".join(thoughts_found).strip()

        cleaned_text: str = pattern.sub("", text).strip()

        return (cleaned_text, thinking_content)

NODE_CLASS_MAPPINGS = {
    "TruncateThinking": TruncateThinking
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TruncateThinking": "Truncate LLM Thinking"
}