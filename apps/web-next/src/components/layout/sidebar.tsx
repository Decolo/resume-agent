"use client"

import * as React from "react"
import { PlusIcon, MessageSquareIcon, MenuIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { cn } from "@/lib/utils"

export interface Session {
  id: string
  title: string
  updatedAt: Date
}

interface SidebarProps {
  sessions: Session[]
  activeSessionId?: string
  onSelectSession: (id: string) => void
  onNewSession: () => void
  className?: string
}

function formatRelativeTime(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 1) return "just now"
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  return date.toLocaleDateString()
}

function SessionList({
  sessions,
  activeSessionId,
  onSelectSession,
}: Pick<SidebarProps, "sessions" | "activeSessionId" | "onSelectSession">) {
  if (sessions.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-sm text-muted-foreground">
        No sessions yet
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1 px-2">
      {sessions.map((session) => (
        <button
          key={session.id}
          onClick={() => onSelectSession(session.id)}
          className={cn(
            "flex items-start gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent",
            activeSessionId === session.id && "bg-accent text-accent-foreground"
          )}
        >
          <MessageSquareIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{session.title}</p>
            <p className="text-xs text-muted-foreground">
              {formatRelativeTime(session.updatedAt)}
            </p>
          </div>
        </button>
      ))}
    </div>
  )
}

function SidebarContent(props: SidebarProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="p-3">
        <Button onClick={props.onNewSession} className="w-full" size="sm">
          <PlusIcon />
          New Session
        </Button>
      </div>
      <Separator />
      <ScrollArea className="flex-1">
        <div className="py-2">
          <SessionList
            sessions={props.sessions}
            activeSessionId={props.activeSessionId}
            onSelectSession={props.onSelectSession}
          />
        </div>
      </ScrollArea>
    </div>
  )
}

/** Desktop sidebar -- hidden on mobile, visible on md+ */
export function Sidebar(props: SidebarProps) {
  return (
    <aside
      className={cn(
        "hidden w-64 shrink-0 border-r bg-sidebar text-sidebar-foreground md:block",
        props.className
      )}
    >
      <SidebarContent {...props} />
    </aside>
  )
}

/** Mobile sidebar trigger + sheet -- visible on mobile, hidden on md+ */
export function MobileSidebar(props: SidebarProps) {
  const [open, setOpen] = React.useState(false)

  const handleSelect = (id: string) => {
    props.onSelectSession(id)
    setOpen(false)
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden">
          <MenuIcon />
          <span className="sr-only">Open sessions</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-0">
        <SheetHeader className="sr-only">
          <SheetTitle>Sessions</SheetTitle>
        </SheetHeader>
        <SidebarContent {...props} onSelectSession={handleSelect} />
      </SheetContent>
    </Sheet>
  )
}
