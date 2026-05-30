import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

server_mock = MagicMock()
server_mock.PromptServer.instance.send_sync = MagicMock()
sys.modules["server"] = server_mock

import asyncio
import urllib.error

import aiohttp

from llm_utils import (
    MAX_IMAGE_DIMENSION,
    LlmConfigBuilder,
    LlmStreamer,
    _async_fetch_stream,
    _run_async,
    _run_async_stream,
    encode_image_to_base64,
    fetch_openrouter_credits,
    push_error_to_ui,
)


class TestLlmStreamerStreamResponse(unittest.TestCase):
    def test_stream_response_yields_from_async(self):
        with patch("llm_utils._run_async_stream", return_value=[b"chunk1", b"chunk2"]):
            result = list(LlmStreamer.stream_response("http://url", {}, "key", 30))
            self.assertEqual(result, [b"chunk1", b"chunk2"])

    def test_stream_response_empty(self):
        with patch("llm_utils._run_async_stream", return_value=[]):
            result = list(LlmStreamer.stream_response("http://url", {}, "key", 30))
            self.assertEqual(result, [])


class AsyncIter:
    def __init__(self, items):
        self._items = items
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        val = self._items[self._idx]
        self._idx += 1
        return val


class TestAsyncFetchStream(unittest.TestCase):
    def _make_mock_session(self, content_lines=None):
        content_lines = content_lines or [b"line1\n", b"line2\n"]
        mock_response = MagicMock()
        mock_response.content = AsyncIter(content_lines)
        mock_response.raise_for_status = MagicMock()

        mock_post_cm = MagicMock()
        mock_post_cm.__aenter__.return_value = mock_response
        mock_post_cm.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_cm
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        return mock_session

    def test_async_fetch_stream_success(self):
        async def run():
            mock_session = self._make_mock_session([b"line1\n", b"line2\n"])
            with patch("aiohttp.ClientSession", return_value=mock_session):
                return await _async_fetch_stream("http://test/url", {"model": "x"}, "sk-key", 10)

        result = asyncio.run(run())
        self.assertEqual(result, [b"line1\n", b"line2\n"])

    def test_async_fetch_stream_passes_authorization_header(self):
        mock_session = self._make_mock_session()

        async def run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                return await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        asyncio.run(run())
        args, kwargs = mock_session.post.call_args
        self.assertIn("Authorization", kwargs.get("headers", {}))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-key")


class TestRunAsyncStream(unittest.TestCase):
    def test_run_async_stream_propagates_error_on_http_error(self):
        with patch("llm_utils._async_fetch_stream", side_effect=aiohttp.ClientResponseError(
            status=403, message="Forbidden", request_info=MagicMock(), history=()
        )):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                _run_async_stream("http://url", {}, "key", 30)
            self.assertEqual(ctx.exception.code, 403)

    def test_run_async_stream_raises_timeout(self):
        with patch("llm_utils._async_fetch_stream", side_effect=asyncio.TimeoutError):
            with self.assertRaises(urllib.error.URLError):
                _run_async_stream("http://url", {}, "key", 30)

    def test_run_async_stream_raises_timeout_on_socket_timeout(self):
        with patch("llm_utils._async_fetch_stream", side_effect=TimeoutError("timed out")):
            with self.assertRaises(urllib.error.URLError):
                _run_async_stream("http://url", {}, "key", 30)

    def test_run_async_stream_raises_on_generic_client_error(self):
        with patch("llm_utils._async_fetch_stream", side_effect=aiohttp.ClientError("connection failed")):
            with self.assertRaises(urllib.error.URLError) as ctx:
                _run_async_stream("http://url", {}, "key", 30)
            self.assertIn("connection failed", str(ctx.exception.reason))

    def test_run_async_stream_success(self):
        with patch("llm_utils._async_fetch_stream", return_value=[b"data"]):
            result = _run_async_stream("http://url", {}, "key", 30)
            self.assertEqual(result, [b"data"])


