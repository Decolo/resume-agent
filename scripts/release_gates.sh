#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Local developer machines may define SOCKS/HTTP proxy env vars that are not
# present in CI and can cause unrelated provider test failures.
unset all_proxy
unset http_proxy
unset https_proxy

echo "[release-gates] Sync dependencies..."
uv sync --frozen --extra dev

echo "[release-gates] Gate 1: API contract tests..."
uv run --extra dev pytest -q tests/test_web_api_week1.py

echo "[release-gates] Gate 2: happy-path journey..."
uv run --extra dev pytest -q \
  tests/test_web_api_week1.py::test_resume_and_jd_workflow_transitions \
  tests/test_web_api_week1.py::test_export_endpoint_creates_artifact_and_marks_exported

echo "[release-gates] Gate 3: interrupt/reject edge cases..."
uv run --extra dev pytest -q \
  tests/test_web_api_week1.py::test_reject_flow_completes_without_tool_result \
  tests/test_web_api_week1.py::test_interrupt_flow_returns_interrupted_terminal_event \
  tests/test_web_api_week1.py::test_interrupt_terminal_run_returns_200_with_current_status

echo "[release-gates] All automated release gates passed."
