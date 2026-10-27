import { useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { hasPermission } from '../../domain/admin/operations.ts'
import type { Permission } from '../../domain/admin/operations.ts'
import { displayPeriods } from '../../data/classroom/useClassroom.ts'
import { Workspace } from '../common/Workspace.tsx'
import { validPeriod } from '../../domain/parent.ts'
import { AdminOperations } from './AdminOperations.tsx'
import { MissionManager } from './MissionManager.tsx'
import { ModelManager, ErrorManager } from './ModelManager.tsx'
export function AdminWorkspace() {
  const { session } = useSession(),
    location = useLocation(),
    [params, setParams] = useSearchParams(),
    period = {
      from: params.get('from') ?? displayPeriods.recentPeriod.from,
      to: params.get('to') ?? displayPeriods.recentPeriod.to,
    },
    [from, setFrom] = useState(period.from),
    [to, setTo] = useState(period.to),
    [error, setError] = useState(''),
    page = location.pathname.split('/')[2] ?? 'home',
    can = (p: Permission) => hasPermission(session?.permissions, p)
  const nav = [
    { path: '/admin/home', label: '운영 현황' },
    { path: '/admin/audit', label: '감사 이력' },
    ...(can('SERVICE_OPS')
      ? [
          { path: '/admin/jobs', label: '작업 재처리' },
          { path: '/admin/queues', label: '큐·DLQ' },
          { path: '/admin/models', label: '모델·프롬프트' },
          { path: '/admin/usage', label: 'AI 사용량' },
          { path: '/admin/errors', label: '오류 신고' },
        ]
      : []),
    ...(can('CONTENT') ? [{ path: '/admin/missions', label: '미션 관리' }] : []),
  ]
  const denied =
    (['jobs', 'queues', 'models', 'usage', 'errors'].includes(page) && !can('SERVICE_OPS')) ||
    (page === 'missions' && !can('CONTENT'))
  return (
    <Workspace title="관리자 운영 공간" nav={nav}>
      <h1>관리자 운영 화면</h1>
      <p>승인 권한 · {session?.permissions?.join(' · ') || '없음'}</p>
      <p>
        운영 현황에는 학생 원문을 표시하지 않습니다. 콘텐츠·결제 권한으로 학생 답변을 열람할 수
        없습니다.
      </p>
      <form
        className="ws-toolbar"
        onSubmit={(e) => {
          e.preventDefault()
          if (!validPeriod({ from, to })) {
            setError('집계 기간을 확인해 주세요.')
            return
          }
          setError('')
          const next = new URLSearchParams(params)
          next.set('from', from)
          next.set('to', to)
          setParams(next)
        }}
      >
        <label>
          집계 시작일
          <input
            type="date"
            aria-label="집계 시작일"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          집계 종료일
          <input
            type="date"
            aria-label="집계 종료일"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <button className="cj-secondary">집계 기간 적용</button>
        <span>
          집계 기간 · {period.from} ~ {period.to}
        </span>
      </form>
      {error && <p role="alert">{error}</p>}
      {denied ? (
        <p role="alert">FORBIDDEN · 필요한 관리자 권한이 없습니다.</p>
      ) : !validPeriod(period) ? (
        <p role="alert">조회 기간을 확인해 주세요.</p>
      ) : page === 'missions' ? (
        <MissionManager />
      ) : page === 'models' ? (
        <ModelManager />
      ) : page === 'errors' ? (
        <ErrorManager />
      ) : (
        <AdminOperations page={page} period={period} permissions={session?.permissions ?? []} />
      )}
      {(can('PAYMENT_VIEW') || can('PAYMENT_REFUND')) && (
        <p>결제 조회·환불 권한은 확인했으나 결제 운영 화면은 이번 이슈 범위 밖입니다.</p>
      )}
    </Workspace>
  )
}
