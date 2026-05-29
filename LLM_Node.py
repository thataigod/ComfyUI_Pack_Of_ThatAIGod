import os
import json
import hashlib
import urllib.request
import urllib.error
from urllib.parse import urlparse
import socket
import io
import base64
import time
import logging
from collections import OrderedDict
from typing import Any, Iterator
from PIL import Image
import numpy as np
import torch
from server import PromptServer

from llm_utils import (
    LlmConfigBuilder, LlmStreamer,
    CACHE_MAX_SIZE, MAX_ERROR_BODY_LENGTH,
    DEFAULT_MODELS,
    encode_image_to_base64 as _encode_image_to_base64,
    fetch_openrouter_credits as _fetch_openrouter_credits,
    push_error_to_ui as _push_error_to_ui,
)

logger = logging.getLogger("ThatAIGod")

MODEL_FETCH_TIMEOUT: int = 2
MAX_MODELS_IN_DROPDOWN: int = 200


class LLM_Node:
    DESCRIPTION = "Sends prompts to OpenRouter or a local LLM server with streaming response, vision support, caching, and credit checking."

    _model_cache: list[str] | None = None
    _response_cache: OrderedDict[Any, tuple[str, bool, str]] = OrderedDict()
    _cache_max_size: int = CACHE_MAX_SIZE

    _config_builder: LlmConfigBuilder = LlmConfigBuilder()
    _streamer: LlmStreamer = LlmStreamer()

    @classmethod
    def get_initial_model_list(cls) -> list[str]:
        if cls._model_cache is not None:
            return cls._model_cache

        defaults: list[str] = list(DEFAULT_MODELS)

        try:
            url: str = "https://openrouter.ai/api/v1/models"
            req: urllib.request.Request = urllib.request.Request(
                url, headers={"User-Agent": "ThatAIGod-ComfyUI-Node/1.0"}
            )
            with urllib.request.urlopen(req, timeout=MODEL_FETCH_TIMEOUT) as response:
                data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
                if "data" in data and isinstance(data["data"], list):
                    fetched_models: list[str] = [m["id"] for m in data["data"]]
                    cls._model_cache = fetched_models[:MAX_MODELS_IN_DROPDOWN]
                    return cls._model_cache
                logger.warning("Unexpected API response format from OpenRouter models endpoint")
        except Exception as e:
            logger.warning("Failed to fetch model list from OpenRouter: %s", e)

        return defaults

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        model_list: list[str] = cls.get_initial_model_list()

        return {
            "required": {
                "Mode": (["OpenRouter", "Local"], {"default": "OpenRouter"}),
                "Model": (model_list, {"default": "mistralai/devstral-2512:free"}),
                "System Prompt": (
                    "STRING",
                    {"multiline": True, "default": "You are a helpful assistant."},
                ),
                "User Prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamic": True,
                        "placeholder": "Input text or connect input...",
                    },
                ),
                "Temperature": (
                    "FLOAT",
                    {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01},
                ),
                "Max Tokens": ("INT", {"default": 1024, "min": 1, "max": 128000}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "Timeout (Seconds)": ("INT", {"default": 30, "min": 1, "max": 300}),
            },
            "optional": {
                "API Key Env Var": (
                    ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_BACKUP", "OPENROUTER_API_KEY_EXTRA"],
                    {"default": "OPENROUTER_API_KEY"},
                ),
                "Local URL": ("STRING", {"default": "http://localhost:1234/v1"}),
                "Image(s)": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES: tuple[str, ...] = ("STRING", "BOOLEAN", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Generated Text", "Status (Boolean)", "Information")
    FUNCTION: str = "generate"
    CATEGORY: str = "ThatAIGod/LLM"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs: Any) -> bool | str:
        mode: str = kwargs.get("Mode", "OpenRouter")
        api_key_env: str = kwargs.get("API Key Env Var", "OPENROUTER_API_KEY")
        temperature: float = kwargs.get("Temperature", 0.7)
        max_tokens: int = kwargs.get("Max Tokens", 1024)

        if mode == "OpenRouter" and not os.environ.get(api_key_env.strip()):
            return f"API key not found in environment variable '{api_key_env}'"

        if temperature < 0.0 or temperature > 2.0:
            return "Temperature must be between 0.0 and 2.0"

        if max_tokens < 1:
            return "Max Tokens must be at least 1"

        return True

    def encode_image_to_base64(self, image_tensor: torch.Tensor) -> str:
        return _encode_image_to_base64(image_tensor)

    def fetch_openrouter_credits(self, api_key: str) -> str | None:
        return _fetch_openrouter_credits(api_key)

    def push_error_to_ui(self, unique_id: str | None, error_msg: str) -> None:
        _push_error_to_ui(unique_id, error_msg)

    def _build_config(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return self._config_builder.build_config(kwargs)

    def _resolve_api_config(self, cfg: dict[str, Any]) -> tuple[str, str, str | None]:
        return self._config_builder.resolve_api_config(cfg)

    def _build_messages(self, system_prompt: str, user_prompt: str, b64_image: str | None) -> list[dict[str, Any]]:
        return self._config_builder.build_messages(system_prompt, user_prompt, b64_image)

    def _build_payload(self, cfg: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
        return self._config_builder.build_payload(cfg, messages)

    def _stream_response(self, url: str, payload: dict[str, Any], api_key: str, timeout: int) -> Iterator[bytes]:
        return self._streamer.stream_response(url, payload, api_key, timeout)

    def _parse_stream_chunk(self, line: bytes) -> str | None:
        return self._streamer.parse_stream_chunk(line)

    def _cache_get(self, key: tuple[Any, ...]) -> tuple[str, bool, str] | None:
        if key in self._response_cache:
            self._response_cache.move_to_end(key)
            return self._response_cache[key]
        return None

    def _cache_put(self, key: tuple[Any, ...], value: tuple[str, bool, str]) -> None:
        self._response_cache[key] = value
        if len(self._response_cache) > LLM_Node._cache_max_size:
            self._response_cache.popitem(last=False)

    def generate(self, **kwargs: Any) -> tuple[str, bool, str]:
        cfg: dict[str, Any] = self._build_config(kwargs)
        unique_id = cfg["unique_id"]

        if unique_id:
            PromptServer.instance.send_sync(
                "that_ai_god.stream", {"node": unique_id, "type": "start"}
            )

        b64_image: str | None = None
        if cfg["vision_image"] is not None:
            try:
                b64_image = self.encode_image_to_base64(cfg["vision_image"])
            except Exception as e:
                err = f"Error processing image: {str(e)}"
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)

        image_hash: str | None = (
            hashlib.md5(b64_image.encode()).hexdigest() if b64_image else None
        )
        # Cache key includes all inputs + image hash so identical prompts with different images don't collide
        cache_key: tuple[Any, ...] = (
            cfg["mode"],
            cfg["model_name"],
            cfg["system_prompt"],
            cfg["user_prompt"],
            cfg["temperature"],
            cfg["max_tokens"],
            cfg["seed"],
            image_hash,
        )

        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached LLM response for seed %s", cfg["seed"])
            cached_text, status, info = cached
            if unique_id:
                PromptServer.instance.send_sync(
                    "that_ai_god.stream",
                    {"node": unique_id, "type": "update", "delta": cached_text},
                )
            return (cached_text, status, info)

        base_url, api_key, api_error = self._resolve_api_config(cfg)
        if api_error:
            self.push_error_to_ui(unique_id, api_error)
            return ("", False, api_error)

        messages = self._build_messages(cfg["system_prompt"], cfg["user_prompt"], b64_image)
        payload = self._build_payload(cfg, messages)

        start_time: float = time.time()

        try:
            full_content: list[str] = []
            for line in self._stream_response(
                base_url, payload, api_key, cfg["timeout_seconds"]
            ):
                content = self._parse_stream_chunk(line)
                if content is None:
                    break
                if content:
                    full_content.append(content)
                    if unique_id:
                        PromptServer.instance.send_sync(
                            "that_ai_god.stream",
                            {"node": unique_id, "type": "update", "delta": content},
                        )

            end_time: float = time.time()
            latency: float = end_time - start_time
            generated_content: str = "".join(full_content).strip()

            info_parts: list[str] = [f"Latency: {latency:.2f}s"]
            if cfg["mode"] == "OpenRouter":
                credits: str | None = self.fetch_openrouter_credits(api_key)
                if credits:
                    info_parts.append(f"Credits: {credits}")
            final_info: str = " | ".join(info_parts)

            result: tuple[str, bool, str] = (generated_content, True, final_info)
            self._cache_put(cache_key, result)
            return result

        except urllib.error.HTTPError as e:
            error_body: str = e.read().decode("utf-8")[:MAX_ERROR_BODY_LENGTH]
            err_msg = f"HTTP Error {e.code}: {e.reason}\nDetails: {error_body}"
            self.push_error_to_ui(unique_id, err_msg)
            return ("", False, err_msg)

        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout):
                err = "Error: Request timed out."
            else:
                err = f"Connection Error: {e.reason}"
            self.push_error_to_ui(unique_id, err)
            return ("", False, err)

        except Exception as e:
            err = f"Unknown Error: {str(e)}"
            self.push_error_to_ui(unique_id, err)
            return ("", False, err)


NODE_CLASS_MAPPINGS = {
    "LLM_Node": LLM_Node,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LLM_Node": "LLM Chat (OpenRouter/Local)",
}
