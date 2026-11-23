import { BookOpen, Download } from 'lucide-react'
import { useState } from 'react'
import { openDownload } from '../../data/memoryBook/api.ts'
import { useChildMemoryBookDownload, useChildMemoryBooks } from '../../data/memoryBook/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import { memoryBookFailure } from '../../domain/memoryBook.ts'
import type { MemoryBook } from '../../domain/memoryBook.ts'
import { weekLabel } from '../../domain/retention.ts'

const STATUS_LABELS: Record<MemoryBook['status'], string> = {
  QUEUED: '만드는 중',
  READY: '받을 수 있음',
  FAILED: '만들지 못함',
  EXPIRED: '보관 기간 지남',
}

/**
 * 학부모 리포트 화면의 추억 그림책 목록 (docs/proposals/memory-book.md, 미도입 시험 구현).
 * 아이가 앨범에서 만든 그림책을 받는다. 아이가 답 보여 주기를 꺼 두면 목록 대신 안내만 보인다(D2).
 */
export function ParentMemoryBooks({ child }: { child: Child }) {
  const books = useChildMemoryBooks(child.id)
  const download = useChildMemoryBookDownload(child.id)
  const [notice, setNotice] = useState<string | null>(null)
  const blocked = memoryBookFailure(books.error, 'PARENT')

  async function save(bookId: string) {
    setNotice(null)
    try {
      openDownload(await download.mutateAsync(bookId))
    } catch (error) {
      setNotice(memoryBookFailure(error, 'PARENT') ?? '그림책을 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
      void books.refetch()
    }
  }

  return (
    <section className="ws-card parent-memory-books" aria-labelledby="parent-memory-books-h">
      <h2 id="parent-memory-books-h"><BookOpen size={20} aria-hidden="true" /> 추억 그림책</h2>
      <p>아이가 추억 앨범에서 만든 그림책(PDF)입니다. 한 주의 그림과 아이의 답을 이어 붙였습니다.</p>
      {books.isPending && <p role="status">불러오는 중입니다.</p>}
      {blocked && <p role="alert">{blocked}</p>}
      {books.error && !blocked && <p role="alert">그림책 목록을 불러오지 못했습니다.</p>}
      {books.data && books.data.items.length === 0 && <p className="muted">아직 만든 그림책이 없습니다.</p>}
      {books.data && books.data.items.length > 0 && (
        <ul>
          {books.data.items.map((book) => (
            <li key={book.bookId}>
              <span>{weekLabel(book.rounds[0].weekStart)} 그림책</span>
              <span className="muted"> · {STATUS_LABELS[book.status]}</span>
              {book.status === 'READY' && (
                <button type="button" disabled={download.isPending} onClick={() => void save(book.bookId)}>
                  <Download size={16} aria-hidden="true" /> 받기
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {notice && <p role="alert">{notice}</p>}
    </section>
  )
}
