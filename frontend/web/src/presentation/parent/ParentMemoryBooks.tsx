import { BookOpen, Download } from 'lucide-react'
import { useState } from 'react'
import { openDownload } from '../../data/memoryBook/api.ts'
import { useCreateMemoryBook, useMemoryBookDownload, useMemoryBookRounds } from '../../data/memoryBook/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import { memoryBookFailure } from '../../domain/memoryBook.ts'
import type { MemoryBookRoundItem } from '../../domain/memoryBook.ts'
import { weekLabel } from '../../domain/retention.ts'

/**
 * 학부모 리포트 화면의 추억 그림책 (docs/proposals/memory-book.md, 미도입 시험 구현).
 * 아이가 받은 기념 액자 회차마다 "그림책 발급" → 만드는 중 → "받기". 발급은 학부모만(2026-11-23 결정).
 * 아이가 답 보여 주기를 꺼 두면 목록 대신 안내만 보인다(D2). 유료·한도 거절은 서버 응답을 안내로 바꿔 보인다.
 */
export function ParentMemoryBooks({ child }: { child: Child }) {
  const rounds = useMemoryBookRounds(child.id)
  const create = useCreateMemoryBook(child.id)
  const download = useMemoryBookDownload(child.id)
  const [notice, setNotice] = useState<string | null>(null)
  const blocked = memoryBookFailure(rounds.error)

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

  return (
    <section className="ws-card parent-memory-books" aria-labelledby="parent-memory-books-h">
      <h2 id="parent-memory-books-h"><BookOpen size={20} aria-hidden="true" /> 추억 그림책</h2>
      <p>아이가 한 주 테마를 모두 마쳐 받은 기념 액자마다, 그 주의 그림과 아이의 답을 엮은 그림책(PDF)을 발급할 수 있습니다.</p>
      {rounds.isPending && <p role="status">불러오는 중입니다.</p>}
      {blocked && <p role="alert">{blocked}</p>}
      {rounds.error && !blocked && <p role="alert">회차 목록을 불러오지 못했습니다.</p>}
      {rounds.data && rounds.data.items.length === 0 && <p className="muted">아직 받은 기념 액자가 없습니다. 한 주 테마 다섯 문제를 모두 마치면 생깁니다.</p>}
      {rounds.data && rounds.data.items.length > 0 && (
        <ul aria-label="그림책을 발급할 수 있는 회차">
          {rounds.data.items.map((round) => {
            const book = round.book
            return (
              <li key={`${round.themeId}@${round.weekStart}`}>
                <span><strong>{round.title || '이름 없는 테마'}</strong> · {weekLabel(round.weekStart)}</span>
                {book?.status === 'QUEUED' ? (
                  <span role="status" className="muted">만드는 중</span>
                ) : book?.status === 'READY' ? (
                  <button type="button" disabled={download.isPending} onClick={() => void save(book.bookId)}>
                    <Download size={16} aria-hidden="true" /> 받기
                  </button>
                ) : (
                  <>
                    {book?.status === 'FAILED' && <span className="muted">지난 발급 실패</span>}
                    {book?.status === 'EXPIRED' && <span className="muted">보관 기간 지남</span>}
                    <button type="button" disabled={create.isPending} onClick={() => void issue(round)}>그림책 발급</button>
                  </>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {notice && <p role="alert">{notice}</p>}
    </section>
  )
}