class TestLlmConfigBuilder(unittest.TestCase):
    def test_build_config_defaults(self):
        cfg = LlmConfigBuilder.build_config({})
        self.assertEqual(cfg["mode"], "OpenRouter")

    def test_resolve_api_config_openrouter_success(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-key"}):
            url, key, err = LlmConfigBuilder.resolve_api_config({
                "mode": "OpenRouter", "api_key_env_var": "OPENROUTER_API_KEY",
                "user_prompt": "hi", "vision_image": None,
            })
            self.assertIsNone(err)

    def test_resolve_api_config_openrouter_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            url, key, err = LlmConfigBuilder.resolve_api_config({
                "mode": "OpenRouter", "api_key_env_var": "OPENROUTER_API_KEY",
                "user_prompt": "hi", "vision_image": None,
            })
            self.assertIsNotNone(err)

    def test_resolve_api_config_empty_prompt_no_image(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-key"}):
            url, key, err = LlmConfigBuilder.resolve_api_config({
                "mode": "OpenRouter", "api_key_env_var": "OPENROUTER_API_KEY",
                "user_prompt": "   ", "vision_image": None,
            })
            self.assertIsNotNone(err)

    def test_resolve_api_config_local_success(self):
        url, key, err = LlmConfigBuilder.resolve_api_config({
            "mode": "Local", "local_url": "http://localhost:1234/v1",
            "user_prompt": "hi", "vision_image": None,
        })
        self.assertIsNone(err)
        self.assertTrue(url.endswith("/chat/completions"))

    def test_resolve_api_config_local_rejects_external(self):
        url, key, err = LlmConfigBuilder.resolve_api_config({
            "mode": "Local", "local_url": "http://evil.com:9999",
            "user_prompt": "hi", "vision_image": None,
        })
        self.assertIsNotNone(err)

    def test_build_messages_with_image(self):
        msgs = LlmConfigBuilder.build_messages("sys", "user", "b64img")
        self.assertIsInstance(msgs[1]["content"], list)
        self.assertEqual(msgs[1]["content"][1]["type"], "image_url")

    def test_build_messages_without_image(self):
        msgs = LlmConfigBuilder.build_messages("sys", "user", None)
        self.assertEqual(msgs[1]["content"], "user")

    def test_build_payload_includes_seed_when_nonzero(self):
        cfg = {"model_name": "m", "temperature": 0.7, "max_tokens": 100, "seed": 42}
        payload = LlmConfigBuilder.build_payload(cfg, [])
        self.assertEqual(payload["seed"], 42)

    def test_build_payload_omits_seed_when_zero(self):
        cfg = {"model_name": "m", "temperature": 0.7, "max_tokens": 100, "seed": 0}
        payload = LlmConfigBuilder.build_payload(cfg, [])
        self.assertNotIn("seed", payload)


class TestEncodeImage(unittest.TestCase):
    def test_encode_image_to_base64(self):
        import torch
        dummy = torch.zeros((1, 64, 64, 3))
        result = encode_image_to_base64(dummy)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_encode_image_to_base64_valid(self):
        import base64

        import torch
        dummy = torch.ones((1, 64, 64, 3)) * 127
        result = encode_image_to_base64(dummy)
        decoded = base64.b64decode(result)
        self.assertGreater(len(decoded), 0)


class TestFetchCredits(unittest.TestCase):
    def test_fetch_openrouter_credits_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "data": {"total_credits": 20.0, "total_usage": 5.0}
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = fetch_openrouter_credits("sk-key")
            self.assertEqual(result, "$15.00")

    def test_fetch_openrouter_credits_no_data_key(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"error": "bad"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = fetch_openrouter_credits("sk-key")
            self.assertIsNone(result)

    def test_fetch_openrouter_credits_failure_returns_none(self):
        with patch.object(urllib.request, "urlopen", side_effect=OSError("err")):
            result = fetch_openrouter_credits("sk-key")
            self.assertIsNone(result)


class TestPushError(unittest.TestCase):
    def test_push_error_to_ui_with_unique_id(self):
        with patch("llm_utils.PromptServer.instance.send_sync") as mock_send:
            push_error_to_ui("uid_1", "test error")
            mock_send.assert_called_once()

    def test_push_error_to_ui_without_unique_id(self):
        with patch("llm_utils.PromptServer.instance.send_sync") as mock_send:
            push_error_to_ui(None, "test error")
            mock_send.assert_not_called()


class TestRetryLogic(unittest.TestCase):
    def _make_async_cm(self, obj):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=obj)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    def _make_raising_cm(self, exc):
        cm = MagicMock()

        async def raise_on_enter(_self=None):
            raise exc

        cm.__aenter__ = raise_on_enter
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    def test_retry_on_429_then_success(self):
        resp_429 = MagicMock()
        resp_429.status = 429
        resp_429.headers = {}
        resp_429.raise_for_status = MagicMock()

        resp_200 = MagicMock()
        resp_200.status = 200
        resp_200.raise_for_status = MagicMock()
        resp_200.content = AsyncIter([b"data\n"])

        call_count = [0]
        def post_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return self._make_async_cm(resp_429)
            return self._make_async_cm(resp_200)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=post_side_effect)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with patch("llm_utils.asyncio.sleep", new_callable=AsyncMock):
                    return await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        asyncio.run(run())
        self.assertEqual(mock_session.post.call_count, 2)

    def test_no_retry_on_401(self):
        resp_401 = MagicMock()
        resp_401.status = 401
        resp_401.raise_for_status = MagicMock(side_effect=aiohttp.ClientResponseError(
            status=401, message="Unauthorized", request_info=MagicMock(), history=()
        ))

        mock_session = MagicMock()
        mock_session.post.return_value = self._make_async_cm(resp_401)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with self.assertRaises(aiohttp.ClientResponseError):
                    await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        asyncio.run(run())

    def test_retry_exhausted_returns_last_error_data(self):
        resp_502 = MagicMock()
        resp_502.status = 502
        resp_502.headers = {}
        resp_502.raise_for_status = MagicMock()
        resp_502.content = AsyncIter([b"error data\n"])

        mock_session = MagicMock()
        mock_session.post.return_value = self._make_async_cm(resp_502)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with patch("llm_utils.asyncio.sleep", new_callable=AsyncMock):
                    return await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        asyncio.run(run())
        self.assertEqual(mock_session.post.call_count, 3)

    def test_retry_on_client_error_then_success(self):
        call_count = [0]
        resp_ok = MagicMock()
        resp_ok.status = 200
        resp_ok.raise_for_status = MagicMock()
        resp_ok.content = AsyncIter([b"data\n"])

        def post_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return self._make_raising_cm(aiohttp.ClientError("connection reset"))
            return self._make_async_cm(resp_ok)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=post_side_effect)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with patch("llm_utils.asyncio.sleep", new_callable=AsyncMock):
                    return await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        asyncio.run(run())
        self.assertEqual(mock_session.post.call_count, 2)

    def test_retry_on_timeout_then_success(self):
        call_count = [0]
        resp_ok = MagicMock()
        resp_ok.status = 200
        resp_ok.raise_for_status = MagicMock()
        resp_ok.content = AsyncIter([b"data\n"])

        def post_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return self._make_raising_cm(TimeoutError("timed out"))
            return self._make_async_cm(resp_ok)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=post_side_effect)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with patch("llm_utils.asyncio.sleep", new_callable=AsyncMock):
                    return await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        asyncio.run(run())
        self.assertEqual(mock_session.post.call_count, 2)

    def test_retry_on_client_response_error_then_success(self):
        call_count = [0]
        resp_ok = MagicMock()
        resp_ok.status = 200
        resp_ok.raise_for_status = MagicMock()
        resp_ok.content = AsyncIter([b"data\n"])

        def post_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return self._make_raising_cm(aiohttp.ClientResponseError(
                    status=502, message="Bad Gateway",
                    request_info=MagicMock(), history=()
                ))
            return self._make_async_cm(resp_ok)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=post_side_effect)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with patch("llm_utils.asyncio.sleep", new_callable=AsyncMock):
                    return await _async_fetch_stream("http://test/url", {}, "sk-key", 10)

        result = asyncio.run(run())
        self.assertEqual(call_count[0], 2)
        self.assertEqual(result, [b"data\n"])

    def test_retry_on_client_error_exhausted(self):
        mock_session = MagicMock()
        exc = aiohttp.ClientError("connection failed repeatedly")
        mock_session.post.return_value = self._make_raising_cm(exc)

        async def run():
            with patch("aiohttp.ClientSession", return_value=self._make_async_cm(mock_session)):
                with patch("llm_utils.asyncio.sleep", new_callable=AsyncMock):
                    try:
                        await _async_fetch_stream("http://test/url", {}, "sk-key", 10)
                        self.fail("Expected an exception")
                    except aiohttp.ClientError:
                        pass

        asyncio.run(run())
        self.assertEqual(mock_session.post.call_count, 3)


