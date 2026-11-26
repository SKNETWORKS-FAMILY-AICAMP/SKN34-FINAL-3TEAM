import { useState } from 'react'

/** History is local to an open dialog and never changes browser navigation. */
export function useReportDialogHistory<T>(initial: readonly T[], same: (a: T, b: T) => boolean) {
  const [history, setHistory] = useState(() => ({ entries: [...initial], index: initial.length - 1 }))
  return {
    current: history.entries[history.index],
    canBack: history.index > 0,
    canForward: history.index < history.entries.length - 1,
    back: () => setHistory(value => value.index > 0 ? { ...value, index: value.index - 1 } : value),
    forward: () => setHistory(value => value.index < value.entries.length - 1 ? { ...value, index: value.index + 1 } : value),
    navigate: (next: T) => setHistory(value => same(value.entries[value.index], next) ? value : {
      entries: [...value.entries.slice(0, value.index + 1), next], index: value.index + 1,
    }),
  }
}
