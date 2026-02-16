"""Compatibility checks for Slice B providers extraction."""

from __future__ import annotations

from packages.providers.resume_agent_providers import (
    PROVIDER_DEFAULTS as PACKAGE_PROVIDER_DEFAULTS,
)
from packages.providers.resume_agent_providers import (
    ChatProvider as PackageChatProvider,
)
from packages.providers.resume_agent_providers import (
    GeminiProvider as PackageGeminiProvider,
)
from packages.providers.resume_agent_providers import (
    OpenAICompatibleProvider as PackageOpenAICompatibleProvider,
)
from packages.providers.resume_agent_providers import (
    create_provider as package_create_provider,
)
from packages.providers.resume_agent_providers.types import (
    FunctionCall as PackageFunctionCall,
)
from packages.providers.resume_agent_providers.types import (
    GenerationConfig as PackageGenerationConfig,
)
from resume_agent.providers import (
    PROVIDER_DEFAULTS,
    ChatProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
    create_provider,
)
from resume_agent.providers.types import FunctionCall, GenerationConfig


def test_provider_exports_are_compatible_with_package_source() -> None:
    assert ChatProvider is PackageChatProvider
    assert GeminiProvider is PackageGeminiProvider
    assert OpenAICompatibleProvider is PackageOpenAICompatibleProvider
    assert create_provider is package_create_provider
    assert PROVIDER_DEFAULTS == PACKAGE_PROVIDER_DEFAULTS


def test_provider_types_are_compatible_with_package_source() -> None:
    assert FunctionCall is PackageFunctionCall
    assert GenerationConfig is PackageGenerationConfig
