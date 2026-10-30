import type { ReactNode } from 'react'
import { Link } from 'react-router'
export function Panel({ title, action, children, className = '' }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`ad-panel ${className}`}>{title && <div className="ad-panel-heading"><h2>{title}</h2>{action}</div>}{children}</section>
}
export function Badge({ children, active = false }: { children: ReactNode; active?: boolean }) {
  return <span className={`ad-badge${active ? ' is-active' : ''}`}>{children}</span>
}
export function Empty({ children = '조건에 맞는 기록이 없습니다.' }: { children?: ReactNode }) { return <p className="ad-empty">{children}</p> }
export function Stat({ label, value, note, href }: { label: string; value: ReactNode; note?: ReactNode; href?: string }) {
  const content = <><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</>
  return href ? <Link className="ad-stat" to={href}>{content}</Link> : <div className="ad-stat">{content}</div>
}
