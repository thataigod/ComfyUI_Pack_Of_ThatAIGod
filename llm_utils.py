import os
import json
import hashlib
import asyncio
import urllib.request
import urllib.error
from urllib.parse import urlparse
import socket
import base64
import io
import logging
from collections import OrderedDict
from typing import Any, Iterator
from PIL import Image
import numpy as np
import torch
import aiohttp
from server import PromptServer


logger = logging.getLogger("ThatAIGod")

CACHE_MAX_SIZE: int = 10
MODEL_FETCH_TIMEOUT: int = 2
CREDITS_FETCH_TIMEOUT: int = 3
MAX_MODELS_IN_DROPDOWN: int = 200
MAX_ERROR_BODY_LENGTH: int = 500

DEFAULT_MODELS: list[str] = [
    "mistralai/devstral-2512:free",
    "z-ai/glm-4.5-air:free",
    "tngtech/tng-r1t-chimera:free",
    "amazon/nova-2-lite-v1:free",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
]


class LlmCache:
    def __init__(self, max_size: int = CACHE_MAX_SIZE) -> None:
        self._cache: OrderedDict[Any, tuple[str, bool, str]] = OrderedDict()
        self._max_size: int = max_size

    def get(self, key: tuple[Any, ...]) -> tuple[str, bool, str] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: tuple[Any, ...], value: tuple[str, bool, str]) -> None:
        self._cache[key] = value
        # Evict oldest entry when cache exceeds capacity
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class LlmConfigBuilder:
    @staticmethod
    def build_config(kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": kwargs.get("Mode", "OpenRouter"),
            "model_name": kwargs.get("Model", "mistralai/devstral-2512:free"),
            "system_prompt": kwargs.get("System Prompt", ""),
            "user_prompt": kwargs.get("User Prompt", ""),
            "temperature": kwargs.get("Temperature", 0.7),
            "max_tokens": kwargs.get("Max Tokens", 1024),
            "seed": kwargs.get("seed", 0),
            "timeout_seconds": kwargs.get("Timeout (Seconds)", 30),
            "unique_id": kwargs.get("unique_id", None),
            "api_key_env_var": kwargs.get("API Key Env Var", "OPENROUTER_API_KEY"),
            "local_url": kwargs.get("Local URL", "http://localhost:1234/v1"),
            "vision_image": kwargs.get("Image(s)", None),
        }

    @staticmethod
    def resolve_api_config(cfg: dict[str, Any]) -> tuple[str, str, str | None]:
        mode = cfg["mode"]
        if mode == "OpenRouter":
            base_url = "https://openrouter.ai/api/v1/chat/completions"
            api_key = os.environ.get(cfg["api_key_env_var"].strip(), "")
            if not api_key:
                return ("", "", "Error: No API Key found in " + cfg["api_key_env_var"] + ".")
        else:
            base_url = cfg["local_url"].strip().rstrip("/")
            parsed = urlparse(base_url)
            if parsed.hostname not in ("localhost", "127.0.0.1", "::1", ""):
                return ("", "", f"Error: Local URL must be localhost (got {parsed.hostname}).")
            if not base_url.endswith("/chat/completions"):
                base_url += "/chat/completions"
            api_key = "lm-studio"

        final_user_content: str = cfg["user_prompt"]
        if not final_user_content.strip() and cfg["vision_image"] is None:
            return ("", "", "Error: User prompt is empty.")

        return (base_url, api_key, None)

    @staticmethod
    def build_messages(
        system_prompt: str, user_prompt: str, b64_image: str | None
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if b64_image:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                        },
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": user_prompt})
        return messages

    @staticmethod
    def build_payload(cfg: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": cfg["model_name"],
            "messages": messages,
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
            "stream": True,
        }
        if cfg["seed"] != 0:
            payload["seed"] = cfg["seed"]
        return payload


