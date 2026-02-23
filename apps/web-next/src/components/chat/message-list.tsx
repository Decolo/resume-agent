"use client"

import * as React from "react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export type MessageRole = "user" | "assistant" | "tool"

export interface ToolCallResult {
  toolName: string
  args?: Record<string, unknown>
  result?: string
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  toolCall?: ToolCallResult
  createdAt?: Date
}

interface MessageListProps {
  messages: ChatMessage[]
  className?: string
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3">
      <Avatar size="sm">
        <AvatarFallback>U</AvatarFallback>
      </Avatar>
      <div className="flex-1 rounded-lg bg-muted px-3 py-2 text-sm">
        {content}
      </div>
    </div>
  )
}

function AssistantMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3">
      <Avatar size="sm">
        <AvatarFallback className="bg-primary text-primary-foreground">
          AI
        </AvatarFallback>
      </Avatar>
      <div
        className="prose prose-sm dark:prose-invert max-w-none flex-1 text-sm"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
      />
    </div>
  )
}

function ToolMessage({ toolCall }: { toolCall: ToolCallResult }) {
  return (
    <div className="ml-11 rounded-md border bg-muted/50 p-3">
      <div className="mb-1 flex items-center gap-2">
        <Badge variant="outline" className="font-mono text-xs">
          {toolCall.toolName}
        </Badge>
      </div>
      {toolCall.result && (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
          {toolCall.result}
        </pre>
      )}
    </div>
  )
}

/**
 * Minimal markdown-to-HTML: handles **bold**, *italic*, `code`,
 * code blocks, and newlines. For production, swap in a proper
 * markdown library (e.g. react-markdown).
 */
function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
  // code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
  // inline code
  html = html.replace(/`([^`]+)`/g, '<code class="bg-muted px-1 rounded text-xs">$1</code>')
  // bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
  // italic
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>")
  // line breaks
  html = html.replace(/\n/g, "<br/>")
  return html
}

export function MessageList({ messages, className }: MessageListProps) {
  return (
    <div className={cn("flex flex-col gap-4 p-4", className)}>
      {messages.map((msg) => {
        switch (msg.role) {
          case "user":
            return <UserMessage key={msg.id} content={msg.content} />
          case "assistant":
            return <AssistantMessage key={msg.id} content={msg.content} />
          case "tool":
            return msg.toolCall ? (
              <ToolMessage key={msg.id} toolCall={msg.toolCall} />
            ) : null
          default:
            return null
        }
      })}
    </div>
  )
}
