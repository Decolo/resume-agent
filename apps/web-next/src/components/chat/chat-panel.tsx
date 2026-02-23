"use client"

import * as React from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MessageList, type ChatMessage } from "@/components/chat/message-list"
import { MessageInput } from "@/components/chat/message-input"
import { cn } from "@/lib/utils"

interface ChatPanelProps {
  messages: ChatMessage[]
  onSend: (message: string, files?: File[]) => void
  isLoading?: boolean
  hasResume?: boolean
  className?: string
}

export function ChatPanel({
  messages,
  onSend,
  isLoading,
  hasResume,
  className,
}: ChatPanelProps) {
  const bottomRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages.length])

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <ScrollArea className="flex-1 overflow-y-auto">
        <div className="flex flex-col">
          <MessageList messages={messages} />
          {isLoading && (
            <div className="px-4 pb-4">
              <div className="ml-11 flex items-center gap-1 text-sm text-muted-foreground">
                <span className="animate-pulse">Thinking</span>
                <span className="animate-bounce delay-100">.</span>
                <span className="animate-bounce delay-200">.</span>
                <span className="animate-bounce delay-300">.</span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
      <MessageInput onSend={onSend} disabled={isLoading} hasResume={hasResume} />
    </div>
  )
}