class LlmStreamer:
    @staticmethod
    def stream_response(
        url: str, payload: dict[str, Any], api_key: str, timeout: int
    ) -> Iterator[bytes]:
        chunks: list[bytes] = _run_async_stream(url, payload, api_key, timeout)
        yield from chunks

    @staticmethod
    def parse_stream_chunk(line: bytes) -> str | None:
        # Parse SSE format: "data: {json}" or "data: [DONE]"
        decoded_line: str = line.decode("utf-8").strip()
        if decoded_line.startswith("data: "):
            data_str: str = decoded_line[6:]
            if data_str == "[DONE]":
                return None
            try:
                json_chunk: dict[str, Any] = json.loads(data_str)
                if "choices" in json_chunk and len(json_chunk["choices"]) > 0:
                    delta: dict[str, Any] = json_chunk["choices"][0].get("delta", {})
                    return delta.get("content", "")
            except (json.JSONDecodeError, KeyError, IndexError):
                pass
        return ""


_STREAM_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "User-Agent": "ThatAIGod-ComfyUI-Node/1.0",
    "X-Title": "ComfyUI-Pack-Of-ThatAIGod",
}


async def _async_fetch_stream(
    url: str, payload: dict[str, Any], api_key: str, timeout: int
) -> list[bytes]:
    headers: dict[str, str] = {**_STREAM_HEADERS, "Authorization": f"Bearer {api_key}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            response.raise_for_status()
            return [line async for line in response.content]


def _run_async_stream(
    url: str, payload: dict[str, Any], api_key: str, timeout: int
) -> list[bytes]:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            _async_fetch_stream(url, payload, api_key, timeout)
        )
    except aiohttp.ClientResponseError as e:
        raise urllib.error.HTTPError(
            url, e.status, e.message, None, None
        )
    except (asyncio.TimeoutError, socket.timeout):
        raise urllib.error.URLError(socket.timeout())
    except aiohttp.ClientError as e:
        raise urllib.error.URLError(str(e))
    finally:
        loop.close()


def encode_image_to_base64(image_tensor: torch.Tensor) -> str:
    arr: np.ndarray = (255.0 * image_tensor[0].cpu().numpy()).astype("uint8")
    img: Image.Image = Image.fromarray(arr, "RGB")
    buffered: io.BytesIO = io.BytesIO()
    img.save(buffered, format="JPEG", quality=90)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def fetch_openrouter_credits(api_key: str) -> str | None:
    try:
        req: urllib.request.Request = urllib.request.Request(
            "https://openrouter.ai/api/v1/credits",
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "ThatAIGod-ComfyUI-Node/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=CREDITS_FETCH_TIMEOUT) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            if "data" in data:
                d: dict[str, Any] = data["data"]
                total: float = float(d.get("total_credits", 0))
                usage: float = float(d.get("total_usage", 0))
                remaining: float = total - usage
                return f"${remaining:.2f}"
    except Exception:
        return None
    return None


def push_error_to_ui(unique_id: str | None, error_msg: str) -> None:
    if unique_id:
        PromptServer.instance.send_sync(
            "that_ai_god.stream",
            {"node": unique_id, "type": "update", "delta": f"\n\n[ERROR]: {error_msg}"},
        )


_model_cache: list[str] | None = None


def get_initial_model_list() -> list[str]:
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    try:
        url: str = "https://openrouter.ai/api/v1/models"
        req: urllib.request.Request = urllib.request.Request(
            url, headers={"User-Agent": "ThatAIGod-ComfyUI-Node/1.0"}
        )
        with urllib.request.urlopen(req, timeout=MODEL_FETCH_TIMEOUT) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            if "data" in data and isinstance(data["data"], list):
                fetched_models: list[str] = [m["id"] for m in data["data"]]
                _model_cache = fetched_models[:MAX_MODELS_IN_DROPDOWN]
                return _model_cache
            logger.warning("Unexpected API response format from OpenRouter models endpoint")
    except Exception as e:
        logger.warning("Failed to fetch model list from OpenRouter: %s", e)

    return list(DEFAULT_MODELS)
