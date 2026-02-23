import { create } from "zustand"
import type { JsonResume } from "@/components/editor/resume-preview"

interface ResumeState {
  resume: JsonResume
  history: JsonResume[]
  historyIndex: number
  setResume: (resume: JsonResume) => void
  updateSection: (path: string, value: unknown) => void
  undo: () => void
  redo: () => void
  canUndo: () => boolean
  canRedo: () => boolean
}

function setByPath(obj: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const clone = structuredClone(obj)
  const parts = path.replace(/^\$\.?/, "").split(".")
  let current: Record<string, unknown> = clone
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i]
    if (!(key in current) || typeof current[key] !== "object") {
      current[key] = {}
    }
    current = current[key] as Record<string, unknown>
  }
  current[parts[parts.length - 1]] = value
  return clone
}

export const useResume = create<ResumeState>((set, get) => ({
  resume: {},
  history: [{}],
  historyIndex: 0,

  setResume: (resume) =>
    set({ resume, history: [resume], historyIndex: 0 }),

  updateSection: (path, value) => {
    const { resume, history, historyIndex } = get()
    const updated = setByPath(resume as Record<string, unknown>, path, value) as JsonResume
    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push(updated)
    set({ resume: updated, history: newHistory, historyIndex: newHistory.length - 1 })
  },

  undo: () => {
    const { history, historyIndex } = get()
    if (historyIndex > 0) {
      set({ resume: history[historyIndex - 1], historyIndex: historyIndex - 1 })
    }
  },

  redo: () => {
    const { history, historyIndex } = get()
    if (historyIndex < history.length - 1) {
      set({ resume: history[historyIndex + 1], historyIndex: historyIndex + 1 })
    }
  },

  canUndo: () => get().historyIndex > 0,
  canRedo: () => get().historyIndex < get().history.length - 1,
}))
