"""Shared utility functions and constants for ComfyUI-Pack-Of-ThatAIGod.

This module is intentionally named ``_utils`` (underscore prefix) rather than
``utils`` to avoid shadowing ComfyUI's own ``utils`` package.  See DECISIONS.md D11.

Exports:
    configure_logging: Initialize structlog-based structured logging once at startup.
    get_logger: Return the shared ``ThatAIGod`` logger instance.
    handle_exceptions: Decorator wrapping a function in a try/except with structured logging.
    clamp_dimension: Clamp an integer dimension to [min, max].
    round_to_multiple: Round an integer to the nearest multiple (banker's rounding).
    round_down_to_multiple: Round an integer down to the nearest multiple.
    compute_aspect_ratio_dimensions: Compute (width, height) from a max-side and ratio.
    safe_import: Import a module by name, returning None on ImportError.
"""

from __future__ import annotations

import functools
import importlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    import structlog

F = TypeVar("F", bound=Callable[..., Any])

# Minimum pixel dimension used throughout the pack (e.g. placeholder images, clamping).
DEFAULT_MIN_DIMENSION: int = 64
# Maximum pixel dimension — matches the practical upper limit of ComfyUI workflows.
DEFAULT_MAX_DIMENSION: int = 16384
# ComfyUI requires image dimensions to be multiples of 8 for most model architectures.
DEFAULT_MULTIPLE: int = 8

# ---------------------------------------------------------------------------
# Structured logging configuration (structlog)
# ---------------------------------------------------------------------------

_LOG_CONFIGURED: bool = False


def configure_logging() -> None:
    """Initialise structlog-based structured logging for the ``ThatAIGod`` logger.

    Call this once at application startup (it is idempotent).  Uses
    ``structlog.stdlib`` processors to integrate with standard library logging
    so that existing ``logging.getLogger("ThatAIGod")`` calls continue to work
    while benefiting from structured context and JSON-friendly formatting.

    In ComfyUI, log output is typically captured by the main ComfyUI console;
    this configuration adds structured timestamps, logger names, and level
    information to every log record without requiring a separate log file.
    """
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return

    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.dev.ConsoleRenderer(sort_keys=False),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Ensure the ThatAIGod logger propagates to the root ComfyUI logger
    root = logging.getLogger()
    that_logger = logging.getLogger("ThatAIGod")
    that_logger.setLevel(logging.DEBUG)
    that_logger.handlers.clear()
    if root.handlers:
        that_logger.propagate = True

    _LOG_CONFIGURED = True


def get_logger() -> structlog.stdlib.BoundLogger:
    """Return the shared ThatAIGod logger backed by structlog.

    All nodes in the pack use a single named logger so that log output can be
    filtered or captured by name in tests.

    Returns:
        A structlog ``BoundLogger`` that can be used with structured keyword
        arguments::

            logger = get_logger()
            logger.info("node_processed", node="LLM_Node", status="ok")
    """
    configure_logging()
    import structlog
    return structlog.get_logger("ThatAIGod")


# ---------------------------------------------------------------------------
# Centralised error handling
# ---------------------------------------------------------------------------


class NodeError(Exception):
    """Base exception for all pack-specific runtime errors.

    All custom exceptions raised by nodes in this pack should inherit from
    this class so that :func:`handle_exceptions` can distinguish expected
    errors from unexpected crashes.
    """


class ConfigurationError(NodeError):
    """Raised when required configuration is missing or invalid (e.g. no API key)."""


class InputValidationError(NodeError):
    """Raised when a user-provided input fails validation."""


class ExternalServiceError(NodeError):
    """Raised when an external service (LLM API, file system) returns an error."""


