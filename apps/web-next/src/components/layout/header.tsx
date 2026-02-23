"use client"

import * as React from "react"
import { SettingsIcon, ChevronDownIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

export type Provider = "openai" | "gemini"

const providerLabels: Record<Provider, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
}

interface HeaderProps {
  provider: Provider
  onProviderChange: (provider: Provider) => void
  onSettingsClick?: () => void
  className?: string
  /** Slot for mobile sidebar trigger */
  leading?: React.ReactNode
}

export function Header({
  provider,
  onProviderChange,
  onSettingsClick,
  className,
  leading,
}: HeaderProps) {
  return (
    <header
      className={cn(
        "flex h-14 shrink-0 items-center gap-2 border-b bg-background px-4",
        className
      )}
    >
      {leading}

      <h1 className="text-base font-semibold tracking-tight">
        Resume Agent
      </h1>

      <div className="ml-auto flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              {providerLabels[provider]}
              <ChevronDownIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>AI Provider</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup
              value={provider}
              onValueChange={(v) => onProviderChange(v as Provider)}
            >
              <DropdownMenuRadioItem value="gemini">
                Gemini
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="openai">
                OpenAI
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>

        {onSettingsClick && (
          <Button variant="ghost" size="icon" onClick={onSettingsClick}>
            <SettingsIcon />
            <span className="sr-only">Settings</span>
          </Button>
        )}
      </div>
    </header>
  )
}
