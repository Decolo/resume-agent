"""Retry logic with exponential backoff for agent operations."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Callable, TypeVar, Any
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.2  # ±20% random variation


class TransientError(Exception):
    """Exception for transient errors that should be retried."""
    pass


class PermanentError(Exception):
    """Exception for permanent errors that should not be retried."""
    pass


async def retry_with_backoff(
    func: Callable[..., T],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Execute a function with exponential backoff retry logic.

    Args:
        func: Async function to execute
        config: Retry configuration
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result from successful function execution

    Raises:
        Exception: If all retry attempts fail
    """
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Success - return result
            if attempt > 0:
                logger.info(f"Retry succeeded on attempt {attempt + 1}")
            return result

        except asyncio.CancelledError:
            # Don't retry if the operation was cancelled by the user
            raise
        except PermanentError:
            # Don't retry permanent errors
            logger.error(f"Permanent error encountered, not retrying")
            raise

        except Exception as e:
            last_exception = e

            # Stop retrying if the error isn't transient
            if not is_transient_error(e):
                logger.error("Permanent error encountered, not retrying")
                raise PermanentError(str(e)) from e

            # If this was the last attempt, raise the exception
            if attempt == config.max_attempts - 1:
                logger.error(f"All {config.max_attempts} retry attempts failed")
                raise

            # Calculate delay with exponential backoff
            base_delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )

            # Add jitter (random variation) to prevent thundering herd
            jitter = base_delay * config.jitter_factor * (2 * random.random() - 1)
            delay = base_delay + jitter

            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed: {str(e)}. "
                f"Retrying in {delay:.2f}s..."
            )

            # Wait before retrying
            await asyncio.sleep(delay)

    # Should never reach here, but just in case
    raise last_exception or Exception("Retry failed with unknown error")


def is_transient_error(error: Exception) -> bool:
    """
    Determine if an error is transient and should be retried.

    Args:
        error: Exception to check

    Returns:
        True if error is transient, False otherwise
    """
    # Explicit transient wrapper
    if isinstance(error, TransientError):
        return True

    # Network-related errors
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True

    # Check error message for common transient patterns
    error_msg = str(error).lower()
    transient_patterns = [
        "timeout",
        "connection",
        "rate limit",
        "429",
        "500",
        "503",
        "504",
        "ssl",
        "eof",
        "connection reset",
        "broken pipe",
        "temporary",
        "unavailable",
    ]

    return any(pattern in error_msg for pattern in transient_patterns)
