import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _utils import (
    ConfigurationError,
    ExternalServiceError,
    InputValidationError,
    NodeError,
    clamp_dimension,
    compute_aspect_ratio_dimensions,
    configure_logging,
    get_logger,
    handle_exceptions,
    round_down_to_multiple,
    round_to_multiple,
    safe_import,
)


class TestUtils(unittest.TestCase):
    def test_get_logger_returns_named_logger(self):
        logger = get_logger()
        self.assertEqual(logger.name, "ThatAIGod")

    def test_clamp_dimension_within_range(self):
        self.assertEqual(clamp_dimension(512, 64, 16384), 512)

    def test_clamp_dimension_below_min(self):
        self.assertEqual(clamp_dimension(32, 64, 16384), 64)

    def test_clamp_dimension_above_max(self):
        self.assertEqual(clamp_dimension(20000, 64, 16384), 16384)

    def test_round_to_multiple_even(self):
        # Python 3 round uses bankers' rounding: 12.5 -> 12
        self.assertEqual(round_to_multiple(100, 8), 96)

    def test_round_to_multiple_exact(self):
        self.assertEqual(round_to_multiple(104, 8), 104)

    def test_round_to_multiple_odd(self):
        self.assertEqual(round_to_multiple(7, 8), 8)

    def test_compute_aspect_ratio_landscape(self):
        w, h = compute_aspect_ratio_dimensions(1024, 16 / 9)
        self.assertAlmostEqual(w / h, 16 / 9, delta=0.02)
        self.assertGreaterEqual(w, 64)
        self.assertGreaterEqual(h, 64)

    def test_compute_aspect_ratio_portrait(self):
        w, h = compute_aspect_ratio_dimensions(1024, 2 / 3)
        self.assertAlmostEqual(w / h, 2 / 3, delta=0.02)
        self.assertLessEqual(w, h)

    def test_compute_aspect_ratio_square(self):
        w, h = compute_aspect_ratio_dimensions(1024, 1.0)
        self.assertEqual(w, h)

    def test_compute_aspect_ratio_min_dimension(self):
        w, h = compute_aspect_ratio_dimensions(1, 1.0)
        self.assertGreaterEqual(w, 64)
        self.assertGreaterEqual(h, 64)

    def test_safe_import_nonexistent_module(self):
        result = safe_import("nonexistent_module_xyz")
        self.assertIsNone(result)

    def test_safe_import_existing_module(self):
        with patch("importlib.import_module", return_value=unittest.mock.MagicMock()):
            result = safe_import("utils")
            self.assertIsNotNone(result)

    def test_round_down_to_multiple_within_range(self):
        self.assertEqual(round_down_to_multiple(100, 8), 96)

    def test_round_down_to_multiple_exact(self):
        self.assertEqual(round_down_to_multiple(104, 8), 104)

    def test_round_down_to_multiple_below_multiple(self):
        self.assertEqual(round_down_to_multiple(5, 8), 0)

    def test_round_down_to_multiple_custom_multiple(self):
        self.assertEqual(round_down_to_multiple(50, 16), 48)

    def test_round_down_to_multiple_zero_value(self):
        self.assertEqual(round_down_to_multiple(0, 8), 0)


class TestErrorHandling(unittest.TestCase):
    """Tests for structured logging, custom exceptions, and handle_exceptions."""

    def test_configure_logging_is_idempotent(self):
        """configure_logging should be safe to call multiple times."""
        configure_logging()
        configure_logging()  # second call should not raise
        self.assertTrue(True)

    def test_get_logger_returns_structlog_logger(self):
        """get_logger should return a structlog BoundLogger."""
        logger = get_logger()
        # structlog's BoundLogger has a .name property that forwards to the wrapped logger
        self.assertEqual(logger.name, "ThatAIGod")

    def test_node_error_hierarchy(self):
        """NodeError should be the base for all custom exceptions."""
        self.assertTrue(issubclass(ConfigurationError, NodeError))
        self.assertTrue(issubclass(InputValidationError, NodeError))
        self.assertTrue(issubclass(ExternalServiceError, NodeError))
        self.assertIsInstance(ConfigurationError("test"), Exception)
        self.assertIsInstance(InputValidationError("test"), Exception)
        self.assertIsInstance(ExternalServiceError("test"), Exception)

    def test_handle_exceptions_catches_node_error(self):
        """handle_exceptions should catch NodeError subclasses and return fallback."""

        @handle_exceptions(fallback_return="fallback_val")
        def failing_fn() -> str:
            raise ConfigurationError("bad config")

        result = failing_fn()
        self.assertEqual(result, "fallback_val")

    def test_handle_exceptions_catches_unexpected_exception(self):
        """handle_exceptions should catch unexpected Exception types."""

        @handle_exceptions(fallback_return=42)
        def unexpected_fn() -> int:
            raise RuntimeError("unexpected")

        result = unexpected_fn()
        self.assertEqual(result, 42)

    def test_handle_exceptions_reraises_specified_types(self):
        """handle_exceptions should re-raise exception types listed in reraise."""

        @handle_exceptions(fallback_return="x", reraise=(ValueError,))
        def re_raise_fn() -> str:
            raise ValueError("must propagate")

        with self.assertRaises(ValueError):
            re_raise_fn()

    def test_handle_exceptions_passes_through_on_success(self):
        """handle_exceptions should return the original function result on success."""

        @handle_exceptions(fallback_return=None)
        def success_fn(x: int) -> int:
            return x * 2

        self.assertEqual(success_fn(5), 10)

    def test_handle_exceptions_custom_logger(self):
        """handle_exceptions should accept a custom logger."""
        mock_logger = MagicMock()
        # MagicMock doesn't have .exception method by default, but it auto-creates attrs

        @handle_exceptions(logger=mock_logger, fallback_return="fb")
        def failing_fn() -> str:
            raise ConfigurationError("test")

        result = failing_fn()
        self.assertEqual(result, "fb")
        # Check that .exception() was called on the mock logger
        mock_logger.exception.assert_called_once()


class TestErrorHandlingIntegration(unittest.TestCase):
    """Integration-style tests that verify the full flow."""

    def test_handle_exceptions_with_configured_logging(self):
        """Verify handle_exceptions works with the real structured logger."""
        configure_logging()

        @handle_exceptions(fallback_return="fallback")
        def fn() -> str:
            raise InputValidationError("invalid input")

        result = fn()
        self.assertEqual(result, "fallback")

    def test_all_error_types_work_with_handle_exceptions(self):
        """All custom error types should be caught by handle_exceptions."""
        configure_logging()

        for error_type in [ConfigurationError, InputValidationError, ExternalServiceError]:

            @handle_exceptions(fallback_return="caught")
            def fn() -> str:
                raise error_type(f"test {error_type.__name__}")

            result = fn()
            self.assertEqual(result, "caught")


if __name__ == "__main__":
    unittest.main()
