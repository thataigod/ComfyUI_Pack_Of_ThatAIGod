import sys
import os
import json
import socket
import unittest
from unittest.mock import patch, MagicMock
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        LLM_Node._response_cache.clear()

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

    def test_get_initial_model_list_missing_data_key(self):
        LLM_Node._model_cache = None
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"error": "unauthorized"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        with patch.object(urllib.request, "urlopen", return_value=mock_response):
            result = LLM_Node.get_initial_model_list()
            self.assertIn("mistralai/devstral-2512:free", result)

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
        cache_key = ("OpenRouter", "test-model", "", "hello", 0.7, 1024, 0, None)
        LLM_Node._response_cache[cache_key] = ("cached reply", True, "cached info")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            with patch("LLM_Node.PromptServer"):
                result = self.node.generate(**_make_kwargs({
                    "User Prompt": "hello", "System Prompt": ""
                }))
                text, status, info = result
                self.assertEqual(text, "cached reply")
                self.assertTrue(status)

    def test_cache_get_returns_none_for_missing_key(self):
        result = self.node._cache_get(("nonexistent",))
        self.assertIsNone(result)

    def test_cache_get_moves_to_end_on_hit(self):
        from collections import OrderedDict
        LLM_Node._response_cache = OrderedDict()
        key1 = ("key1",)
        key2 = ("key2",)
        LLM_Node._response_cache[key1] = ("val1", True, "")
        LLM_Node._response_cache[key2] = ("val2", True, "")

        self.node._cache_get(key1)
        keys = list(LLM_Node._response_cache.keys())
        self.assertEqual(keys[-1], key1)

    def test_cache_put_evicts_oldest_when_full(self):
        LLM_Node._response_cache.clear()
        LLM_Node._cache_max_size = 3

        for i in range(3):
            self.node._cache_put((f"key{i}",), (f"val{i}", True, ""))
        self.assertEqual(len(LLM_Node._response_cache), 3)

        self.node._cache_put(("key3",), ("val3", True, ""))
        self.assertEqual(len(LLM_Node._response_cache), 3)
        self.assertNotIn(("key0",), LLM_Node._response_cache)

    def test_cache_put_lru_protects_recently_used(self):
        LLM_Node._response_cache.clear()
        LLM_Node._cache_max_size = 3

        for i in range(3):
            self.node._cache_put((f"key{i}",), (f"val{i}", True, ""))
        self.node._cache_get(("key0",))
        self.node._cache_put(("key3",), ("val3", True, ""))
        self.assertIn(("key0",), LLM_Node._response_cache)
        self.assertNotIn(("key1",), LLM_Node._response_cache)

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

    def test_build_config_returns_dict(self):
        kwargs = _make_kwargs()
        cfg = self.node._build_config(kwargs)
        self.assertEqual(cfg["mode"], "OpenRouter")
        self.assertEqual(cfg["model_name"], "test-model")
        self.assertEqual(cfg["seed"], 0)
        self.assertEqual(cfg["timeout_seconds"], 30)

    def test_resolve_api_config_openrouter_missing_key(self):
        cfg = self.node._build_config(_make_kwargs({"Mode": "OpenRouter"}))
        with patch.dict(os.environ, {}, clear=True):
            url, key, error = self.node._resolve_api_config(cfg)
            self.assertIsNotNone(error)
            self.assertIn("No API Key", error)

    def test_resolve_api_config_local_success(self):
        cfg = self.node._build_config(_make_kwargs({"Mode": "Local"}))
        url, key, error = self.node._resolve_api_config(cfg)
        self.assertIsNone(error)
        self.assertEqual(key, "lm-studio")
        self.assertIn("chat/completions", url)

    def test_resolve_api_config_local_rejects_external(self):
        cfg = self.node._build_config(_make_kwargs({
            "Mode": "Local",
            "Local URL": "http://evil.com:1234/v1",
        }))
        url, key, error = self.node._resolve_api_config(cfg)
        self.assertIsNotNone(error)
        self.assertIn("must be localhost", error)

    def test_resolve_api_config_local_appends_chat_completions(self):
        cfg = self.node._build_config(_make_kwargs({
            "Mode": "Local",
            "Local URL": "http://localhost:1234/v1",
        }))
        url, key, error = self.node._resolve_api_config(cfg)
        self.assertIsNone(error)
        self.assertTrue(url.endswith("/chat/completions"))

    def test_build_messages_without_image(self):
        messages = self.node._build_messages("sys prompt", "user text", None)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")

    def test_build_messages_with_image(self):
        messages = self.node._build_messages("sys", "user text", "base64data")
        self.assertEqual(len(messages), 2)
        self.assertIsInstance(messages[1]["content"], list)
        self.assertEqual(messages[1]["content"][1]["type"], "image_url")

    def test_build_payload_includes_seed_when_nonzero(self):
        cfg = self.node._build_config(_make_kwargs({"seed": 42}))
        payload = self.node._build_payload(cfg, [{"role": "user", "content": "hi"}])
        self.assertEqual(payload["seed"], 42)

    def test_build_payload_omits_seed_when_zero(self):
        cfg = self.node._build_config(_make_kwargs({"seed": 0}))
        payload = self.node._build_payload(cfg, [{"role": "user", "content": "hi"}])
        self.assertNotIn("seed", payload)

    def test_parse_stream_chunk_returns_content(self):
        line = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n'
        result = self.node._parse_stream_chunk(line)
        self.assertEqual(result, "hello")

    def test_parse_stream_chunk_done_returns_none(self):
        line = b"data: [DONE]\n"
        result = self.node._parse_stream_chunk(line)
        self.assertIsNone(result)

    def test_parse_stream_chunk_empty_returns_empty(self):
        line = b"data: {\"choices\":[{\"delta\":{}}]}\n"
        result = self.node._parse_stream_chunk(line)
        self.assertEqual(result, "")

    def test_parse_stream_chunk_malformed_json_returns_empty(self):
        line = b"data: not-json\n"
        result = self.node._parse_stream_chunk(line)
        self.assertEqual(result, "")

    def test_parse_stream_chunk_non_data_line_returns_empty(self):
        line = b"ping: something\n"
        result = self.node._parse_stream_chunk(line)
        self.assertEqual(result, "")

    def test_has_description(self):
        self.assertTrue(hasattr(LLM_Node, "DESCRIPTION"))
        self.assertIsInstance(LLM_Node.DESCRIPTION, str)

    def test_mappings_exported(self):
        from LLM_Node import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
        self.assertIn("LLM_Node", NODE_CLASS_MAPPINGS)
        self.assertIn("LLM_Node", NODE_DISPLAY_NAME_MAPPINGS)

    def test_generate_timeout_returns_error_tuple(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test-key"}):
            with patch("LLM_Node.PromptServer"):
                with patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError(socket.timeout())):
                    result = self.node.generate(**_make_kwargs())
                    text, status, info = result
                    self.assertEqual(text, "")
                    self.assertFalse(status)
                    self.assertIn("timed out", info.lower())


if __name__ == "__main__":
    unittest.main()
