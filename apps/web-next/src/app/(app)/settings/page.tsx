"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const PROVIDERS = [
  { value: "gemini", label: "Google Gemini", placeholder: "AIza..." },
  { value: "openai", label: "OpenAI", placeholder: "sk-..." },
] as const

export default function SettingsPage() {
  const [provider, setProvider] = React.useState("gemini")
  const [apiKey, setApiKey] = React.useState("")
  const [baseURL, setBaseURL] = React.useState("")
  const [modelId, setModelId] = React.useState("")
  const [saved, setSaved] = React.useState(false)

  React.useEffect(() => {
    setApiKey(localStorage.getItem("resume-agent-api-key") ?? "")
    setProvider(localStorage.getItem("resume-agent-provider") ?? "gemini")
    setBaseURL(localStorage.getItem("resume-agent-base-url") ?? "")
    setModelId(localStorage.getItem("resume-agent-model-id") ?? "")
  }, [])

  function handleSave() {
    localStorage.setItem("resume-agent-api-key", apiKey)
    localStorage.setItem("resume-agent-provider", provider)
    localStorage.setItem("resume-agent-base-url", baseURL)
    localStorage.setItem("resume-agent-model-id", modelId)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const currentProvider = PROVIDERS.find((p) => p.value === provider) ?? PROVIDERS[0]

  return (
    <div className="mx-auto max-w-xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>AI Provider</CardTitle>
          <CardDescription>
            Choose your AI provider and enter your API key. Keys are stored
            locally in your browser. Use &quot;OpenAI&quot; for any OpenAI-compatible
            API (Kimi, DeepSeek, etc.) with a custom Base URL.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            {PROVIDERS.map((p) => (
              <Button
                key={p.value}
                variant={provider === p.value ? "default" : "outline"}
                size="sm"
                onClick={() => setProvider(p.value)}
              >
                {p.label}
              </Button>
            ))}
          </div>

          <div className="space-y-2">
            <label htmlFor="api-key" className="text-sm font-medium">
              API Key
            </label>
            <Input
              id="api-key"
              type="password"
              placeholder={currentProvider.placeholder}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="base-url" className="text-sm font-medium">
              Base URL <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <Input
              id="base-url"
              type="url"
              placeholder="https://api.moonshot.cn/v1"
              value={baseURL}
              onChange={(e) => setBaseURL(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Custom API endpoint for OpenAI-compatible providers (Kimi, DeepSeek, etc.)
            </p>
          </div>

          <div className="space-y-2">
            <label htmlFor="model-id" className="text-sm font-medium">
              Model ID <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <Input
              id="model-id"
              placeholder="e.g. kimi-k2.5, deepseek-chat"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Leave empty to use the default model for the selected provider.
            </p>
          </div>

          <Button onClick={handleSave}>
            {saved ? "Saved ✓" : "Save Settings"}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
