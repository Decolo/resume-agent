import { NextRequest } from "next/server"
import { streamText, stepCountIs, convertToModelMessages, type UIMessage } from "ai"
import { getModel, type ProviderName } from "@/lib/ai/providers"
import { RESUME_EXPERT_PROMPT } from "@/lib/ai/prompts"
import { makeUpdateSectionTool, resumeTools } from "@/lib/ai/tools"

export async function POST(req: NextRequest) {
  const body = (await req.json()) as {
    messages: UIMessage[]
    provider: ProviderName
    apiKey: string
    baseURL?: string
    modelId?: string
    resume: Record<string, unknown>
  }

  if (!body.apiKey) {
    return new Response(
      JSON.stringify({ error: "API key is required" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    )
  }

  let currentResume = body.resume ?? {}

  const updateSection = makeUpdateSectionTool(
    () => currentResume,
    (next) => { currentResume = next },
  )

  const tools = {
    updateSection,
    ...resumeTools,
  }

  const model = getModel({
    provider: body.provider ?? "gemini",
    apiKey: body.apiKey,
    baseURL: body.baseURL,
    modelId: body.modelId,
  })

  const modelMessages = await convertToModelMessages(body.messages, { tools })

  const result = streamText({
    model,
    system: RESUME_EXPERT_PROMPT,
    messages: modelMessages,
    tools,
    stopWhen: stepCountIs(5),
  })

  return result.toUIMessageStreamResponse()
}
