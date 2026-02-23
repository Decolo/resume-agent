"use client"

import * as React from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

interface DiffLine {
  type: "added" | "removed" | "unchanged"
  content: string
}

interface DiffViewProps {
  before: string
  after: string
  className?: string
}

function computeDiff(before: string, after: string): DiffLine[] {
  const oldLines = before.split("\n")
  const newLines = after.split("\n")
  const lines: DiffLine[] = []

  let oi = 0
  let ni = 0

  while (oi < oldLines.length || ni < newLines.length) {
    if (oi < oldLines.length && ni < newLines.length) {
      if (oldLines[oi] === newLines[ni]) {
        lines.push({ type: "unchanged", content: oldLines[oi] })
        oi++
        ni++
      } else {
        lines.push({ type: "removed", content: oldLines[oi] })
        lines.push({ type: "added", content: newLines[ni] })
        oi++
        ni++
      }
    } else if (oi < oldLines.length) {
      lines.push({ type: "removed", content: oldLines[oi] })
      oi++
    } else {
      lines.push({ type: "added", content: newLines[ni] })
      ni++
    }
  }

  return lines
}

export function DiffView({ before, after, className }: DiffViewProps) {
  const lines = React.useMemo(() => computeDiff(before, after), [before, after])

  return (
    <ScrollArea className={cn("rounded-md border", className)}>
      <pre className="p-4 text-xs leading-relaxed font-mono">
        {lines.map((line, i) => (
          <div
            key={i}
            className={cn(
              "px-2",
              line.type === "added" && "bg-green-500/10 text-green-700 dark:text-green-400",
              line.type === "removed" && "bg-red-500/10 text-red-700 dark:text-red-400 line-through"
            )}
          >
            <span className="mr-3 inline-block w-4 select-none text-muted-foreground">
              {line.type === "added" ? "+" : line.type === "removed" ? "-" : " "}
            </span>
            {line.content || "\u00A0"}
          </div>
        ))}
      </pre>
    </ScrollArea>
  )
}
