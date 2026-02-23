"use client"

import * as React from "react"
import { SendIcon, PaperclipIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

interface MessageInputProps {
  onSend: (message: string, files?: File[]) => void
  disabled?: boolean
  hasResume?: boolean
  className?: string
}

export function MessageInput({ onSend, disabled, hasResume, className }: MessageInputProps) {
  const [value, setValue] = React.useState("")
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const [files, setFiles] = React.useState<File[]>([])

  const canSend = value.trim().length > 0 || files.length > 0

  function handleSend() {
    if (!canSend || disabled) return
    onSend(value.trim(), files.length > 0 ? files : undefined)
    setValue("")
    setFiles([])
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault()
      handleSend()
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files
    if (selected) {
      setFiles(Array.from(selected))
    }
  }

  return (
    <div className={cn("border-t bg-background p-4", className)}>
      {files.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {files.map((f, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs"
            >
              {f.name}
              <button
                type="button"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                className="text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${f.name}`}
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
              >
                <PaperclipIcon />
                <span className="sr-only">Attach file</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {hasResume ? "Replace resume file" : "Attach resume file"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.md,.json,.html,.txt"
          onChange={handleFileChange}
        />
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your resume... (Cmd+Enter to send)"
          disabled={disabled}
          className="min-h-10 max-h-40 flex-1 resize-none"
          rows={1}
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!canSend || disabled}
        >
          <SendIcon />
          <span className="sr-only">Send message</span>
        </Button>
      </div>
    </div>
  )
}