class TestRunAsync(unittest.TestCase):
    def test_run_async_no_loop(self):
        async def dummy():
            return 42
        result = _run_async(dummy())
        self.assertEqual(result, 42)

    def test_run_async_from_loop(self):
        async def run():
            async def dummy():
                return 99
            result = _run_async(dummy())
            self.assertEqual(result, 99)
        asyncio.run(run())


class TestEncodeImageEdgeCases(unittest.TestCase):
    def test_encode_image_oversized_raises(self):
        import torch
        large = torch.zeros((1, MAX_IMAGE_DIMENSION + 1, 64, 3))
        with self.assertRaises(ValueError):
            encode_image_to_base64(large)


class TestCreditsCache(unittest.TestCase):
    def test_fetch_openrouter_credits_cache_hit(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "data": {"total_credits": 50.0, "total_usage": 10.0}
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            first = fetch_openrouter_credits("cache-test-key-2")
            self.assertEqual(first, "$40.00")

        second = fetch_openrouter_credits("cache-test-key-2")
        self.assertEqual(second, "$40.00")


class AsyncMock:
    def __init__(self, return_value=None, **kwargs):
        self._return_value = return_value

    def __call__(self, *args, **kwargs):
        return self

    def __await__(self):
        return self._async().__await__()

    async def _async(self):
        return self._return_value


if __name__ == "__main__":
    unittest.main()
