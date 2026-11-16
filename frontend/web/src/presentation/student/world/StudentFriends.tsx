import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { Child } from '../../../domain/classroom.ts'
import { companionToFriend, friendById, FRIENDS } from '../../../domain/studentLook.ts'
import type { FriendId } from '../../../domain/studentLook.ts'
import { companionKey } from '../../../domain/retention.ts'
import { Companion } from './Companion.tsx'
import { LookLoadState, LookStatus, UnlockConfirm } from './Customize.tsx'
import { useLookShop } from './lookShop.ts'
import type { LookShop } from './lookShop.ts'

/**
 * 뭉치 친구들(/student/friends, #648 시안 Friends, URL은 user-flow 7장 기준안). 왼쪽 큰 캐릭터 + 오른쪽 12장 카드.
 * 12종 모두 고르고 해금한다(꾸미기 캐릭터 칸과 같은 요청·확인 단계, core 12종 저장 #697 뒤 #698).
 */
export function StudentFriends({ child }: { child: Child }) {
  return <FriendsPage key={child.id} child={child} />
}

const TILTS = ['-3deg', '2deg', '-1.5deg', '2.5deg', '-2deg', '1.5deg']

function FriendsPage({ child }: { child: Child }) {
  const shop = useLookShop(child)
  const [selected, setSelected] = useState<FriendId>(() => companionToFriend(shop.companion))
  const status = (id: FriendId) => friendStatus(shop, id)
  const current = friendById(selected)
  const st = status(selected)
  const ring = st.kind === 'using' ? '함께 다니는 중 · ' : st.kind === 'owned' ? '가지고 있어요 · ' : '새 친구를 만나 볼까? · '
  const c = current.companion
  const action = () => {
    if (st.kind === 'owned') shop.choose({ companion: c })
    else if (st.kind === 'locked' && shop.onSale(companionKey(c))) shop.startUnlock(companionKey(c))
  }
  const label = st.kind === 'using' ? '함께 다니는 중' : st.kind === 'owned' ? '함께 다니기'
    : shop.onSale(companionKey(c)) ? `${shop.price(companionKey(c)).toLocaleString('ko-KR')} 포인트로 만나기` : '지금은 만날 수 없어요'
  const actionable = (st.kind === 'owned' && !shop.choosingBlocked) ||
    (st.kind === 'locked' && shop.onSale(companionKey(c)) && !shop.busy && shop.confirming === null && shop.balance !== undefined)
  return (
    <main className="st-paper st-sheet st-friends-page" aria-busy={shop.busy}>
      <section className="st-friends-left" aria-label="고른 친구">
        <h1 className="st-friends-title"><span>뭉치</span> <span>친구들</span></h1>
        <div className="st-friend-stage" style={{ '--st-friend-tint': current.color } as CSSProperties}>
          <svg className="st-friend-ring" viewBox="0 0 200 200" aria-hidden="true" focusable="false">
            <defs><path id="st-friend-ring-path" d="M100,100 m-86,0 a86,86 0 1,1 172,0 a86,86 0 1,1 -172,0" /></defs>
            <circle cx="100" cy="100" r="98" />
            <text><textPath href="#st-friend-ring-path">{ring.repeat(4)}</textPath></text>
          </svg>
          <span className="st-friend-big"><Companion friend={selected} size={190} decorative worn={shop.worn} /></span>
        </div>
        <div className="st-friend-info">
          <h2>{current.name}</h2>
          <p>{current.desc}</p>
        </div>
        <button type="button" className="st-friend-action" data-kind={st.kind} disabled={!actionable} onClick={action}>{label}</button>
        <UnlockConfirm shop={shop} />
        <LookStatus shop={shop} />
        <p className="st-points-pill" role="status">{shop.balance !== undefined ? `내 포인트 ${shop.balance.toLocaleString('ko-KR')}`
          : shop.points.isPending ? '포인트를 확인하고 있어요.' : '포인트를 확인하지 못했어요.'}</p>
        <LookLoadState shop={shop} />
      </section>
      <section className="st-friends-right" aria-label="친구 목록">
        <ul className="st-friend-cards">
          {FRIENDS.map((f, n) => {
            const s = status(f.id)
            return (
              <li key={f.id}>
                <button type="button" className="st-friend-card" data-kind={s.kind} aria-pressed={selected === f.id}
                  style={{ '--st-friend-tint': f.color, '--st-tilt': TILTS[n % TILTS.length] } as CSSProperties}
                  onClick={() => { setSelected(f.id); if (shop.confirming) shop.cancelUnlock() }}>
                  <Companion friend={f.id} size={96} decorative worn={shop.worn} />
                  <strong>{f.name}</strong>
                  <span className="st-friend-pill">{s.label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </section>
    </main>
  )
}

/** 친구 하나의 상태: 함께 다니는 중·가지고 있어요·포인트(잠김) */
function friendStatus(shop: LookShop, id: FriendId): { kind: 'using' | 'owned' | 'locked'; label: string } {
  const c = friendById(id).companion
  if (c === shop.companion) return { kind: 'using', label: '함께 다니는 중' }
  if (!shop.locked(companionKey(c))) return { kind: 'owned', label: '가지고 있어요' }
  return { kind: 'locked', label: shop.catalog?.some((i) => i.itemKey === companionKey(c)) ? `${shop.price(companionKey(c)).toLocaleString('ko-KR')} 포인트` : '해금 확인 필요' }
}
