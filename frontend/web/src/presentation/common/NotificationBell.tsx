import { lazy, Suspense, useState } from 'react'
import { Bell } from 'lucide-react'
import { useUnreadNotifications } from '../../data/notifications.ts'
import { useSession } from '../auth/sessionContext.ts'
import { Modal } from '../shared/ClassroomParts.tsx'

const Center = lazy(() => import('../service/NotificationCenter.tsx').then(module => ({ default: module.NotificationCenter })))

export function NotificationBell() {
  const { session } = useSession()
  const [open, setOpen] = useState(false)
  const available = !!session && session.role !== 'STUDENT' && (session.nextAction ?? 'READY') === 'READY'
  const unread = useUnreadNotifications(available)
  if (!available) return null
  const count = unread.error ? 0 : unread.data?.items.length ?? 0
  return <div className="notification-bell">
    <button type="button" className="notification-trigger" aria-label="알림 열기" aria-haspopup="dialog" aria-expanded={open}
      aria-description={count ? `읽지 않은 알림 ${count}${unread.data?.hasNext ? '개 이상' : '개'}` : undefined} onClick={() => setOpen(true)}>
      <Bell size={22} aria-hidden="true" />{count > 0 && <span className="notification-count" aria-hidden="true">{count}{unread.data?.hasNext ? '+' : ''}</span>}
    </button>
    {open && <Modal title="알림" onClose={() => setOpen(false)}><Suspense fallback={<p role="status">알림을 불러오고 있습니다.</p>}><Center role={session.role} embedded onNavigate={() => setOpen(false)} /></Suspense></Modal>}
  </div>
}
