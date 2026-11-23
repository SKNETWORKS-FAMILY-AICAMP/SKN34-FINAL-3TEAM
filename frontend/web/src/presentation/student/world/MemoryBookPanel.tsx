import { BookOpen, Download } from 'lucide-react'
import { useState } from 'react'
import { openDownload } from '../../../data/memoryBook/api.ts'
import { useCreateMemoryBook, useMemoryBookDownload, useMyMemoryBooks } from '../../../data/memoryBook/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { bookOfRound, memoryBookFailure } from '../../../domain/memoryBook.ts'

/**
 * 회차 상세의 추억 그림책 칸 (docs/proposals/memory-book.md, 미도입 시험 구현).
 * 없음·실패·만료 → "그림책 만들기", 만드는 중 → 기다림 안내(목록을 몇 초마다 다시 봄), 완성 → "그림책 받기".
 * 유료·원문 공개 확인은 서버가 하고, 거절되면 이유를 그대로 아이 말로 보여 준다.
 */
export function MemoryBookPanel({ child, themeId, weekStart }: { child: Child; themeId: string; weekStart: string }) {
  const books = useMyMemoryBooks(child.id)
  const create = useCreateMemoryBook(child.id)
  const download = useMemoryBookDownload()
  const [notice, setNotice] = useState<string | null>(null)
  const book = bookOfRound(books.data?.items, themeId, weekStart)
  const listBlocked = memoryBookFailure(books.error)

  async function make() {
    setNotice(null)
    try {
      await create.mutateAsync({ themeId, weekStart })
    } catch (error) {
      setNotice(memoryBookFailure(error) ?? '그림책을 만들지 못했어요. 잠시 뒤 다시 해 주세요.')
    }
  }
  async function save(bookId: string) {
    setNotice(null)
    try {
      openDownload(await download.mutateAsync(bookId))
    } catch (error) {
      setNotice(memoryBookFailure(error) ?? '그림책을 받지 못했어요. 잠시 뒤 다시 해 주세요.')
      void books.refetch()
    }
  }

  return (
    <section className="st-episode-book" aria-labelledby="episode-book-h">
      <h2 id="episode-book-h"><BookOpen aria-hidden="true" /> 추억 그림책</h2>
      <p className="st-meta">이 주의 그림과 내 답을 이어 붙인 그림책(PDF)을 만들어 간직할 수 있어요.</p>
      {books.isPending && <p role="status">그림책을 찾고 있어요.</p>}
      {listBlocked && <p role="alert">{listBlocked}</p>}
      {!books.isPending && !listBlocked && (
        book?.status === 'QUEUED' ? (
          <p role="status">그림책을 만들고 있어요. 조금만 기다려 주세요.</p>
        ) : book?.status === 'READY' ? (
          <button type="button" className="st-pill-link" disabled={download.isPending} onClick={() => void save(book.bookId)}>
            <Download aria-hidden="true" /> 그림책 받기
          </button>
        ) : (
          <>
            {book?.status === 'FAILED' && <p className="st-meta">지난번에는 그림책을 만들지 못했어요.</p>}
            {book?.status === 'EXPIRED' && <p className="st-meta">보관 기간이 지나서 다시 만들어야 해요.</p>}
            <button type="button" className="st-pill-link" disabled={create.isPending} onClick={() => void make()}>
              그림책 만들기
            </button>
          </>
        )
      )}
      {notice && <p role="alert">{notice}</p>}
    </section>
  )
}
