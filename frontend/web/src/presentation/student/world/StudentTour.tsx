import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, RefObject } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { useCompleteOnboarding, useOnboarding } from '../../../data/onboarding/queries.ts'
import { companionToFriend, friendById } from '../../../domain/studentLook.ts'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { SpeechBubble } from './SpeechBubble.tsx'
import type { StudentPage } from './StudentWorld.tsx'
import { TOUR_STEPS, josa, pickLine, shouldRecordTour, tourAdvance, tourIndex, tourPath, tourSeen } from './tourSteps.ts'
import type { TourLine } from './tourSteps.ts'
import './tour.css'

const TYPE_MS = 28
/** 표시를 기다리는 시간: 가장 앞 경우가 보이면 바로, 다른 경우만 보이면 조금 더 기다렸다가, 아무것도 없으면 대체 대사 */
const SETTLE_MS = 500
const GIVE_UP_MS = 3000
const reduceMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const tourEl = (target: string) => document.querySelector<HTMLElement>(`[data-tour="${target}"]`)

/** 이 화면에서 대사의 경우를 고른다(화면 데이터가 늦게 그려지면 잠깐 기다림). 고르기 전에는 null */
function usePickedLine(index: number | null, onPage: boolean, name: string): TourLine | null {
  const [picked, setPicked] = useState<{ key: string; value: TourLine } | null>(null)
  const key = `${index}:${name}`
  useEffect(() => {
    if (index === null || !onPage) return
    const step = TOUR_STEPS[index]
    const started = Date.now()
    let firstSeen: number | null = null
    const tick = () => {
      const best = step.variants.findIndex((v) => !!tourEl(v.target))
      const now = Date.now()
      if (best >= 0 && firstSeen === null) firstSeen = now
      if (best === 0 || step.variants.length === 0 || (firstSeen !== null && now - firstSeen >= SETTLE_MS) || now - started >= GIVE_UP_MS) {
        setPicked({ key, value: pickLine(step, (t) => !!tourEl(t), name) })
        return true
      }
      return false
    }
    if (tick()) return
    const timer = window.setInterval(() => { if (tick()) window.clearInterval(timer) }, 100)
    return () => window.clearInterval(timer)
  }, [index, onPage, name, key])
  return picked?.key === key ? picked.value : null
}

/**
 * 강조할 곳의 위치. 대화창에 가리지 않게 필요할 때만 스크롤한다(좁은 화면). 스크롤·창 크기 변화를 따라간다
 */
function useSpotlight(target: string | null, dock: RefObject<HTMLDivElement | null>) {
  const [spot, setSpot] = useState<{ target: string; rect: DOMRect; top: boolean } | null>(null)
  useLayoutEffect(() => {
    if (!target) return
    const el = tourEl(target)
    if (!el) return
    // 대화창이 화면 아래에 있을 때의 윗선(대화창이 위로 올라가 있어도 아래 자리 기준으로 판단)
    const dockTop = innerHeight - (dock.current?.offsetHeight ?? 0) - 14
    // 스크롤해도 강조할 곳이 대화창 자리에 걸리면(한 화면에 맞춘 넓은 화면의 요일 칩 등) 대화창을 위로 올린다
    const measure = () => {
      const rect = el.getBoundingClientRect()
      setSpot({ target, rect, top: rect.bottom + 8 > dockTop })
    }
    const r = el.getBoundingClientRect()
    const gap = 16
    if (r.top < gap || r.bottom > dockTop - gap) {
      const fits = r.height <= dockTop - gap * 2
      el.style.scrollMarginTop = `${gap}px`
      el.style.scrollMarginBottom = `${innerHeight - dockTop + gap}px`
      el.scrollIntoView({ block: fits ? 'end' : 'start', behavior: reduceMotion() ? 'auto' : 'smooth' })
    }
    // 부드러운 스크롤 동안 위치를 따라간다(첫 틀에서 바로 잼)
    let frames = 0
    let raf = requestAnimationFrame(function follow() {
      measure()
      if (++frames < 45) raf = requestAnimationFrame(follow)
    })
    addEventListener('resize', measure)
    addEventListener('scroll', measure, true)
    return () => {
      cancelAnimationFrame(raf)
      removeEventListener('resize', measure)
      removeEventListener('scroll', measure, true)
      el.style.scrollMarginTop = ''
      el.style.scrollMarginBottom = ''
    }
  }, [target, dock])
  return spot && spot.target === target ? spot : null
}

/**
 * 학생 화면 둘러보기(#1038). 주소 `?tour=N`이 있으면 켜진다(홈 첫 진입 자동 시작은 StudentHome, 다시 하기는 도움말).
 * 화면 아래 대화창(캐릭터 이름표·얼굴·말풍선 대사·진행 수·그만 볼래)을 두고, 누르거나 Enter·Space면 다음 대사, Esc는 그만 볼래.
 * 다른 화면의 대사면 그 화면으로 옮긴다(주소 바꿔치기, 뒤로 가기가 둘러보기 중간으로 오지 않게).
 * 뒤 화면(shell)은 inert로 막아 초점을 대화창 안에 가둔다
 */
