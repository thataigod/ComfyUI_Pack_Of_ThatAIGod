import asyncio
import base64
import concurrent.futures
import http.client
import io
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import aiohttp
import numpy as np
import torch
from PIL import Image
from server import PromptServer

logger = logging.getLogger("ThatAIGod")

CACHE_MAX_SIZE: int = 10
CREDITS_FETCH_TIMEOUT: int = 3
CREDITS_CACHE_TTL: int = 60
MAX_ERROR_BODY_LENGTH: int = 500
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 1.0
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 502, 503})
MAX_IMAGE_DIMENSION: int = 8192

DEFAULT_MODELS: list[str] = [
    "mistralai/devstral-2512:free",
    "z-ai/glm-4.5-air:free",
    "tngtech/tng-r1t-chimera:free",
    "amazon/nova-2-lite-v1:free",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
]


class LlmConfigBuilder:
    """Builds configuration dicts, API payloads, and message lists for LLM API calls."""

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
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
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
    """Handles streaming LLM responses via aiohttp with async-to-sync bridging."""

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
    for attempt in range(MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                        retry_after = float(response.headers.get("Retry-After", RETRY_BACKOFF_BASE * (2 ** attempt)))
                        logger.warning("Retryable HTTP %d, retrying in %.1fs (attempt %d/%d)", response.status, retry_after, attempt + 1, MAX_RETRIES)
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    return [line async for line in response.content]
        except aiohttp.ClientResponseError as e:
            if e.status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("Retryable error %d, retrying in %.1fs (attempt %d/%d)", e.status, wait, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(wait)
                continue
            raise
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("Network error, retrying in %.1fs (attempt %d/%d): %s", wait, attempt + 1, MAX_RETRIES, e)
                await asyncio.sleep(wait)
                continue
            raise


_EXECUTOR: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_async(coro):
    """Run a coroutine from a sync context.

    Detects whether an event loop is already running in this thread (e.g.
    ComfyUI's own loop) and dispatches accordingly:
    - No running loop: use ``asyncio.run()`` directly.
    - Running loop present: submit to a thread-pool so the new loop does not
      collide with the existing one.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    return _EXECUTOR.submit(asyncio.run, coro).result()


def _run_async_stream(
    url: str, payload: dict[str, Any], api_key: str, timeout: int
) -> list[bytes]:
    try:
        return _run_async(
            _async_fetch_stream(url, payload, api_key, timeout)
        )
    except aiohttp.ClientResponseError as e:
        raise urllib.error.HTTPError(
            url, e.status, e.message, http.client.HTTPMessage(), None
        )
    except (TimeoutError, asyncio.TimeoutError):
        raise urllib.error.URLError(TimeoutError())
    except aiohttp.ClientError as e:
        raise urllib.error.URLError(str(e))


def encode_image_to_base64(image_tensor: torch.Tensor) -> str:
    """Encode a ComfyUI image tensor to a base64 PNG string.

    Args:
        image_tensor: A (1, H, W, 3) float32 tensor with values in [0, 1].

    Returns:
        Base64-encoded PNG string.
    """
    arr: np.ndarray = (255.0 * image_tensor[0].cpu().numpy()).astype("uint8")
    if arr.shape[0] > MAX_IMAGE_DIMENSION or arr.shape[1] > MAX_IMAGE_DIMENSION:
        raise ValueError(
            f"Image dimensions {arr.shape[1]}x{arr.shape[0]} exceed maximum {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
        )
    img: Image.Image = Image.fromarray(arr, "RGB")
    buffered: io.BytesIO = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


_credits_cache: dict[str, tuple[float, str]] = {}


def fetch_openrouter_credits(api_key: str) -> str | None:
    """Fetch remaining OpenRouter credit balance as a formatted string (e.g. '$7.50').

    Results are cached for CREDITS_CACHE_TTL seconds to avoid redundant API calls.
    Returns None on any failure.
    """
    import time as _time

    now = _time.time()
    if api_key in _credits_cache:
        cached_time, cached_value = _credits_cache[api_key]
        if now - cached_time < CREDITS_CACHE_TTL:
            return cached_value

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
                result = f"${remaining:.2f}"
                _credits_cache[api_key] = (now, result)
                return result
    except Exception as e:
        logger.debug("Failed to fetch OpenRouter credits: %s", e)
        return None
    return None


def push_error_to_ui(unique_id: str | None, error_msg: str) -> None:
    if unique_id:
        PromptServer.instance.send_sync(
            "that_ai_god.stream",
            {"node": unique_id, "type": "update", "delta": f"\n\n[ERROR]: {error_msg}"},
        )


__all__: list[str] = [
    "CACHE_MAX_SIZE",
    "CREDITS_FETCH_TIMEOUT",
    "MAX_ERROR_BODY_LENGTH",
    "MAX_RETRIES",
    "RETRY_BACKOFF_BASE",
    "RETRYABLE_STATUS_CODES",
    "DEFAULT_MODELS",
    "LlmConfigBuilder",
    "LlmStreamer",
    "encode_image_to_base64",
    "fetch_openrouter_credits",
    "push_error_to_ui",
]
