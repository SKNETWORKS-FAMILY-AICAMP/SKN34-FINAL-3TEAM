import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { ApiError } from '../../data/apiClient.ts'
import { isDemo } from '../../data/classroom/useClassroom.ts'
import type { Mission } from '../../domain/classroom.ts'

export function ErrorNotice({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : '요청을 처리하지 못했습니다.'
  const problem = error instanceof ApiError ? error.problem : null
  return (
    <div className="ux-error" role="alert" data-query-state="FAILED">
      <strong>{problem?.title ?? message}</strong>
      {problem?.detail && <p>{problem.detail}</p>}
      {problem?.status === 404 && (
        <p>
          요청한 기능 또는 기록을 찾지 못했습니다. 현재 develop의 공개 기능 API는 아직 구현
          전입니다.
        </p>
      )}
      {error instanceof TypeError && (
        <p>core-service 연결 상태를 확인해 주세요. 예시 데이터로 자동 전환하지 않습니다.</p>
      )}
      {problem?.code && (
        <small>
          {problem.code}
          {problem.traceId ? ` · 확인 번호 ${problem.traceId}` : ''}
        </small>
      )}
      {problem?.missingFields?.length ? (
        <ul aria-label="게시 누락 항목">
          {problem.missingFields.map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
      ) : null}
      {retry && (!problem || (problem.retryable ?? problem.status >= 500)) && (
        <button type="button" className="cj-secondary" onClick={retry}>
          다시 시도
        </button>
      )}
    </div>
  )
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string
  children: ReactNode
  onClose: () => void
}) {
  const panel = useRef<HTMLElement>(null),
    close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  }, [onClose])
  useEffect(() => {
    const old = document.activeElement as HTMLElement | null
    const blocked: { el: HTMLElement; inert: boolean }[] = []
    let branch = panel.current?.parentElement
    while (branch?.parentElement && branch.parentElement !== document.body) {
      for (const sibling of branch.parentElement.children)
        if (sibling !== branch && sibling instanceof HTMLElement) {
          blocked.push({ el: sibling, inert: sibling.inert })
          sibling.inert = true
        }
      branch = branch.parentElement
    }
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true })
    panel.current?.scrollIntoView({ block: 'nearest' })
    const keydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close.current()
      if (e.key !== 'Tab') return
      const elements = [
        ...(panel.current?.querySelectorAll<HTMLElement>('button,input,textarea,select,summary') ??
          []),
      ].filter((el) => !el.hasAttribute('disabled') && el.getClientRects().length)
      const first = elements[0],
        last = elements.at(-1)
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last?.focus()
      }
      if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first?.focus()
      }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      blocked.forEach(({ el, inert }) => {
        el.inert = inert
      })
      document.body.style.overflow = oldOverflow
      if (old?.isConnected) old.focus({ preventScroll: true })
    }
  }, [])
  return (
    <div className="cj-modal-layer">
      <section ref={panel} className="cj-modal" role="dialog" aria-modal="true" aria-label={title}>
        <header className="cj-modal-head">
          <h2>{title}</h2>
          <button type="button" className="cj-close" onClick={onClose} aria-label="창 닫기">
            <X />
          </button>
        </header>
        <div className="cj-modal-body">{children}</div>
      </section>
    </div>
  )
}
export function Brand() {
  return (
    <span className="cj-brand">
      <span className="cj-brand-mark">
        <img src="/brand.jpg" alt="" />
      </span>
      <span className="cj-brand-word">
        <img src="/brand.jpg" alt="사고뭉치" />
      </span>
    </span>
  )
}
export function ActivityPaper({ mission, text = '' }: { mission: Mission; text?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let alive = true
    const image = new Image()
    function draw() {
      if (!alive || !ref.current) return
      const ctx = ref.current.getContext('2d')
      if (!ctx) return
      ctx.clearRect(0, 0, 1000, 540)
      ctx.fillStyle = '#fffef9'
      ctx.fillRect(0, 0, 1000, 540)
      ctx.strokeStyle = '#e7ece5'
      ctx.lineWidth = 1
      for (let y = 100; y < 540; y += 39) {
        ctx.beginPath()
        ctx.moveTo(30, y)
        ctx.lineTo(970, y)
        ctx.stroke()
      }
      ctx.fillStyle = '#738477'
      ctx.font = '400 23px "Noto Sans KR",sans-serif'
      ctx.fillText(`${mission.subject} / ${mission.title}`, 38, 47)
      if (image.complete && image.naturalWidth) {
        const x =
          mission.scene === 'science' || mission.scene === 'korean' ? image.naturalWidth * 0.5 : 0
        const y =
          mission.scene === 'english' || mission.scene === 'korean' ? image.naturalHeight * 0.44 : 0
        ctx.drawImage(
          image,
          x,
          y,
          image.naturalWidth * 0.5,
          image.naturalHeight * 0.43,
          37,
          105,
          448,
          330,
        )
      }
      ctx.font = '400 38px "Gaegu","Malgun Gothic",sans-serif'
      ctx.fillStyle = '#4f7f9d'
      const value = text || '여기에 내 생각을 남겨 보세요.'
      let line = '',
        y = 151
      for (const ch of value) {
        if (ch === '\n' || ctx.measureText(line + ch).width > 426) {
          ctx.fillText(line, 535, y)
          y += 54
          line = ch === '\n' ? '' : ch
          if (y > 475) {
            line = '…'
            break
          }
        } else line += ch
      }
      ctx.fillText(line, 535, Math.min(480, y))
    }
    image.onload = draw
    if (isDemo) image.src = '/demo/atlas.jpg'
    draw()
    void document.fonts.ready.then(draw)
    return () => {
      alive = false
    }
  }, [mission, text])
  return (
    <canvas
      ref={ref}
      className="cj-art"
      width={1000}
      height={540}
      role="img"
      aria-label={`${mission.title} 활동지. 답변 원문은 그림 아래에도 표시됩니다.`}
    />
  )
}
export function MemoCanvas() {
  const ref = useRef<HTMLCanvasElement>(null),
    lines = useRef<{ x: number; y: number }[][]>([]),
    active = useRef(false)
  useEffect(() => {
    const c = ref.current!
    const ctx = c.getContext('2d')!
    const paint = () => {
      const r = c.getBoundingClientRect()
      c.width = Math.round(r.width * 2)
      c.height = Math.round(r.height * 2)
      ctx.strokeStyle = '#4487af'
      ctx.lineWidth = 5
      ctx.lineCap = 'round'
      for (const points of lines.current) {
        ctx.beginPath()
        points.forEach((p, i) =>
          i ? ctx.lineTo(p.x * c.width, p.y * c.height) : ctx.moveTo(p.x * c.width, p.y * c.height),
        )
        ctx.stroke()
      }
    }
    const p = (e: PointerEvent) => {
      const r = c.getBoundingClientRect()
      return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }
    }
    const down = (e: PointerEvent) => {
      c.setPointerCapture(e.pointerId)
      active.current = true
      lines.current.push([p(e)])
      e.preventDefault()
    }
    const move = (e: PointerEvent) => {
      if (!active.current) return
      lines.current.at(-1)!.push(p(e))
      paint()
    }
    const up = () => {
      active.current = false
    }
    c.addEventListener('pointerdown', down)
    c.addEventListener('pointermove', move)
    c.addEventListener('pointerup', up)
    c.addEventListener('pointercancel', up)
    const observer = new ResizeObserver(paint)
    observer.observe(c)
    return () => {
      observer.disconnect()
      c.removeEventListener('pointerdown', down)
      c.removeEventListener('pointermove', move)
      c.removeEventListener('pointerup', up)
      c.removeEventListener('pointercancel', up)
    }
  }, [])
  return (
    <div className="ux-memo-drawing">
      <canvas
        ref={ref}
        aria-label="학생 전용 그림 연습. 제출·판정·학부모 공유에 포함되지 않습니다."
      />
      <button
        type="button"
        className="cj-secondary"
        onClick={() => {
          lines.current.pop()
          const c = ref.current!
          c.dispatchEvent(new Event('pointerup'))
          const ctx = c.getContext('2d')!
          ctx.clearRect(0, 0, c.width, c.height)
          ctx.strokeStyle = '#4487af'
          ctx.lineWidth = 5
          for (const points of lines.current) {
            ctx.beginPath()
            points.forEach((p, i) =>
              i
                ? ctx.lineTo(p.x * c.width, p.y * c.height)
                : ctx.moveTo(p.x * c.width, p.y * c.height),
            )
            ctx.stroke()
          }
        }}
      >
        마지막 획 지우기
      </button>
      <small>그림 연습은 현재 화면에서만 유지됩니다. 글 메모는 초안 저장 대상입니다.</small>
    </div>
  )
}
