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
import torch
from PIL import Image
from server import PromptServer

class LLM_Node:
    _model_cache = None
    _response_cache = {} 

    def __init__(self):
        pass

    @classmethod
    def get_initial_model_list(cls):
        if cls._model_cache:
            return cls._model_cache

        defaults = [
            "mistralai/devstral-2512:free",
            "z-ai/glm-4.5-air:free",
            "tngtech/tng-r1t-chimera:free",
            "amazon/nova-2-lite-v1:free",
            "anthropic/claude-3.5-sonnet", 
            "openai/gpt-4o"
        ]

        try:
            url = "https://openrouter.ai/api/v1/models"
            # Added User-Agent to prevent Cloudflare blocks
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
                if "data" in data and isinstance(data["data"], list):
                    fetched_models = [m["id"] for m in data["data"]]
                    cls._model_cache = fetched_models
                    return fetched_models
        except Exception:
            pass
        
        return defaults

    @classmethod
    def INPUT_TYPES(s):
        model_list = s.get_initial_model_list()

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
                "Image(s)": ("IMAGE", ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("Generated Text", "Status (Boolean)", "Information")
    FUNCTION = "generate"
    CATEGORY = "ThatAIGod/LLM"

    @classmethod
    def VALIDATE_INPUTS(s, **kwargs):
        return True

    def encode_image_to_base64(self, image_tensor):
        i = 255. * image_tensor[0].cpu().numpy()
        img = Image.fromarray(i.astype('uint8'), 'RGB')
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=90)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def fetch_openrouter_credits(self, api_key):
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/credits",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "Mozilla/5.0"
                }
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
                if "data" in data:
                    d = data["data"]
                    total = float(d.get("total_credits", 0))
                    usage = float(d.get("total_usage", 0))
                    remaining = total - usage
                    return f"${remaining:.2f}"
        except Exception:
            return None
        return None

    def push_error_to_ui(self, unique_id, error_msg):
        if unique_id:
            PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "update", "delta": f"\n\n[ERROR]: {error_msg}"})

    def generate(self, **kwargs):
        mode = kwargs.get("Mode", "OpenRouter")
        model_name = kwargs.get("Model", "mistralai/devstral-2512:free")
        system_prompt = kwargs.get("System Prompt", "")
        user_prompt = kwargs.get("User Prompt", "")
        temperature = kwargs.get("Temperature", 0.7)
        max_tokens = kwargs.get("Max Tokens", 1024)
        seed = kwargs.get("seed", 0)
        timeout_seconds = kwargs.get("Timeout (Seconds)", 30)
        unique_id = kwargs.get("unique_id", None)
        
        api_key_env_var = kwargs.get("API Key Env Var", "OPENROUTER_API_KEY")
        local_url = kwargs.get("Local URL", "http://localhost:1234/v1")
        vision_image = kwargs.get("Image(s)", None)

        # Notify UI start
        if unique_id:
            PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "start"})

        # 1. Image Cache Key
        b64_image = None
        if vision_image is not None:
            try:
                b64_image = self.encode_image_to_base64(vision_image)
            except Exception as e:
                err = f"Error processing image: {str(e)}"
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)

        # 2. Cache Check
        image_hash = hashlib.md5(b64_image.encode()).hexdigest() if b64_image else None
        cache_key = (mode, model_name, system_prompt, user_prompt, temperature, max_tokens, seed, image_hash)

        if cache_key in self._response_cache:
            print(f"[ThatAIGod] Returning cached LLM response for seed {seed}")
            cached_text, status, info = self._response_cache[cache_key]
            if unique_id:
                PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "update", "delta": cached_text})
            return (cached_text, status, info)

        # 3. Setup
        api_key = ""
        base_url = ""

        if mode == "OpenRouter":
            base_url = "https://openrouter.ai/api/v1/chat/completions"
            api_key = os.environ.get(api_key_env_var.strip(), "")
            if not api_key:
                err = f"Error: No API Key found in {api_key_env_var}."
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)
        else:
            base_url = local_url.strip().rstrip('/')
            # Validate Local URL only allows localhost
            parsed = urlparse(base_url)
            if parsed.hostname not in ("localhost", "127.0.0.1", ""):
                err = f"Error: Local URL must be localhost (got {parsed.hostname})."
                self.push_error_to_ui(unique_id, err)
                return ("", False, err)
            if not base_url.endswith("/chat/completions"):
                base_url += "/chat/completions"
            api_key = "lm-studio"

        # 4. Payload
        final_user_content = user_prompt
        if not final_user_content.strip() and vision_image is None:
            err = "Error: User prompt is empty."
            self.push_error_to_ui(unique_id, err)
            return ("", False, err)

        messages = [{"role": "system", "content": system_prompt}]
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

        payload = {
            "model": model_name, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": True
        }
        if seed != 0: payload["seed"] = seed

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/thataigod",
            "X-Title": "ComfyUI-Pack-Of-ThatAIGod",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # 5. Execute with WebSocket Streaming
        start_time = time.time()
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(base_url, data=data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                full_content = []
                
                for line in response:
                    decoded_line = line.decode("utf-8").strip()
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str == "[DONE]": break
                        try:
                            json_chunk = json.loads(data_str)
                            if "choices" in json_chunk and len(json_chunk["choices"]) > 0:
                                delta = json_chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_content.append(content)
                                    if unique_id:
                                        PromptServer.instance.send_sync("that_ai_god.stream", {"node": unique_id, "type": "update", "delta": content})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

                end_time = time.time()
                latency = end_time - start_time
                generated_content = "".join(full_content)
                
                if generated_content:
                    generated_content = generated_content.strip()

                info_parts = [f"Latency: {latency:.2f}s"]
                if mode == "OpenRouter":
                    credits = self.fetch_openrouter_credits(api_key)
                    if credits: info_parts.append(f"Credits: {credits}")
                api_key = ""
                final_info = " | ".join(info_parts)
                
                result = (generated_content, True, final_info)
                self._response_cache[cache_key] = result
                # Keep only the last 10 entries to prevent unbounded growth
                if len(self._response_cache) > 10:
                    oldest_key = next(iter(self._response_cache))
                    del self._response_cache[oldest_key]
                return result

        # --- FIX: CATCH HTTP ERROR BEFORE URL ERROR ---
        except urllib.error.HTTPError as e:
            # This captures the real API error (400, 401, 404, 500)
            error_body = e.read().decode("utf-8")[:500]
            err_msg = f"HTTP Error {e.code}: {e.reason}\nDetails: {error_body}"
            self.push_error_to_ui(unique_id, err_msg)
            return ("", False, err_msg)

        except urllib.error.URLError as e:
            # This captures DNS/Network issues
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