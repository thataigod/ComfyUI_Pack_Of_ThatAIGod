import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ComfyUI server module before importing LLM_Node
server_mock = MagicMock()
server_mock.PromptServer.instance.send_sync = MagicMock()
sys.modules["server"] = server_mock

from LLM_Node import LLM_Node
import urllib.error


def _make_kwargs(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "Mode": "OpenRouter",
        "Model": "test-model",
        "System Prompt": "You are helpful.",
        "User Prompt": "Hello",
        "Temperature": 0.7,
        "Max Tokens": 1024,
        "seed": 0,
        "Timeout (Seconds)": 30,
        "API Key Env Var": "OPENROUTER_API_KEY",
        "Local URL": "http://localhost:1234/v1",
        "Image(s)": None,
        "unique_id": None,
    }
    if overrides:
        base.update(overrides)
    return base


class TestLLMNode(unittest.TestCase):
    def setUp(self):
        self.node = LLM_Node()
        LLM_Node._model_cache = None
        LLM_Node._response_cache = {}

    def test_validate_inputs_missing_api_key_returns_error(self):
        with patch.dict(os.environ, {}, clear=True):
            result = LLM_Node.VALIDATE_INPUTS(**{
                "Mode": "OpenRouter",
                "API Key Env Var": "OPENROUTER_API_KEY",
                "Temperature": 0.7,
                "Max Tokens": 1024,
            })
            self.assertIsInstance(result, str)
            self.assertIn("API key not found", result)

    def test_validate_inputs_with_api_key_returns_true(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            result = LLM_Node.VALIDATE_INPUTS(**{
                "Mode": "OpenRouter",
                "API Key Env Var": "OPENROUTER_API_KEY",
                "Temperature": 0.7,
                "Max Tokens": 1024,
            })
            self.assertTrue(result)

    def test_validate_inputs_local_mode_skips_api_key_check(self):
        result = LLM_Node.VALIDATE_INPUTS(**{
            "Mode": "Local",
            "API Key Env Var": "OPENROUTER_API_KEY",
            "Temperature": 0.7,
            "Max Tokens": 1024,
        })
        self.assertTrue(result)

    def test_validate_inputs_temperature_out_of_range(self):
        result = LLM_Node.VALIDATE_INPUTS(**{
            "Mode": "Local",
            "API Key Env Var": "OPENROUTER_API_KEY",
            "Temperature": 3.0,
            "Max Tokens": 1024,
        })
        self.assertIsInstance(result, str)

    def test_validate_inputs_max_tokens_too_low(self):
        result = LLM_Node.VALIDATE_INPUTS(**{
            "Mode": "Local",
            "API Key Env Var": "OPENROUTER_API_KEY",
            "Temperature": 0.7,
            "Max Tokens": 0,
        })
        self.assertIsInstance(result, str)

    def test_get_initial_model_list_returns_cached(self):
        LLM_Node._model_cache = ["test-model"]
        result = LLM_Node.get_initial_model_list()
        self.assertEqual(result, ["test-model"])

    def test_get_initial_model_list_returns_defaults_on_fetch_failure(self):
        LLM_Node._model_cache = None
        with patch.object(urllib.request, "urlopen", side_effect=OSError("no connection")):
            result = LLM_Node.get_initial_model_list()
            self.assertIn("mistralai/devstral-2512:free", result)
            self.assertGreater(len(result), 0)

    def test_get_initial_model_list_fetches_and_caches(self):
        LLM_Node._model_cache = None
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": [{"id": "model1"}, {"id": "model2"}]
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        with patch.object(urllib.request, "urlopen", return_value=mock_response) as mock_urlopen:
            result = LLM_Node.get_initial_model_list()
            self.assertEqual(result, ["model1", "model2"])
            self.assertEqual(LLM_Node._model_cache, ["model1", "model2"])

    @patch("LLM_Node.PromptServer")
    def test_generate_empty_prompt_returns_error(self, mock_ps):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            result = self.node.generate(**_make_kwargs({
                "User Prompt": "", "System Prompt": ""
            }))
            text, status, info = result
            self.assertEqual(text, "")
            self.assertFalse(status)

    def test_encode_image_to_base64_returns_string(self):
        import torch
        dummy_image = torch.zeros((1, 64, 64, 3))
        result = self.node.encode_image_to_base64(dummy_image)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_encode_image_to_base64_is_valid_base64(self):
        import base64
        import torch
        dummy_image = torch.ones((1, 64, 64, 3)) * 127
        result = self.node.encode_image_to_base64(dummy_image)
        decoded = base64.b64decode(result)
        self.assertGreater(len(decoded), 0)

    def test_fetch_openrouter_credits_returns_none_on_failure(self):
        with patch.object(urllib.request, "urlopen", side_effect=OSError("timeout")):
            result = self.node.fetch_openrouter_credits("test-key")
            self.assertIsNone(result)

    def test_fetch_openrouter_credits_returns_string_on_success(self):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": {
                "total_credits": 10.0,
                "total_usage": 2.5,
            }
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        with patch.object(urllib.request, "urlopen", return_value=mock_response):
            result = self.node.fetch_openrouter_credits("test-key")
            self.assertEqual(result, "$7.50")

    def test_response_cache_hit_returns_cached_value(self):
        cache_key = (
            "OpenRouter", "test-model", "", "hello", 0.7, 1024, 0, None
        )
        LLM_Node._response_cache[cache_key] = ("cached reply", True, "cached info")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            with patch("LLM_Node.PromptServer"):
                result = self.node.generate(**_make_kwargs({
                    "User Prompt": "hello", "System Prompt": ""
                }))
                text, status, info = result
                self.assertEqual(text, "cached reply")
                self.assertTrue(status)

    def test_generate_http_error_returns_error_tuple(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            with patch("LLM_Node.PromptServer"):
                with patch.object(urllib.request, "urlopen", side_effect=urllib.error.HTTPError(
                    "http://example.com", 401, "Unauthorized", {}, None
                )):
                    result = self.node.generate(**_make_kwargs())
                    text, status, info = result
                    self.assertEqual(text, "")
                    self.assertFalse(status)
                    self.assertIn("HTTP Error", info)

    def test_local_url_rejects_non_localhost(self):
        with patch("LLM_Node.PromptServer"):
            result = self.node.generate(**_make_kwargs({
                "Mode": "Local",
                "Local URL": "http://evil-server.com:1234/v1",
            }))
            text, status, info = result
            self.assertEqual(text, "")
            self.assertFalse(status)
            self.assertIn("must be localhost", info)

    def test_local_url_allows_ipv6_localhost(self):
        with patch("LLM_Node.PromptServer"):
            result = self.node.generate(**_make_kwargs({
                "Mode": "Local",
                "Local URL": "http://[::1]:1234/v1",
            }))
            text, status, info = result
            self.assertNotIn("must be localhost", info)

    def test_generate_streaming_success(self):
        mock_response = MagicMock()
        chunks = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            b'data: {"choices":[{"delta":{"content":" world"}}]}\n',
            b'data: [DONE]\n',
        ]
        mock_response.__enter__.return_value.__iter__.return_value = chunks

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            with patch("LLM_Node.PromptServer"):
                with patch.object(urllib.request, "urlopen", return_value=mock_response):
                    result = self.node.generate(**_make_kwargs())
                    text, status, info = result
                    self.assertEqual(text, "Hello world")
                    self.assertTrue(status)

    def test_response_cache_eviction(self):
        LLM_Node._response_cache.clear()

        for i in range(LLM_Node._cache_max_size + 1):
            key = ("test", str(i), "", "", 0.7, 1024, 0, None)
            LLM_Node._response_cache[key] = (f"result{i}", True, "")
            if len(LLM_Node._response_cache) > LLM_Node._cache_max_size:
                oldest = next(iter(LLM_Node._response_cache))
                del LLM_Node._response_cache[oldest]

        self.assertLessEqual(len(LLM_Node._response_cache), LLM_Node._cache_max_size)


if __name__ == "__main__":
    unittest.main()
