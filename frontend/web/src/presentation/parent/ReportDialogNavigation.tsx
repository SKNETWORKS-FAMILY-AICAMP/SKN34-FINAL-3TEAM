import { ArrowLeft, ArrowRight } from 'lucide-react'

export function ReportDialogNavigation({ canBack, canForward, back, forward }: {
  canBack: boolean; canForward: boolean; back: () => void; forward: () => void
}) {
  return <nav className="report-dialog-navigation" aria-label="리포트 탐색">
    <button type="button" aria-label="뒤로 가기" title="뒤로 가기" disabled={!canBack} onClick={back}><ArrowLeft size={19} aria-hidden="true" /></button>
    <button type="button" aria-label="앞으로 가기" title="앞으로 가기" disabled={!canForward} onClick={forward}><ArrowRight size={19} aria-hidden="true" /></button>
  </nav>
}
