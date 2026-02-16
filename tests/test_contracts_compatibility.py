"""Compatibility checks for Slice A contracts extraction."""

from __future__ import annotations

from resume_agent.contracts.web.runtime import (
    ACTIVE_RUN_STATES as CONTRACT_ACTIVE_RUN_STATES,
)
from resume_agent.contracts.web.runtime import (
    DEFAULT_ALLOWED_UPLOAD_MIME_TYPES as CONTRACT_ALLOWED_UPLOAD_MIME_TYPES,
)
from resume_agent.contracts.web.runtime import (
    DEFAULT_COST_PER_MILLION_TOKENS as CONTRACT_DEFAULT_COST,
)
from resume_agent.contracts.web.runtime import (
    TERMINAL_RUN_STATES as CONTRACT_TERMINAL_RUN_STATES,
)
from resume_agent.contracts.web.runtime import (
    WORKFLOW_ORDER as CONTRACT_WORKFLOW_ORDER,
)
from resume_agent.contracts.web.settings import CleanupResponse as ContractCleanupResponse
from resume_agent.web.api.v1.endpoints import settings as settings_endpoint
from resume_agent.web.store import (
    ACTIVE_RUN_STATES as STORE_ACTIVE_RUN_STATES,
)
from resume_agent.web.store import (
    DEFAULT_ALLOWED_UPLOAD_MIME_TYPES as STORE_ALLOWED_UPLOAD_MIME_TYPES,
)
from resume_agent.web.store import (
    DEFAULT_COST_PER_MILLION_TOKENS as STORE_DEFAULT_COST,
)
from resume_agent.web.store import (
    TERMINAL_RUN_STATES as STORE_TERMINAL_RUN_STATES,
)
from resume_agent.web.store import (
    WORKFLOW_ORDER as STORE_WORKFLOW_ORDER,
)


def test_store_runtime_constants_match_contracts() -> None:
    assert STORE_TERMINAL_RUN_STATES == CONTRACT_TERMINAL_RUN_STATES
    assert STORE_ACTIVE_RUN_STATES == CONTRACT_ACTIVE_RUN_STATES
    assert STORE_WORKFLOW_ORDER == CONTRACT_WORKFLOW_ORDER
    assert STORE_ALLOWED_UPLOAD_MIME_TYPES == CONTRACT_ALLOWED_UPLOAD_MIME_TYPES
    assert STORE_DEFAULT_COST == CONTRACT_DEFAULT_COST


def test_settings_endpoint_reexports_contract_models() -> None:
    assert settings_endpoint.CleanupResponse is ContractCleanupResponse
