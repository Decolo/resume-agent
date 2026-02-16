## Summary
- What changed and why.

## Validation
- [ ] `uv run --extra dev ruff check .`
- [ ] `uv run --extra dev mypy`
- [ ] `env -u all_proxy -u http_proxy -u https_proxy uv run --extra dev pytest -q`
- [ ] `./scripts/release_gates.sh` (for release-impacting changes)

## Risk
- [ ] Backward compatibility checked
- [ ] No secrets/PII introduced
- [ ] Rollback path is clear

## Notes
- Link relevant docs/checklist updates if behavior or operations changed.