def handle_exceptions(
    logger: structlog.stdlib.BoundLogger | logging.Logger | None = None,
    fallback_return: Any = None,
    reraise: tuple[type[Exception], ...] | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps a callable in centralised try/except logging.

    Every exception is logged at ERROR level via the structured logger.
    ``NodeError`` subclasses are treated as expected failures and return
    *fallback_return*.  Unexpected exceptions (``Exception``) are also caught
    and return *fallback_return* unless their type appears in *reraise*.

    Args:
        logger: Logger instance to use.  Defaults to ``get_logger()``.
        fallback_return: Value returned when the wrapped function raises
            (default ``None``).
        reraise: Tuple of exception types that should **not** be caught but
            instead re-raised (e.g. ``(KeyboardInterrupt,)``).

    Example::

        @handle_exceptions(fallback_return="fallback", reraise=(KeyboardInterrupt,))
        def risky_operation(x: int) -> str:
            if x < 0:
                raise ConfigurationError("x must be non-negative")
            return str(x)
    """
    _logger = logger or get_logger()
    _reraise = reraise or ()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except _reraise:
                raise
            except NodeError:
                _logger.exception("expected_error", func_name=func.__name__)  # type: ignore[call-arg]
                return fallback_return
            except Exception:
                _logger.exception("unexpected_error", func_name=func.__name__)  # type: ignore[call-arg]
                return fallback_return

        return wrapper  # type: ignore[return-value]

    return decorator


def clamp_dimension(value: int, min_val: int = DEFAULT_MIN_DIMENSION, max_val: int = DEFAULT_MAX_DIMENSION) -> int:
    """Clamp a dimension value between *min_val* and *max_val* (inclusive).

    Args:
        value: The integer to clamp.
        min_val: Lower bound (default: :data:`DEFAULT_MIN_DIMENSION`).
        max_val: Upper bound (default: :data:`DEFAULT_MAX_DIMENSION`).

    Returns:
        The clamped value.
    """
    return max(min_val, min(value, max_val))


def round_to_multiple(value: int, multiple: int = DEFAULT_MULTIPLE) -> int:
    """Round *value* to the nearest *multiple* using banker's rounding (round-half-to-even).

    Args:
        value: The integer to round.
        multiple: The rounding granularity (default: :data:`DEFAULT_MULTIPLE` = 8).

    Returns:
        The rounded value.
    """
    return int(round(value / multiple) * multiple)


def round_down_to_multiple(value: int, multiple: int = DEFAULT_MULTIPLE) -> int:
    """Round *value* down to the nearest *multiple* (floor division).

    Args:
        value: The integer to round down.
        multiple: The rounding granularity (default: :data:`DEFAULT_MULTIPLE` = 8).

    Returns:
        The largest multiple of *multiple* that is ≤ *value*.
    """
    return (value // multiple) * multiple


def compute_aspect_ratio_dimensions(max_side: int, ratio: float) -> tuple[int, int]:
    """Compute width and height from a max-side length and a width-to-height ratio.

    The longer side is set to *max_side*; the shorter side is derived from
    *ratio*.  Both dimensions are rounded to the nearest :data:`DEFAULT_MULTIPLE`
    (8 px) using banker's rounding and clamped to at least
    :data:`DEFAULT_MIN_DIMENSION`.

    Args:
        max_side: The target pixel count for the longest side.
        ratio: Width-to-height ratio (e.g. ``16/9`` for landscape, ``2/3`` for portrait).
            A ratio of exactly ``1.0`` produces a square image.

    Returns:
        A ``(width, height)`` tuple rounded to :data:`DEFAULT_MULTIPLE` and clamped
        to a minimum of :data:`DEFAULT_MIN_DIMENSION`.
    """
    if ratio > 1.0:
        w = float(max_side)
        h = max_side / ratio
    elif ratio < 1.0:
        h = float(max_side)
        w = max_side * ratio
    else:
        w = float(max_side)
        h = float(max_side)

    width_int = max(round_to_multiple(int(round(w))), DEFAULT_MIN_DIMENSION)
    height_int = max(round_to_multiple(int(round(h))), DEFAULT_MIN_DIMENSION)
    return width_int, height_int


def safe_import(module_name: str) -> Any | None:
    """Import *module_name* by name, returning ``None`` on any failure.

    On failure a WARNING is logged via :func:`get_logger` so that the caller
    can continue loading other modules without crashing.

    Args:
        module_name: Fully-qualified module name (e.g. ``"LLM_Node"``).

    Returns:
        The imported module object, or ``None`` if the import failed.
    """
    try:
        return importlib.import_module(module_name)
    except Exception as e:
        logger = get_logger()
        logger.warning(
            "ComfyUI-Pack-Of-ThatAIGod: failed to import %s: %s",
            module_name,
            e,
        )
        return None


__all__: list[str] = [
    "configure_logging",
    "get_logger",
    "NodeError",
    "ConfigurationError",
    "InputValidationError",
    "ExternalServiceError",
    "handle_exceptions",
    "clamp_dimension",
    "round_to_multiple",
    "round_down_to_multiple",
    "compute_aspect_ratio_dimensions",
    "safe_import",
]
