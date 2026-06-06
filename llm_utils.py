"""Core LLM utility module for ComfyUI-Pack-Of-ThatAIGod.

Provides helper classes and functions used by :mod:`LLM_Node`:

* :class:`LlmConfigBuilder` — builds flat config dicts, OpenAI-style message lists,
  and JSON request payloads from ComfyUI ``**kwargs``.
* :class:`LlmStreamer` — streams SSE responses via ``aiohttp`` and parses delta chunks.
* :func:`encode_image_to_base64` — converts a ComfyUI image tensor to a base64 PNG string.
* :func:`fetch_openrouter_credits` — fetches the remaining OpenRouter credit balance (cached).
* :func:`push_error_to_ui` — sends an error message to the ComfyUI streaming widget.

The async streaming pipeline bridges ``aiohttp`` (async) to ComfyUI's synchronous node
execution model via a daemon thread + bounded ``queue.Queue``.  See DECISIONS.md D12.
"""

import asyncio
import base64
import http.client
import io
import json
import logging
import os
import queue
import threading
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator
from typing import Any
from urllib.parse import urlparse

import aiohttp
import numpy as np
import torch
from PIL import Image
from server import PromptServer

logger = logging.getLogger("ThatAIGod")

# Maximum number of LLM responses held in the LRU cache on LLM_Node.
CACHE_MAX_SIZE: int = 10
# Timeout in seconds for the OpenRouter credits API call.
CREDITS_FETCH_TIMEOUT: int = 3
# How long (seconds) to cache a credits result before re-fetching.
CREDITS_CACHE_TTL: int = 60
# Maximum number of characters read from an HTTP error response body.
MAX_ERROR_BODY_LENGTH: int = 500
# Number of streaming retry attempts for transient errors.
MAX_RETRIES: int = 3
# Base delay (seconds) for exponential backoff between retries.
RETRY_BACKOFF_BASE: float = 1.0
# HTTP status codes that warrant an automatic retry.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 502, 503})
# Maximum allowed image dimension (width or height) for vision inputs.
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
        """Extract and normalise ComfyUI node ``**kwargs`` into a flat config dict.

        All keys use snake_case and have safe defaults so that downstream code never
        needs to call ``kwargs.get(...)`` directly.

        Args:
            kwargs: The raw keyword arguments passed to the node's execution method,
                typically containing ComfyUI input widget values.

        Returns:
            A dict with keys: ``mode``, ``model_name``, ``system_prompt``,
            ``user_prompt``, ``temperature``, ``max_tokens``, ``seed``,
            ``timeout_seconds``, ``unique_id``, ``api_key_env_var``,
            ``local_url``, ``vision_image``.
        """
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
        """Resolve the API base URL and authentication key from *cfg*.

        Returns a 3-tuple ``(base_url, api_key, error_message)``.  On success
        ``error_message`` is ``None``; on failure ``base_url`` and ``api_key``
        are empty strings and ``error_message`` contains a human-readable
        description suitable for display in the UI.

        Validation rules:
        - OpenRouter mode: the environment variable named by ``cfg["api_key_env_var"]``
          must be set and non-empty.
        - Local mode: the hostname of ``cfg["local_url"]`` must be ``localhost``,
          ``127.0.0.1``, or ``::1`` (security restriction, see README).
        - Either mode: ``cfg["user_prompt"]`` must be non-empty unless a vision
          image is also provided.

        Args:
            cfg: Config dict produced by :meth:`build_config`.

        Returns:
            ``(base_url, api_key, None)`` on success, or
            ``("", "", error_string)`` on validation failure.
        """
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
    def build_messages(system_prompt: str, user_prompt: str, b64_image: str | None) -> list[dict[str, Any]]:
        """Build an OpenAI-style messages list for the chat completions API.

        When *b64_image* is provided the user message uses the multimodal content
        format (a list with a ``text`` part and an ``image_url`` part).  Otherwise
        the user message is a plain string.

        Args:
            system_prompt: The system instruction text.
            user_prompt: The user's input text.
            b64_image: Optional base64-encoded PNG string for vision models.  When
                provided the image is embedded as a data-URI (``data:image/png;base64,...``).

        Returns:
            A list of message dicts suitable for the ``"messages"`` field of the
            chat completions request payload.
        """
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
        """Build the JSON request payload for the chat completions API.

        ``stream`` is always ``True`` because all LLM responses are consumed via
        server-sent events.

        **seed behaviour:** when ``cfg["seed"]`` is ``0`` the ``seed`` field is
        omitted from the payload entirely.  Most LLM APIs interpret a missing
        seed as "non-deterministic"; sending ``seed=0`` may be treated as a
        specific seed value on some backends, which would cause unexpected
        determinism.

        Args:
            cfg: Config dict produced by :meth:`build_config`.
            messages: Message list produced by :meth:`build_messages`.

        Returns:
            A dict ready to be JSON-serialised and POSTed to the API endpoint.
        """
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
    """Handles streaming LLM responses via aiohttp with async-to-sync bridging.

    See DECISIONS.md D12 for the rationale behind the thread + queue architecture.
    """

    @staticmethod
    def stream_response(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> Iterator[bytes]:
        """Stream SSE lines from the chat completions API.

        Delegates to :func:`_run_async_stream`, which runs the async aiohttp
        producer on a dedicated daemon thread and bridges results back via a
        bounded ``queue.Queue``.

        Args:
            url: Full API endpoint URL.
            payload: JSON-serialisable request payload.
            api_key: Bearer token for the ``Authorization`` header.
            timeout: Socket connect timeout in seconds.

        Yields:
            Raw SSE line bytes (e.g. ``b"data: {...}\\n"``).
        """
        yield from _run_async_stream(url, payload, api_key, timeout)

    @staticmethod
    def parse_stream_chunk(line: bytes) -> tuple[str | None, str, str]:
        """Parse an SSE line from the streaming response.

        Returns a 3-tuple ``(combined, reasoning, content)``:

        * ``combined``: the concatenation of reasoning and content text for this
          chunk, used for the streaming UI preview.  ``None`` signals the end of
          the stream (``[DONE]`` sentinel).
        * ``reasoning``: reasoning/thinking text from the ``delta.reasoning``
          or ``delta.reasoning_content`` field (empty string if absent).
        * ``content``: regular response text from the ``delta.content`` field
          (empty string if absent).

        Non-data lines (e.g. blank lines, comments) return ``("", "", "")``.

        Args:
            line: A raw bytes line from the SSE stream.

        Returns:
            ``(combined, reasoning, content)`` as described above.
        """
        decoded_line: str = line.decode("utf-8").strip()
        if decoded_line.startswith("data: "):
            data_str: str = decoded_line[6:]
            if data_str == "[DONE]":
                return (None, "", "")
            try:
                json_chunk: dict[str, Any] = json.loads(data_str)
                if "choices" in json_chunk and len(json_chunk["choices"]) > 0:
                    delta: dict[str, Any] = json_chunk["choices"][0].get("delta", {})
                    content: str = delta.get("content", "")
                    reasoning: str = delta.get("reasoning", "") or delta.get("reasoning_content", "")
                    if reasoning or content:
                        return (reasoning + content, reasoning, content)
                    return ("", "", "")
            except (json.JSONDecodeError, KeyError, IndexError):
                pass
        return ("", "", "")


# Standard headers sent with every streaming request.
# The X-Title header is an OpenRouter convention for identifying the calling application.
_STREAM_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "User-Agent": "ThatAIGod-ComfyUI-Node/1.0",
    "X-Title": "ComfyUI-Pack-Of-ThatAIGod",
}


