# Config Guide

This project loads config in this order:

1. `config/config.local.yaml` (recommended for local overrides)
2. `config/config.yaml` (shared defaults)

Environment variables override `api_key` placeholders.

## Rule of Thumb

- Keep `config/config.yaml` as stable team defaults.
- Keep `config/config.local.yaml` minimal and provider-specific.
- Do not commit secrets.

## Minimal Local Config (Kimi)

```yaml
provider: "kimi"
api_key: "${KIMI_API_KEY}"
model: "kimi-k2-turbo-preview"
api_base: "https://api.moonshot.cn/v1"

multi_agent:
  enabled: false

routing:
  enabled: false
```

## Minimal Local Config (Gemini)

```yaml
provider: "gemini"
api_key: "${GEMINI_API_KEY}"
model: "gemini-2.5-flash"
```

## Provider Keys

- `gemini` -> `GEMINI_API_KEY`
- `kimi` -> `KIMI_API_KEY`
- `glm` -> `GLM_API_KEY`
- `deepseek` -> `DEEPSEEK_API_KEY`
- `minimax` -> `MINIMAX_API_KEY`

## Why disable multi-agent/routing for Kimi first

`config/config.yaml` currently contains Gemini-oriented multi-agent model presets.
If you switch provider to Kimi in local config, disabling routing and multi-agent
avoids model/provider mismatch while you validate baseline behavior.
