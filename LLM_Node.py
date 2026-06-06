"""LLM Chat node for ComfyUI.

Provides :class:`LLM_Node`, which connects to OpenRouter or a local LLM server
(e.g. LM Studio) and generates text responses with:

* Real-time streaming preview via WebSocket (``that_ai_god.stream`` events)
* Vision support — pass an image tensor to multimodal models
* LRU response cache (last 10 requests) for fast re-runs
* Separate extraction of reasoning / thinking content
* Credit balance display for OpenRouter accounts

See DECISIONS.md D3 (LRU cache), D5 (class-level state), D12 (async bridge).
"""

import hashlib
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

import torch
from server import PromptServer

from llm_utils import (
    CACHE_MAX_SIZE,
    DEFAULT_MODELS,
    MAX_ERROR_BODY_LENGTH,
    LlmConfigBuilder,
    LlmStreamer,
)
from llm_utils import (
    encode_image_to_base64 as _encode_image_to_base64,
)
from llm_utils import (
    fetch_openrouter_credits as _fetch_openrouter_credits,
)
from llm_utils import (
    push_error_to_ui as _push_error_to_ui,
)

logger = logging.getLogger("ThatAIGod")

# Timeout (seconds) for the initial model-list fetch from OpenRouter at startup.
# Kept deliberately short so that ComfyUI loads quickly even when offline.
MODEL_FETCH_TIMEOUT: int = 2
# Cap on the number of models shown in the dropdown to avoid UI sluggishness.
MAX_MODELS_IN_DROPDOWN: int = 200