async def _async_fetch_stream(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> AsyncIterator[bytes]:
    """Async generator that yields SSE lines as they arrive from the API.

    Retries up to :data:`MAX_RETRIES` times on :data:`RETRYABLE_STATUS_CODES`
    (429, 502, 503) and transient network errors, using exponential backoff with
    the ``Retry-After`` header when available.  See DECISIONS.md D2 for why
    ``asyncio.sleep`` is used instead of ``time.sleep``.
    """
    headers: dict[str, str] = {**_STREAM_HEADERS, "Authorization": f"Bearer {api_key}"}
    for attempt in range(MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=None, sock_connect=timeout),
                ) as response:
                    if response.status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                        retry_after = float(response.headers.get("Retry-After", RETRY_BACKOFF_BASE * (2**attempt)))
                        logger.warning(
                            "Retryable HTTP %d, retrying in %.1fs (attempt %d/%d)",
                            response.status,
                            retry_after,
                            attempt + 1,
                            MAX_RETRIES,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    it = response.content.__aiter__()
                    first_chunk = await asyncio.wait_for(it.__anext__(), timeout=timeout)
                    yield first_chunk
                    async for line in it:
                        yield line
                    return
        except aiohttp.ClientResponseError as e:
            if e.status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Retryable error %d, retrying in %.1fs (attempt %d/%d)", e.status, wait, attempt + 1, MAX_RETRIES
                )
                await asyncio.sleep(wait)
                continue
            raise
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning("Network error, retrying in %.1fs (attempt %d/%d): %s", wait, attempt + 1, MAX_RETRIES, e)
                await asyncio.sleep(wait)
                continue
            raise


