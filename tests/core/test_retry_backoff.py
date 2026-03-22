"""Behavior tests for retry backoff execution."""

from __future__ import annotations

import pytest

from resume_agent.core.retry import PermanentError, RetryConfig, TransientError, retry_with_backoff


@pytest.mark.asyncio
async def test_retry_returns_first_success_without_additional_attempts() -> None:
    call_count = 0

    async def succeed_once() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    result = await retry_with_backoff(succeed_once, RetryConfig(max_attempts=3, base_delay=0.1))

    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_retries_transient_failures_until_a_later_attempt_succeeds() -> None:
    call_count = 0

    async def flaky_operation() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TransientError("Temporary failure")
        return "success"

    result = await retry_with_backoff(flaky_operation, RetryConfig(max_attempts=5, base_delay=0.05))

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_does_not_repeat_attempts_after_a_permanent_error() -> None:
    call_count = 0

    async def permanently_failing_operation() -> str:
        nonlocal call_count
        call_count += 1
        raise PermanentError("Permanent failure")

    with pytest.raises(PermanentError):
        await retry_with_backoff(
            permanently_failing_operation,
            RetryConfig(max_attempts=3, base_delay=0.05),
        )

    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_raises_after_exhausting_max_attempts_on_transient_errors() -> None:
    call_count = 0

    async def always_fail_transiently() -> str:
        nonlocal call_count
        call_count += 1
        raise TransientError("Always fails")

    with pytest.raises(TransientError):
        await retry_with_backoff(
            always_fail_transiently,
            RetryConfig(max_attempts=3, base_delay=0.05),
        )

    assert call_count == 3


def test_retry_backoff_grows_exponentially_when_jitter_is_disabled() -> None:
    config = RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        exponential_base=2.0,
        jitter_factor=0.0,
    )

    expected_delays = [1.0, 2.0, 4.0, 8.0]
    for attempt, expected in enumerate(expected_delays):
        delay = min(config.base_delay * (config.exponential_base**attempt), config.max_delay)
        assert delay == expected
