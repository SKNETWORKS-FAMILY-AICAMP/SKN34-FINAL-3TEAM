import { BookOpen, Check, Download, Lock } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { openDownload } from '../../data/memoryBook/api.ts'
import { useCreateMemoryBook, useMemoryBookDownload, useMemoryBookRounds, useReadTogether } from '../../data/memoryBook/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import { memoryBookFailedReason, memoryBookFailure, memoryBookLockedNotice, memoryBookShelfLocked, readTogetherLabel } from '../../domain/memoryBook.ts'
import type { MemoryBookRoundItem } from '../../domain/memoryBook.ts'
import { weekLabel } from '../../domain/retention.ts'

/** 넓은 화면 책장 칸 수(parent-insights.css와 같게) */
const SHELF_COLUMNS = 4

/** 무료·프리미엄 비교표 자리(#998, 이용권·결제 화면 섹션 id). 책장 잠금 안내가 여기로 간다(user-flow #997) */
const comparePath = (childId: string) => `/parent/billing?childId=${encodeURIComponent(childId)}#plan-compare`

/** Use the supplied image, or a readable title cover when no illustration exists. */
function Cover({ round, lockedIssue }: { round: MemoryBookRoundItem; lockedIssue: boolean }) {
  const title = round.title || '이름 없는 테마'
  // 책처럼: 왼쪽 책등 띠, 아래쪽에 제목을 얹는다(제목은 화면 읽기에도 그대로 읽힘)
  return <span className={`memory-shelf-cover-wrap${round.imageUrl ? '' : ' memory-shelf-text-cover'}`}>
    {round.imageUrl
      ? <img className="memory-shelf-cover" src={round.imageUrl} alt="" loading="lazy" />
      : <span className="memory-shelf-cover memory-shelf-cover-blank"><BookOpen size={28} aria-hidden="true" /><strong>{title}</strong></span>}
    {round.imageUrl && <strong className="memory-shelf-title">{title}</strong>}
    {/* 무료라 발급이 잠긴 책: 책마다 문장을 반복하지 않고 표지 모서리 표시 하나로(화면 읽기는 "발급은 프리미엄") */}
    {lockedIssue && <span className="memory-shelf-badge"><Lock size={13} aria-hidden="true" /><span className="memory-shelf-sr">발급은 </span>프리미엄</span>}
    {/* 같이 읽은 책(#1026): 왼쪽 위, 자물쇠도 있으면(무료·보관 기간 지남) 한 줄 아래. 보관 기간이 지나도(EXPIRED) 이미 남긴 날짜는 보인다 */}
    {round.book?.readTogetherAt && <span className={`memory-shelf-read${lockedIssue ? ' memory-shelf-read-below' : ''}`}><Check size={13} aria-hidden="true" />{readTogetherLabel(round.book.readTogetherAt)}</span>}
  </span>
}

/**
 * 학부모 리포트 화면의 추억 그림책 책장 (docs/proposals/memory-book.md, 책장 #1000·설계 #997, api-spec 2.5.1).
 * 아이가 받은 기념 액자 회차를 표지(시작 그림·테마 제목·주)로 꽂는다.
 * - 유료(`canCreate`): 회차마다 "그림책 발급" → 만드는 중 → "받기"(지금 흐름 그대로)
 * - 무료(`canCreate === false`): 서버가 보낸 끝난 최근 4주 표지만, 발급 대신 잠금. 숨긴 회차는 `lockedCount` 숫자로만 알리고 비교표로 잇는다
 * - 발급 여부를 모르면(#999 전 서버, `canCreate` 없음) 지금처럼 발급 단추를 두고 서버가 거절한다
 * 아이 화면에는 없다(FN-DSH-01).
 */
