"use client"

import * as React from "react"
import { useRouter, usePathname } from "next/navigation"
import { Sidebar, MobileSidebar, type Session } from "@/components/layout/sidebar"
import { Header, type Provider } from "@/components/layout/header"
import { useSessions, useCreateSession } from "@/hooks/use-sessions"

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { data: sessions = [] } = useSessions()
  const createSession = useCreateSession()
  const [provider, setProvider] = React.useState<Provider>("gemini")

  const activeSessionId = pathname.match(/\/sessions\/(.+)/)?.[1]

  const sidebarSessions: Session[] = sessions.map((s) => ({
    id: s.id,
    title: s.workflowState === "draft" ? "New Session" : `Session ${s.id.slice(0, 8)}`,
    updatedAt: new Date(s.updatedAt),
  }))

  function handleSelectSession(id: string) {
    router.push(`/sessions/${id}`)
  }

  async function handleNewSession() {
    const session = await createSession.mutateAsync({ provider })
    router.push(`/sessions/${session.id}`)
  }

  const sidebarProps = {
    sessions: sidebarSessions,
    activeSessionId,
    onSelectSession: handleSelectSession,
    onNewSession: handleNewSession,
  }

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar {...sidebarProps} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          provider={provider}
          onProviderChange={setProvider}
          onSettingsClick={() => router.push("/settings")}
          leading={<MobileSidebar {...sidebarProps} />}
        />
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}
