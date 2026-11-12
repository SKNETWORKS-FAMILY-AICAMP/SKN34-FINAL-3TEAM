import { useState } from 'react'
import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { serviceApi } from '../../data/serviceApi.ts'
import { notificationLabels, notificationPath } from '../../domain/service.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

export function NotificationCenter({ role, embedded = false, onNavigate }: { role: string; embedded?: boolean; onNavigate?: () => void }) {
  const cache = useQueryClient()
  const [view, setView] = useState('list'), [unread, setUnread] = useState(false), [page, setPage] = useState(0), [notice, setNotice] = useState('')
  const q = useParentQuery(['notifications', unread, page], signal => serviceApi.notifications(unread, page, signal), role !== 'STUDENT' && view === 'list')
  const settings = useParentQuery(['notification-settings'], serviceApi.settings, role !== 'STUDENT' && view === 'settings')
  const read = useParentMutation(serviceApi.read), all = useParentMutation(serviceApi.readAll), save = useParentMutation(serviceApi.saveSettings)
  const [edited, setEdited] = useState<Record<string, boolean>>({})
  const reload = () => { void cache.invalidateQueries({ queryKey: ['parent', 'notifications'] }) }
  if (role === 'STUDENT') return <p>학생 전용 알림함은 제공하지 않습니다.</p>
  return <div className="notification-center">
    {!embedded && <h1>알림</h1>}
    <nav className="parent-tabs notification-tabs" aria-label="알림 메뉴">
      <button aria-pressed={view === 'list'} onClick={() => setView('list')}>알림 목록</button>
      <button aria-pressed={view === 'settings'} onClick={() => setView('settings')}>수신 설정</button>
    </nav>
    {view === 'list' ? <>
      <div className="ws-actions notification-toolbar"><label className="ws-check"><input type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setPage(0) }} />읽지 않은 알림만</label>
        <div className="notification-bulk-actions"><button onClick={reload}>새로고침</button><button disabled={all.isPending || !!q.error} onClick={() => void all.mutateAsync(undefined).then(reload).catch(() => {})}>모두 읽음</button></div></div>
      <QueryFeedback query={q} /><ErrorNotice error={read.error ?? all.error} />
      {!q.error && q.data && !q.data.items.length && <p>표시할 알림이 없습니다.</p>}
      {!q.error && q.data?.items.map(n => {
        const path = notificationPath(n.link, role, location.origin)
        return <article className="ws-card" key={n.id}><h3>{n.title}</h3><p>{n.readAt ? '읽음' : '읽지 않음'} · {n.createdAt}</p>
          <div className="ws-actions">{!n.readAt && <button disabled={read.isPending} onClick={() => void read.mutateAsync(n.id).then(reload).catch(() => {})}>읽음으로 표시</button>}
            {path ? <Link to={path} onClick={onNavigate}>관련 내용 열기</Link> : <p>관련 화면 주소를 확인할 수 없습니다.</p>}</div></article>
      })}
      <nav className="ws-actions notification-pagination" aria-label="알림 페이지"><button disabled={!page || q.isFetching} onClick={() => setPage(p => p - 1)}>이전</button><span>{page + 1}쪽</span><button disabled={!q.data?.hasNext || q.isFetching} onClick={() => setPage(p => p + 1)}>다음</button></nav>
    </> : <>
      <h3>알림 수신 설정</h3><p>받고 싶은 앱 안 알림을 선택해 주세요.</p><QueryFeedback query={settings} />
      {settings.data && !settings.error && <form className="ws-form" onSubmit={event => {
        event.preventDefault()
        void save.mutateAsync({ items: (settings.data?.items ?? []).map(s => ({ ...s, enabled: edited[s.type] ?? s.enabled })) })
          .then(() => { setEdited({}); setNotice('수신 설정을 저장했습니다.') }).catch(() => {})
      }}>
        {settings.data.items.map(s => <label className="ws-check" key={s.type}><input type="checkbox" checked={edited[s.type] ?? s.enabled} onChange={event => setEdited(value => ({ ...value, [s.type]: event.target.checked }))} />{notificationLabels[s.type]}</label>)}
        <button disabled={save.isPending || !Object.keys(edited).length}>설정 저장</button><ErrorNotice error={save.error} /><p role="status">{notice}</p>
      </form>}
    </>}
  </div>
}
