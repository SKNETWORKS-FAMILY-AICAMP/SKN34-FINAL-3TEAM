import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ChevronDown, FilePlus2, Inbox } from 'lucide-react'
import { Modal } from '../shared/ClassroomParts.tsx'
export function Panel({ title, action, children, className = '' }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`ad-panel ${className}`}>{title && <div className="ad-panel-heading"><h2>{title}</h2>{action}</div>}{children}</section>
}
export function Badge({ children, active = false, tone }: { children: ReactNode; active?: boolean; tone?: 'success' | 'danger' }) {
  return <span className={`ad-badge${active ? ' is-active' : ''}${tone ? ` is-${tone}` : ''}`}>{children}</span>
}
export function Empty({ children = '조건에 맞는 기록이 없습니다.' }: { children?: ReactNode }) { return <div className="ad-empty"><Inbox size={27} strokeWidth={1.4} aria-hidden="true" /><p>{children}</p></div> }
/** 접어도 입력 중인 폼을 마운트한 채 유지한다. 생성 상태를 나타내는 진행 표시가 아니다. */
export function RequestPanel({ title, children }: { title: string; children: ReactNode }) {
  return <details className="ad-request-panel"><summary><FilePlus2 size={19} aria-hidden="true" /><span>{title}</span><ChevronDown size={18} aria-hidden="true" /></summary><div>{children}</div></details>
}
export function DraftWorkflow({ children }: { children: ReactNode }) {
  return <details className="ad-review-guide"><summary>검토·게시 기준</summary><p>{children}</p></details>
}
export function Inspector({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return <div className="ad-inspector"><Modal title={title} onClose={onClose}>{children}</Modal></div>
}
export function Stat({ label, value, note, href }: { label: string; value: ReactNode; note?: ReactNode; href?: string }) {
  const content = <><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</>
  return href ? <Link className="ad-stat" to={href}>{content}</Link> : <div className="ad-stat">{content}</div>
}