export function ParentMemoryBooks({ child }: { child: Child }) {
  const rounds = useMemoryBookRounds(child.id)
  const create = useCreateMemoryBook(child.id)
  const download = useMemoryBookDownload(child.id)
  const readTogether = useReadTogether(child.id)
  const [notice, setNotice] = useState<string | null>(null)
  const blocked = memoryBookFailure(rounds.error)
  const shelf = rounds.data
  const locked = memoryBookShelfLocked(shelf)
  const lockedCount = shelf?.lockedCount ?? 0

  async function issue(round: MemoryBookRoundItem) {
    setNotice(null)
    try {
      await create.mutateAsync({ themeId: round.themeId, weekStart: round.weekStart })
    } catch (error) {
      setNotice(memoryBookFailure(error) ?? '그림책을 발급하지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
    }
  }
  async function save(bookId: string) {
    setNotice(null)
    try {
      openDownload(await download.mutateAsync(bookId))
    } catch (error) {
      setNotice(memoryBookFailure(error) ?? '그림책을 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
      void rounds.refetch()
    }
  }
  /** 같이 읽었어요(#1026, core #1025): 취소 없음·확인 창 없음. 다시 눌러도 서버가 처음 시각을 지킨다 */
  async function markRead(bookId: string) {
    setNotice(null)
    try {
      await readTogether.mutateAsync(bookId)
    } catch (error) {
      setNotice(memoryBookFailure(error) ?? '같이 읽음을 표시하지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
    }
  }

  /** 무료라 이 회차를 발급할 수 없음(이미 만든 그림책을 받거나 만드는 중이면 아님) */
  const lockedIssue = (round: MemoryBookRoundItem) => locked && round.book?.status !== 'READY' && round.book?.status !== 'QUEUED'

  function action(round: MemoryBookRoundItem) {
    const book = round.book
    // 무료라도 이미 만든 그림책(구독 중에 만든 것)은 보관 기간 안 받을 수 있다(api-spec 2.5.1, C2)
    // 같이 읽었어요는 받은 책(READY)에만, 무료 자녀도 같다(core가 유료 판정을 하지 않음, #1025). 표시한 뒤에는 표지 날짜로 대신한다
    if (book?.status === 'READY')
      return <>
        <button type="button" disabled={download.isPending} onClick={() => void save(book.bookId)}><Download size={16} aria-hidden="true" /> 받기</button>
        {!book.readTogetherAt && <button type="button" disabled={readTogether.isPending} onClick={() => void markRead(book.bookId)}>같이 읽었어요</button>}
      </>
    if (book?.status === 'QUEUED') return <span role="status" className="muted">만드는 중</span>
    if (locked) return null
    return <>
      {book?.status === 'FAILED' && <span className="muted">{memoryBookFailedReason(book.failureCode)}</span>}
      {book?.status === 'EXPIRED' && <span className="muted">보관 기간 지남</span>}
      <button type="button" disabled={create.isPending} onClick={() => void issue(round)}>그림책 발급</button>
    </>
  }

  const items = shelf?.items ?? []
  return (
    <section className="ws-card parent-memory-books" aria-labelledby="parent-memory-books-h">
      <h2 id="parent-memory-books-h"><BookOpen size={20} aria-hidden="true" /> 추억 그림책</h2>
      <p>{!locked
        ? '아이가 한 주 테마를 모두 마쳐 받은 기념 액자마다, 그 주의 그림과 아이의 답을 엮은 그림책(PDF)을 발급할 수 있습니다.'
        : items.length === 0
          ? '아이가 한 주 테마를 모두 마쳐 받은 기념 액자가 책장에 꽂혀요. 최근 4주에는 새로 받은 액자가 없어요.'
          : '아이가 한 주 테마를 모두 마쳐 받은 기념 액자가 책장에 꽂혀요. 무료 이용권에서는 최근 4주 표지를 볼 수 있어요.'}</p>
      {rounds.isPending && <p role="status">불러오는 중입니다.</p>}
      {blocked && <p role="alert">{blocked}</p>}
      {/* 실패는 안내와 재시도를 먼저(user-flow 8절) */}
      {rounds.error && !blocked && (
        <p role="alert" className="memory-shelf-retry">
          회차 목록을 불러오지 못했습니다. <button type="button" disabled={rounds.isFetching} onClick={() => void rounds.refetch()}>다시 불러오기</button>
        </p>
      )}
      {shelf && items.length === 0 && lockedCount === 0 && <p className="muted">아직 받은 기념 액자가 없습니다. 한 주 테마 다섯 문제를 모두 마치면 생깁니다.</p>}
      {shelf && (items.length > 0 || lockedCount > 0) && (
        <ul className="memory-shelf" aria-label={locked ? '최근 4주 그림책 표지' : '그림책을 발급할 수 있는 회차'}>
          {items.map((round) => (
            <li className="memory-shelf-book" key={`${round.themeId}@${round.weekStart}`}>
              <Cover round={round} lockedIssue={lockedIssue(round)} />
              <span className="memory-shelf-meta">{weekLabel(round.weekStart)}</span>
              {!lockedIssue(round) && <span className="memory-shelf-action">{action(round)}</span>}
            </li>
          ))}
          {locked && lockedCount > 0 && (
            <li className={`memory-shelf-book memory-shelf-hidden${items.length === 0 ? ' memory-shelf-hidden-only' : ''}`}>
              <span className="memory-shelf-cover memory-shelf-cover-locked" aria-hidden="true"><Lock size={28} /></span>
              <span className="memory-shelf-meta"><strong>잠긴 책 {lockedCount}권</strong> · 지난 회차{items.length === 0 && <span className="memory-shelf-sub">최근 4주보다 오래된 회차라 표지가 잠겨 있어요.</span>}</span>
            </li>
          )}
          {/* 넓은 화면(4칸)에서 첫 줄이 덜 차면 빈 자리를 점선으로 채워 책장처럼 보이게 한다. 꾸밈이라 읽지 않고, 좁은 화면과 표지가 하나도 없을 때(잠긴 책만)는 두지 않는다 */}
          {items.length > 0 && Array.from({ length: Math.max(0, SHELF_COLUMNS - items.length - (locked && lockedCount > 0 ? 1 : 0)) }, (_, i) => (
            <li className="memory-shelf-slot" aria-hidden="true" key={`slot-${i}`}><span className="memory-shelf-cover-slot" /></li>
          ))}
        </ul>
      )}
      {shelf && locked && (
        <p className="memory-shelf-notice" role="note">
          {memoryBookLockedNotice(lockedCount)} <Link to={comparePath(child.id)}>무료와 프리미엄 비교 보기</Link>
        </p>
      )}
      {notice && <p role="alert">{notice}</p>}
    </section>
  )
}