def _run_async_stream(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> Iterator[bytes]:
    """Run the async streaming generator in a thread, yielding chunks one by one as they arrive.

    Creates a daemon :class:`threading.Thread` that owns a fresh event loop and
    runs :func:`_async_fetch_stream`.  Chunks are passed back to the calling thread
    via a bounded :class:`queue.Queue` (maxsize=50) that provides natural backpressure.
    A sentinel object signals end-of-stream.  Any exception raised in the producer
    thread is re-raised in the calling thread after the sentinel is received.

    See DECISIONS.md D12 for the full rationale behind this architecture.
    """
    q: queue.Queue = queue.Queue(maxsize=50)
    _SENTINEL: object = object()
    _error: list[Exception] = []

    async def _producer() -> None:
        try:
            async for line in _async_fetch_stream(url, payload, api_key, timeout):
                q.put(line)
        except Exception as e:
            _error.append(e)
        finally:
            q.put(_SENTINEL)

    def _target() -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_producer())
            loop.close()
        except Exception as e:  # pragma: no cover
            _error.append(e)  # pragma: no cover
            q.put(_SENTINEL)  # pragma: no cover

    t: threading.Thread = threading.Thread(target=_target, daemon=True)
    t.start()

    while True:
        item: object = q.get()
        if item is _SENTINEL:
            break
        yield item  # type: ignore[misc]

    if _error:
        exc: Exception = _error[0]
        if isinstance(exc, aiohttp.ClientResponseError):
            raise urllib.error.HTTPError(url, exc.status, exc.message, http.client.HTTPMessage(), None)
        if isinstance(exc, TimeoutError | asyncio.TimeoutError):
            raise urllib.error.URLError(TimeoutError())
        if isinstance(exc, aiohttp.ClientError):
            raise urllib.error.URLError(str(exc))
        raise exc  # pragma: no cover


def encode_image_to_base64(image_tensor: torch.Tensor) -> str:
    """Encode a ComfyUI image tensor to a base64 PNG string.

    Args:
        image_tensor: A ``(1, H, W, 3)`` float32 tensor with values in ``[0, 1]``.
            Only the first image in a batch is encoded (index 0).

    Returns:
        Base64-encoded PNG string suitable for embedding in a ``data:image/png;base64,``
        data-URI.

    Raises:
        ValueError: If either dimension exceeds :data:`MAX_IMAGE_DIMENSION` (8192 px).
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


# In-memory cache mapping API key → (fetch_timestamp, formatted_balance).
# Results are valid for CREDITS_CACHE_TTL seconds to reduce redundant API calls.
_credits_cache: dict[str, tuple[float, str]] = {}


def fetch_openrouter_credits(api_key: str) -> str | None:
    """Fetch remaining OpenRouter credit balance as a formatted string (e.g. ``'$7.50'``).

    Results are cached for :data:`CREDITS_CACHE_TTL` seconds to avoid redundant
    API calls on every generation.

    Args:
        api_key: OpenRouter bearer token.

    Returns:
        Formatted balance string (e.g. ``"$7.50"``), or ``None`` on any failure
        (network error, malformed response, etc.).
    """
    import time as _time  # Imported locally to avoid ruff flagging unused import (see DECISIONS.md D2)

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
    """Send *error_msg* to the streaming preview widget for the node identified by *unique_id*.

    Uses ``PromptServer.instance.send_sync`` to push a WebSocket message that the
    frontend ``dynamic_display.js`` extension handles as an ``"update"`` event.
    Has no effect when *unique_id* is ``None`` (e.g. during batch-mode execution
    without a running UI).

    Args:
        unique_id: The ComfyUI node ID string, or ``None`` if the UI is not active.
        error_msg: Human-readable error message to display in the streaming widget.
    """
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
