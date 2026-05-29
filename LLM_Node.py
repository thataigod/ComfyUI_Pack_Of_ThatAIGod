import os
import json
import hashlib
import urllib.request
import urllib.error
from urllib.parse import urlparse
import socket
import base64
import io
import time
import logging
import torch
import numpy as np
from typing import Any
from PIL import Image
from server import PromptServer


logger = logging.getLogger("ThatAIGod")


class LLM_Node:
    _model_cache: list[str] | None = None
    _response_cache: dict[Any, tuple[str, bool, str]] = {}

    @classmethod
    def get_initial_model_list(cls) -> list[str]:
        if cls._model_cache:
            return cls._model_cache

        defaults: list[str] = [
            "mistralai/devstral-2512:free",
            "z-ai/glm-4.5-air:free",
            "tngtech/tng-r1t-chimera:free",
            "amazon/nova-2-lite-v1:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o"
        ]

        try:
            url: str = "https://openrouter.ai/api/v1/models"
            req: urllib.request.Request = urllib.request.Request(url, headers={'User-Agent': 'ThatAIGod-ComfyUI-Node/1.0'})
            with urllib.request.urlopen(req, timeout=2) as response:
                data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
                if "data" in data and isinstance(data["data"], list):
                    fetched_models: list[str] = [m["id"] for m in data["data"]]
                    cls._model_cache = fetched_models[:200]
                    return fetched_models
        except Exception:
            pass

        return defaults

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        model_list: list[str] = cls.get_initial_model_list()

        return {
            "required": {
                "Mode": (["OpenRouter", "Local"], {"default": "OpenRouter"}),
                "Model": (model_list, {"default": "mistralai/devstral-2512:free"}),
                "System Prompt": ("STRING", {"multiline": True, "default": "You are a helpful assistant."}),
                "User Prompt": ("STRING", {"multiline": True, "dynamic": True, "placeholder": "Input text or connect input..."}),
                "Temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "Max Tokens": ("INT", {"default": 1024, "min": 1, "max": 128000}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "Timeout (Seconds)": ("INT", {"default": 30, "min": 1, "max": 300}),
            },
            "optional": {
                "API Key Env Var": (["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_BACKUP", "OPENROUTER_API_KEY_EXTRA"], {"default": "OPENROUTER_API_KEY"}),
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
        arr: np.ndarray = (255. * image_tensor[0].cpu().numpy()).astype('uint8')
        img: Image.Image = Image.fromarray(arr, 'RGB')
        buffered: io.BytesIO = io.BytesIO()
        img.save(buffered, format="JPEG", quality=90)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def fetch_openrouter_credits(self, api_key: str) -> str | None:
        try:
            req: urllib.request.Request = urllib.request.Request(
                "https://openrouter.ai/api/v1/credits",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "ThatAIGod-ComfyUI-Node/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=3) as response:
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

    def push_error_to_ui(self, unique_id: str | None, error_msg: str) -> None:
        if unique_id:
            PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "update", "delta": f"\n\n[ERROR]: {error_msg}"})

    def generate(self, **kwargs: Any) -> tuple[str, bool, str]:
        mode: str = kwargs.get("Mode", "OpenRouter")
        model_name: str = kwargs.get("Model", "mistralai/devstral-2512:free")
        system_prompt: str = kwargs.get("System Prompt", "")
        user_prompt: str = kwargs.get("User Prompt", "")
        temperature: float = kwargs.get("Temperature", 0.7)
        max_tokens: int = kwargs.get("Max Tokens", 1024)
        seed: int = kwargs.get("seed", 0)
        timeout_seconds: int = kwargs.get("Timeout (Seconds)", 30)
        unique_id: str | None = kwargs.get("unique_id", None)

        api_key_env_var: str = kwargs.get("API Key Env Var", "OPENROUTER_API_KEY")
        local_url: str = kwargs.get("Local URL", "http://localhost:1234/v1")
        vision_image: torch.Tensor | None = kwargs.get("Image(s)", None)

        if unique_id:
            PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "start"})

        b64_image: str | None = None
        if vision_image is not None:
            try:
                b64_image = self.encode_image_to_base64(vision_image)
            except Exception as e:
                err: str = f"Error processing image: {str(e)}"
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)

        image_hash: str | None = hashlib.md5(b64_image.encode()).hexdigest() if b64_image else None
        cache_key: tuple[Any, ...] = (mode, model_name, system_prompt, user_prompt, temperature, max_tokens, seed, image_hash)

        if cache_key in self._response_cache:
            logger.info("Returning cached LLM response for seed %s", seed)
            cached_text: str
            status: bool
            info: str
            cached_text, status, info = self._response_cache[cache_key]
            if unique_id:
                PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "update", "delta": cached_text})
            return (cached_text, status, info)

        api_key: str = ""
        base_url: str = ""

        if mode == "OpenRouter":
            base_url = "https://openrouter.ai/api/v1/chat/completions"
            api_key = os.environ.get(api_key_env_var.strip(), "")
            if not api_key:
                err = f"Error: No API Key found in {api_key_env_var}."
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)
        else:
            base_url = local_url.strip().rstrip('/')
            parsed = urlparse(base_url)
            if parsed.hostname not in ("localhost", "127.0.0.1", ""):
                err = f"Error: Local URL must be localhost (got {parsed.hostname})."
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)
            if not base_url.endswith("/chat/completions"):
                base_url += "/chat/completions"
            api_key = "lm-studio"

        final_user_content: str = user_prompt
        if not final_user_content.strip() and vision_image is None:
            err = "Error: User prompt is empty."
            self.push_error_to_ui(unique_id, err)
            return ("", False, err)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if b64_image:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": final_user_content},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": final_user_content})

        payload: dict[str, Any] = {
            "model": model_name, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": True
        }
        if seed != 0:
            payload["seed"] = seed

        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ThatAIGod-ComfyUI-Node/1.0",
            "X-Title": "ComfyUI-Pack-Of-ThatAIGod",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        start_time: float = time.time()

        try:
            data: bytes = json.dumps(payload).encode("utf-8")
            req: urllib.request.Request = urllib.request.Request(base_url, data=data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                full_content: list[str] = []

                for line in response:
                    decoded_line: str = line.decode("utf-8").strip()
                    if decoded_line.startswith("data: "):
                        data_str: str = decoded_line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            json_chunk: dict[str, Any] = json.loads(data_str)
                            if "choices" in json_chunk and len(json_chunk["choices"]) > 0:
                                delta: dict[str, Any] = json_chunk["choices"][0].get("delta", {})
                                content: str = delta.get("content", "")
                                if content:
                                    full_content.append(content)
                                    if unique_id:
                                        PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "update", "delta": content})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

                end_time: float = time.time()
                latency: float = end_time - start_time
                generated_content: str = "".join(full_content)

                if generated_content:
                    generated_content = generated_content.strip()

                info_parts: list[str] = [f"Latency: {latency:.2f}s"]
                if mode == "OpenRouter":
                    credits: str | None = self.fetch_openrouter_credits(api_key)
                    if credits:
                        info_parts.append(f"Credits: {credits}")
                api_key = ""
                final_info: str = " | ".join(info_parts)

                result: tuple[str, bool, str] = (generated_content, True, final_info)
                self._response_cache[cache_key] = result
                if len(self._response_cache) > 10:
                    oldest_key: Any = next(iter(self._response_cache))
                    del self._response_cache[oldest_key]
                return result

        except urllib.error.HTTPError as e:
            error_body: str = e.read().decode("utf-8")[:500]
            err_msg: str = f"HTTP Error {e.code}: {e.reason}\nDetails: {error_body}"
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