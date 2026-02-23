import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

export interface SessionSummary {
  id: string
  resumeJson: string | null
  jdText: string | null
  workflowState: string
  provider: string
  createdAt: string
  updatedAt: string
}

const SESSIONS_KEY = ["sessions"] as const

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export function useSessions() {
  return useQuery({
    queryKey: SESSIONS_KEY,
    queryFn: () => fetchJson<SessionSummary[]>("/api/sessions"),
  })
}

export function useSession(id: string | undefined) {
  return useQuery({
    queryKey: [...SESSIONS_KEY, id],
    queryFn: () => fetchJson<SessionSummary>(`/api/sessions/${id}`),
    enabled: !!id,
  })
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { provider?: string }) =>
      fetchJson<SessionSummary>("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
  })
}

export function useUpdateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Record<string, unknown>) =>
      fetchJson<SessionSummary>(`/api/sessions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: SESSIONS_KEY })
      qc.invalidateQueries({ queryKey: [...SESSIONS_KEY, vars.id] })
    },
  })
}

export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      fetch(`/api/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
  })
}