class LLM_Node:
    """ComfyUI node for LLM chat via OpenRouter or local servers.

    Supports streaming responses, vision (image) inputs, response caching,
    and credit balance display for OpenRouter.

    Class-level attributes are shared across all instances because ComfyUI
    treats nodes as effectively singletons.  See DECISIONS.md D5.
    """

    DESCRIPTION = "Sends prompts to OpenRouter or a local LLM server with streaming response, vision support, caching, and credit checking."

    _model_cache: list[str] | None = None
    _response_cache: OrderedDict[Any, tuple[str, bool, str, str]] = OrderedDict()
    _cache_max_size: int = CACHE_MAX_SIZE

    _config_builder: LlmConfigBuilder = LlmConfigBuilder()
    _streamer: LlmStreamer = LlmStreamer()

    @classmethod
    def get_initial_model_list(cls) -> list[str]:
        """Fetch and cache the list of available OpenRouter models.

        On first call, attempts a short (``MODEL_FETCH_TIMEOUT`` second) HTTP request
        to the OpenRouter models endpoint.  The result is stored in the class-level
        ``_model_cache``.  On subsequent calls the cached list is returned immediately.

        Falls back to :data:`~llm_utils.DEFAULT_MODELS` if the network request fails
        or the response is malformed.  The returned list is capped at
        ``MAX_MODELS_IN_DROPDOWN`` entries to keep the dropdown responsive.

        Returns:
            List of model ID strings (e.g. ``["openai/gpt-4o", ...]``).
        """
        if cls._model_cache is not None:
            return cls._model_cache

        defaults: list[str] = list(DEFAULT_MODELS)

        try:
            url: str = "https://openrouter.ai/api/v1/models"
            req: urllib.request.Request = urllib.request.Request(url, headers={"User-Agent": "ThatAIGod-ComfyUI-Node/1.0"})
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
        """Return the ComfyUI input schema for this node.

        Fetches the model list (cached after first call) and exposes all LLM
        configuration parameters as typed widgets with descriptive tooltips.
        """
        model_list: list[str] = cls.get_initial_model_list()

        return {
            "required": {
                "Mode": (
                    ["OpenRouter", "Local"],
                    {
                        "default": "OpenRouter",
                        "tooltip": "OpenRouter uses the cloud API; Local connects to a running LM Studio (or compatible) server.",
                    },
                ),
                "Model": (
                    model_list,
                    {
                        "default": "mistralai/devstral-2512:free",
                        "tooltip": "Model ID. Use 'Refresh Models' to fetch the latest list from OpenRouter or your local server.",
                    },
                ),
                "System Prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "You are a helpful assistant.",
                        "tooltip": "System-level instruction sent before the user message. Sets the assistant's persona and behaviour.",
                    },
                ),
                "User Prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamic": True,
                        "placeholder": "Input text or connect input...",
                        "tooltip": "The user's input to the LLM. Accepts dynamic connections from other nodes.",
                    },
                ),
                "Temperature": (
                    "FLOAT",
                    {
                        "default": 0.7,
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.01,
                        "tooltip": "Sampling temperature. 0.0 = deterministic/greedy, 2.0 = maximum randomness.",
                    },
                ),
                "Max Tokens": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 1,
                        "max": 128000,
                        "tooltip": "Maximum number of tokens to generate in the response.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "tooltip": (
                            "Seed for reproducible outputs. "
                            "Seed 0 is treated as 'no seed' and omitted from the request; "
                            "use any non-zero value for deterministic generation."
                        ),
                    },
                ),
                "Timeout (Seconds)": (
                    "INT",
                    {
                        "default": 30,
                        "min": 1,
                        "max": 300,
                        "tooltip": "Socket connect timeout in seconds. Increase for slow models or large responses.",
                    },
                ),
            },
            "optional": {
                "API Key Env Var": (
                    ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_BACKUP", "OPENROUTER_API_KEY_EXTRA"],
                    {
                        "default": "OPENROUTER_API_KEY",
                        "tooltip": "Name of the environment variable holding your OpenRouter API key.",
                    },
                ),
                "Local URL": (
                    "STRING",
                    {
                        "default": "http://localhost:1234/v1",
                        "tooltip": "Base URL of the local LLM server (must be localhost or 127.0.0.1 for security).",
                    },
                ),
                "Image(s)": (
                    "IMAGE",
                    {"tooltip": "Optional image input for vision-capable models. Maximum 8192×8192 pixels."},
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES: tuple[str, ...] = ("STRING", "BOOLEAN", "STRING", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("Generated Text", "Status (Boolean)", "Information", "Reasoning Content")
    FUNCTION: str = "generate"
    CATEGORY: str = "ThatAIGod/LLM"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs: Any) -> bool | str:
        """Validate node inputs before execution.

        Called by ComfyUI before :meth:`generate`.  Returns ``True`` if all
        inputs are valid, or an error string that ComfyUI displays to the user.

        Checks:
        - OpenRouter mode requires the selected API key env var to be set.
        - Temperature must be in ``[0.0, 2.0]``.
        - Max Tokens must be ≥ 1.

        Returns:
            ``True`` on success, or a human-readable error string on failure.
        """
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
        """Delegate to :func:`llm_utils.encode_image_to_base64`."""
        return _encode_image_to_base64(image_tensor)

    def fetch_openrouter_credits(self, api_key: str) -> str | None:
        """Delegate to :func:`llm_utils.fetch_openrouter_credits`."""
        return _fetch_openrouter_credits(api_key)

    def push_error_to_ui(self, unique_id: str | None, error_msg: str) -> None:
        """Delegate to :func:`llm_utils.push_error_to_ui`."""
        _push_error_to_ui(unique_id, error_msg)

    def _build_config(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Delegate to :meth:`LlmConfigBuilder.build_config`."""
        return self._config_builder.build_config(kwargs)

    def _resolve_api_config(self, cfg: dict[str, Any]) -> tuple[str, str, str | None]:
        """Delegate to :meth:`LlmConfigBuilder.resolve_api_config`."""
        return self._config_builder.resolve_api_config(cfg)

    def _build_messages(self, system_prompt: str, user_prompt: str, b64_image: str | None) -> list[dict[str, Any]]:
        """Delegate to :meth:`LlmConfigBuilder.build_messages`."""
        return self._config_builder.build_messages(system_prompt, user_prompt, b64_image)

    def _build_payload(self, cfg: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Delegate to :meth:`LlmConfigBuilder.build_payload`."""
        return self._config_builder.build_payload(cfg, messages)

    def _stream_response(self, url: str, payload: dict[str, Any], api_key: str, timeout: int) -> Iterator[bytes]:
        """Delegate to :meth:`LlmStreamer.stream_response`."""
        return self._streamer.stream_response(url, payload, api_key, timeout)

    def _parse_stream_chunk(self, line: bytes) -> tuple[str | None, str, str]:
        """Delegate to :meth:`LlmStreamer.parse_stream_chunk`."""
        return self._streamer.parse_stream_chunk(line)

    def _cache_get(self, key: tuple[Any, ...]) -> tuple[str, bool, str, str] | None:
        """Retrieve a cached response by *key* (LRU — promotes the entry on access).

        Uses :meth:`OrderedDict.move_to_end` to keep the most-recently-used entry
        at the tail.  See DECISIONS.md D3 for the LRU implementation rationale.

        Args:
            key: The cache key tuple (mode, model, prompts, temperature, tokens,
                seed, image_hash).

        Returns:
            The cached ``(text, status, info, reasoning)`` tuple, or ``None`` on
            a cache miss.
        """
        if key in self._response_cache:
            self._response_cache.move_to_end(key)
            return self._response_cache[key]
        return None

    def _cache_put(self, key: tuple[Any, ...], value: tuple[str, bool, str, str]) -> None:
        """Store *value* in the LRU cache under *key*, evicting the oldest entry if full.

        Eviction uses :meth:`OrderedDict.popitem(last=False)` to remove the
        least-recently-used entry when the cache exceeds ``_cache_max_size``.

        Args:
            key: The cache key tuple.
            value: The ``(text, status, info, reasoning)`` tuple to cache.
        """
        self._response_cache[key] = value
        if len(self._response_cache) > LLM_Node._cache_max_size:
            self._response_cache.popitem(last=False)

    def generate(self, **kwargs: Any) -> tuple[str, bool, str, str]:
        """Run the LLM generation pipeline and return the result.

        Execution steps:

        1. Build a flat config dict from ``**kwargs``.
        2. Signal the UI streaming widget to start (``"start"`` event).
        3. Encode the vision image (if provided) to base64.
        4. Check the LRU cache — if a matching entry exists, replay it to the UI
           and return immediately.
        5. Resolve the API URL and key; return an error tuple on failure.
        6. Build the messages list and request payload.
        7. Stream the response, parsing each SSE chunk into reasoning and content
           parts.  Reasoning is shown first; when content arrives the widget is
           cleared and content is streamed in its place.
        8. After streaming completes, fetch the OpenRouter credit balance (if applicable).
        9. Cache the result and return.

        Args:
            **kwargs: ComfyUI widget values as keyword arguments (e.g. ``Mode``,
                ``Model``, ``System Prompt``, ``User Prompt``, ``seed``, etc.).

        Returns:
            A 4-tuple ``(generated_text, success, information, reasoning_content)``:

            * ``generated_text`` — the clean LLM response (reasoning blocks removed).
            * ``success`` — ``True`` if generation succeeded, ``False`` on any error.
            * ``information`` — latency and credit info string (e.g.
              ``"Latency: 1.23s | Credits: $7.50"``), or the error message on failure.
            * ``reasoning_content`` — extracted reasoning/thinking text, or ``""`` if
              the model did not produce a reasoning block.
        """
        cfg: dict[str, Any] = self._build_config(kwargs)
        unique_id = cfg["unique_id"]

        if unique_id:
            PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "start"})

        b64_image: str | None = None
        if cfg["vision_image"] is not None:
            try:
                b64_image = self.encode_image_to_base64(cfg["vision_image"])
            except Exception as e:
                err = f"Error processing image: {str(e)}"
                self.push_error_to_ui(unique_id, err)
                return ("", False, err, "")

        image_hash: str | None = hashlib.sha256(b64_image.encode()).hexdigest() if b64_image else None
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
            cached_text, status, info, cached_reasoning = cached
            if unique_id:
                combined = f"<think>{cached_reasoning}</think>{cached_text}" if cached_reasoning else cached_text
                PromptServer.instance.send_sync(
                    "that_ai_god.stream",
                    {"node": unique_id, "type": "update", "delta": combined},
                )
            return (cached_text, status, info, cached_reasoning)

        base_url, api_key, api_error = self._resolve_api_config(cfg)
        if api_error:
            self.push_error_to_ui(unique_id, api_error)
            return ("", False, api_error, "")

        messages = self._build_messages(cfg["system_prompt"], cfg["user_prompt"], b64_image)
        payload = self._build_payload(cfg, messages)

        start_time: float = time.time()

        try:
            clean_parts: list[str] = []
            reasoning_parts: list[str] = []
            cleared_for_content = False
            for line in self._stream_response(base_url, payload, api_key, cfg["timeout_seconds"]):
                combined_text, reasoning_part, content_part = self._parse_stream_chunk(line)
                if combined_text is None:
                    break
                if combined_text:
                    if content_part and not cleared_for_content and (reasoning_parts or reasoning_part):
                        # Reasoning phase ended — clear the widget before streaming clean content
                        cleared_for_content = True
                        if unique_id:
                            PromptServer.instance.send_sync(
                                "that_ai_god.stream",
                                {"node": unique_id, "type": "clear"},
                            )
                    if unique_id:
                        if cleared_for_content and content_part:
                            PromptServer.instance.send_sync(
                                "that_ai_god.stream",
                                {"node": unique_id, "type": "update", "delta": content_part},
                            )
                        elif not cleared_for_content:
                            PromptServer.instance.send_sync(
                                "that_ai_god.stream",
                                {"node": unique_id, "type": "update", "delta": combined_text},
                            )
                    if reasoning_part:
                        reasoning_parts.append(reasoning_part)
                    if content_part:
                        clean_parts.append(content_part)

            end_time: float = time.time()
            latency: float = end_time - start_time
            generated_content: str = "".join(clean_parts).strip()
            reasoning_content: str = "".join(reasoning_parts).strip()

            api_key_was: str = api_key
            info_parts: list[str] = [f"Latency: {latency:.2f}s"]
            if cfg["mode"] == "OpenRouter":
                credits: str | None = self.fetch_openrouter_credits(api_key_was)
                if credits:
                    info_parts.append(f"Credits: {credits}")
            final_info: str = " | ".join(info_parts)

            result: tuple[str, bool, str, str] = (generated_content, True, final_info, reasoning_content)
            self._cache_put(cache_key, result)
            return result

        except urllib.error.HTTPError as e:
            error_body: str = e.read().decode("utf-8")[:MAX_ERROR_BODY_LENGTH]
            err_msg = f"HTTP Error {e.code}: {e.reason}\nDetails: {error_body}"
            self.push_error_to_ui(unique_id, err_msg)
            return ("", False, err_msg, "")

        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout):
                err = "Error: Request timed out."
            else:
                err = f"Connection Error: {e.reason}"
            self.push_error_to_ui(unique_id, err)
            return ("", False, err, "")

        except Exception as e:
            err = f"Unknown Error: {str(e)}"
            self.push_error_to_ui(unique_id, err)
            return ("", False, err, "")


NODE_CLASS_MAPPINGS = {
    "LLM_Node": LLM_Node,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LLM_Node": "LLM Chat (OpenRouter/Local)",
}

__all__: list[str] = ["LLM_Node", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
