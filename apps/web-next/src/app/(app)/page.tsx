"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useSessions, useCreateSession } from "@/hooks/use-sessions"

export default function DashboardPage() {
  const router = useRouter()
  const { data: sessions, isLoading } = useSessions()
  const createSession = useCreateSession()

  useEffect(() => {
    if (isLoading) return
    if (sessions && sessions.length > 0) {
      router.replace(`/sessions/${sessions[0].id}`)
    }
  }, [sessions, isLoading, router])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading sessions...</p>
      </div>
    )
  }

  if (!sessions || sessions.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <h2 className="text-lg font-semibold">No sessions yet</h2>
        <p className="text-sm text-muted-foreground">
          Create your first session to get started.
        </p>
        <button
          onClick={() =>
            createSession.mutateAsync({ provider: "gemini" }).then((s) =>
              router.push(`/sessions/${s.id}`)
            )
          }
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          New Session
        </button>
      </div>
    )
  }

  return null
}