export function StudentTour({ childId, page, shell }: { childId: string; page: StudentPage | null; shell: RefObject<HTMLDivElement | null> }) {
  const location = useLocation()
  const navigate = useNavigate()
  const index = tourIndex(location.search)
  const active = index !== null
  const { companion, worn } = useLook()
  const friend = friendById(companionToFriend(companion))
  const name = friend.name
  const step = index === null ? null : TOUR_STEPS[index]
  const onPage = !!step && page === step.page
  const picked = usePickedLine(index, onPage, name)
  const line = picked?.line ?? ''
  const [typed, setTyped] = useState<{ line: string; shown: number }>({ line: '', shown: 0 })
  // 움직임 줄이기 설정이면 글자 효과 없이 한 번에
  const instant = reduceMotion()
  const shown = instant ? line.length : typed.line === line ? typed.shown : 0
  const dock = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const spot = useSpotlight(picked?.ring ? picked.target : null, dock)
  const rect = spot?.rect
  const onboarding = useOnboarding('STUDENT', childId)
  const complete = useCompleteOnboarding('STUDENT', childId)

  // 둘러보기가 한 번 켜지면 이 탭에서는 다시 자동 시작하지 않는다(끝낸 직후 기록 요청이 덜 끝나도)
  if (active) tourSeen.add(childId)

  // 이 대사의 화면이 아니면 그 화면으로(새로 고침·주소로 들어온 경우)
  useEffect(() => {
    if (index !== null && !onPage && page) void navigate(tourPath(index), { replace: true })
  }, [index, onPage, page, navigate])

  // 글자가 하나씩 나오기(움직임 줄이기 설정이면 한 번에)
  useEffect(() => {
    if (!line || instant) return
    const timer = window.setInterval(() => {
      setTyped((t) => {
        const at = t.line === line ? t.shown : 0
        if (at >= line.length) {
          window.clearInterval(timer)
          return t
        }
        return { line, shown: at + 1 }
      })
    }, TYPE_MS)
    return () => window.clearInterval(timer)
  }, [line, instant])

  // 뒤 화면을 막고(초점 가두기·화면 읽기에서 숨김) 대화창에 초점
  useEffect(() => {
    const el = shell.current
    if (!active || !el) return
    el.toggleAttribute('inert', true)
    return () => { el.toggleAttribute('inert', false) }
  }, [active, shell])
  useEffect(() => {
    if (active && onPage) box.current?.focus({ preventScroll: true })
  }, [active, onPage, index])

  const close = useCallback(() => {
    if (shouldRecordTour(onboarding.data?.completedAt)) complete.mutate()
    void navigate('/student/home', { replace: true })
  }, [onboarding.data?.completedAt, complete, navigate])

  const next = () => {
    if (index === null || !picked) return
    const r = tourAdvance(index, shown, line.length)
    if (r.kind === 'reveal') setTyped({ line, shown: line.length })
    else if (r.kind === 'finish') close()
    else void navigate(tourPath(r.index), { replace: true })
  }

  if (index === null) return null
  const keys = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      close()
    } else if (e.key === 'Tab') {
      // 대화창 안 두 버튼 사이에서만 돈다
      const items = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="button"], button')]
      const at = items.indexOf(document.activeElement as HTMLElement)
      e.preventDefault()
      items[(at + (e.shiftKey ? -1 : 1) + items.length) % items.length]?.focus()
    }
  }
  const pad = 8
  const ring: CSSProperties | undefined = rect
    ? { top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }
    : undefined
  const done = !!picked && shown >= line.length
  const top = !!spot?.top
  return (
    <div className="st-tour" role="dialog" aria-modal="true" aria-label={`${name}${josa(name, '과', '와')} 화면 둘러보기`} onKeyDown={keys}>
      {ring ? <div className="st-tour-ring" style={ring} data-tour-ring={picked?.target ?? undefined} /> : <div className="st-tour-dim" />}
      <div ref={dock} className={top ? 'st-tour-dock st-tour-dock-top' : 'st-tour-dock'}>
        {/* 말풍선(div)을 품으므로 button 대신 role=button. Enter·Space도 다음으로 */}
        <div ref={box} role="button" tabIndex={0} className="st-tour-box" onClick={next} aria-describedby="st-tour-line"
          onKeyDown={(e) => {
            if (e.key !== 'Enter' && e.key !== ' ') return
            e.preventDefault()
            if (!e.repeat) next()
          }}>
          {/* 캐릭터 얼굴을 크게 대화창 위로 올려 강조하고, 이름표는 얼굴 아래에 */}
          <span className="st-tour-who" style={{ '--st-tour-friend': friend.color } as CSSProperties}>
            <span className="st-tour-face" aria-hidden="true">
              <Companion kind={companion} size={118} worn={worn} decorative />
            </span>
            <span className="st-tour-name">{name}</span>
          </span>
          <SpeechBubble tail="left" className="st-tour-bubble">
            <span className="st-tour-text" aria-hidden="true">{line.slice(0, shown)}</span>
            <span className="st-tour-count" aria-hidden="true">{index + 1} / {TOUR_STEPS.length}</span>
            {done && <span className="st-tour-next" aria-hidden="true">▼</span>}
          </SpeechBubble>
          {/* 화면 읽기에는 글자 효과 없이 대사 전체를 알린다 */}
          <span className="st-visually-hidden" id="st-tour-line" aria-live="polite">
            {line && `${index + 1}/${TOUR_STEPS.length}. ${line}`}
          </span>
          <span className="st-visually-hidden">{done ? '누르면 다음으로 넘어가요.' : '누르면 대사가 바로 다 나와요.'}</span>
        </div>
        <button type="button" className="st-tour-skip" onClick={close}>그만 볼래</button>
      </div>
    </div>
  )
}
