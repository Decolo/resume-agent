"use client"

import * as React from "react"
import { UploadIcon, SparklesIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  onUpload: (file: File) => void
  onCreateNew: () => void
  className?: string
}

export function EmptyState({ onUpload, onCreateNew, className }: EmptyStateProps) {
  const [isDragging, setIsDragging] = React.useState(false)
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave() {
    setIsDragging(false)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file)
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) onUpload(file)
  }

  return (
    <div className={cn("flex h-full items-center justify-center p-8", className)}>
      <div className="w-full max-w-md space-y-6">
        <div
          className={cn(
            "rounded-lg border-2 border-dashed p-8 text-center transition-colors",
            isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <UploadIcon className="mx-auto h-12 w-12 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-semibold">Upload your resume</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Drag and drop your resume file here, or click to browse
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Supports .json, .md, .txt
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => fileInputRef.current?.click()}
          >
            Browse files
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".json,.md,.txt"
            onChange={handleFileChange}
          />
        </div>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-background px-2 text-muted-foreground">or</span>
          </div>
        </div>

        <div className="rounded-lg border p-6 text-center">
          <SparklesIcon className="mx-auto h-10 w-10 text-primary" />
          <h3 className="mt-3 text-lg font-semibold">Start from scratch</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Create a new resume with AI assistance
          </p>
          <Button className="mt-4" onClick={onCreateNew}>
            Create new resume
          </Button>
        </div>
      </div>
    </div>
  )
}
