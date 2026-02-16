"""CLI stream-mode command behavior tests."""

from __future__ import annotations

import pytest

from apps.cli.resume_agent_cli.app import handle_command


@pytest.mark.asyncio
async def test_stream_command_updates_runtime_options() -> None:
    runtime_options = {"stream_enabled": True, "stream_render_mode": "md"}

    assert await handle_command("/stream status", object(), runtime_options=runtime_options)
    assert runtime_options["stream_enabled"] is True

    assert await handle_command("/stream off", object(), runtime_options=runtime_options)
    assert runtime_options["stream_enabled"] is False

    assert await handle_command("/stream on", object(), runtime_options=runtime_options)
    assert runtime_options["stream_enabled"] is True


@pytest.mark.asyncio
async def test_stream_command_without_runtime_options_is_noop() -> None:
    assert await handle_command("/stream on", object())


@pytest.mark.asyncio
async def test_stream_render_command_updates_runtime_options() -> None:
    runtime_options = {"stream_enabled": True, "stream_render_mode": "md"}

    assert await handle_command("/stream-render status", object(), runtime_options=runtime_options)
    assert runtime_options["stream_render_mode"] == "md"

    assert await handle_command("/stream-render raw", object(), runtime_options=runtime_options)
    assert runtime_options["stream_render_mode"] == "raw"

    assert await handle_command("/stream-render hybrid", object(), runtime_options=runtime_options)
    assert runtime_options["stream_render_mode"] == "hybrid"
