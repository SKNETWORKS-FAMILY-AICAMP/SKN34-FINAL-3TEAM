import { useEffect, useRef, type ReactNode } from 'react'

export const guardianTransferEnabled = import.meta.env?.VITE_GUARDIAN_TRANSFER_ENABLED === 'true'
export function TransferDialog({ title, children }: { title: string; children: ReactNode }) {
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    panel.current?.focus()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [])
  return <div className="transfer-overlay"><section ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="ws-card ws-form transfer-dialog" onKeyDown={event => {
    if (event.key !== 'Tab') return
    const targets = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]') ?? [])
    const first = targets[0], last = targets.at(-1)
    if (!first) { event.preventDefault(); return }
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }}><h2>{title}</h2>{children}</section></div>
}
