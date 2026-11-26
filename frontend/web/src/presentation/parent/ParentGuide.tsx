import './parent-guide.css'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { needsOnboarding, useCompleteOnboarding, useOnboarding } from '../../data/onboarding/queries.ts'
import { parentMenuSearch } from '../common/parentDisplay.ts'
import { isParentGuideReplay as isReplay, PARENT_GUIDE_DEVICES, parentGuidePlace, parentGuideSteps } from './parentGuide.ts'


/**
 * 학습 현황(/parent/journal)에서만 그린다. 완료 기록이 없다고 확인됐거나 도움말에서 다시 보기로 왔을 때 안내를 띄운다.
 * 다시 보기는 서버 기록을 지우지 않고, 이미 기록이 있으면 다시 기록하지도 않는다.
 */
export function ParentGuideGate() {
  const location = useLocation()
  const replay = isReplay(location.state)
  // 다시 보기로 올 때마다 새로 시작하도록 이동 키로 묶는다.
  return <ParentGuideRun key={replay ? location.key : 'first'} replay={replay} />
}

function ParentGuideRun({ replay }: { replay: boolean }) {
  const query = useOnboarding('PARENT')
  const complete = useCompleteOnboarding('PARENT')
  const navigate = useNavigate(), location = useLocation()
  const [closed, setClosed] = useState(false)
  const pending = needsOnboarding(query)
  if (closed || !(replay || pending)) return null
  return <ParentGuide onFinish={goDevices => {
    setClosed(true)
    if (pending) complete.mutate(undefined, { onError: () => {} })
    const search = parentMenuSearch(location.search)
    if (goDevices) navigate(PARENT_GUIDE_DEVICES + search)
    else if (replay) navigate(location.pathname + location.search, { replace: true, state: null })
  }} />
}

type Place = { where: 'side' | 'bottom' | 'collapsed'; anchor: DOMRect | null; covered: boolean }

const visible = (el: Element) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'
const menuLinks = () => [...document.querySelectorAll<HTMLAnchorElement>('#class-journal .ws-parent .ws-nav a, #class-journal .ws-parent .ws-bottom-nav a')]
const linkPath = (a: HTMLAnchorElement) => new URL(a.href, window.location.origin).pathname

/** 안내 한 단계 = 강조 메뉴 1곳 + 문구 + 다음·건너뛰기. 외부 투어 라이브러리 없이 메뉴 링크에 표시만 붙인다. */
export function ParentGuide({ onFinish }: { onFinish: (goDevices: boolean) => void }) {
  const [index, setIndex] = useState(0)
  const [place, setPlace] = useState<Place>({ where: 'side', anchor: null, covered: false })
  const [size, setSize] = useState({ width: 0, height: 0 })
  const card = useRef<HTMLElement>(null), title = useRef<HTMLHeadingElement>(null)
  const step = parentGuideSteps[index]
  const last = index === parentGuideSteps.length - 1
  const finish = useRef(onFinish)
  useEffect(() => { finish.current = onFinish }, [onFinish])

  // 강조 메뉴 찾기: 보이는 메뉴 링크에 표시를 붙이고, 없으면 접힌 '메뉴' 버튼을 강조한다.
  const locate = useCallback(() => {
    for (const el of document.querySelectorAll('[data-parent-guide-target]')) el.removeAttribute('data-parent-guide-target')
    const shown = menuLinks().filter(a => step.targets.includes(linkPath(a)) && visible(a))
    const marked: Element[] = shown.length ? shown : [...document.querySelectorAll('#class-journal .ws-parent .ws-menu-toggle')].filter(visible)
    for (const el of marked) el.setAttribute('data-parent-guide-target', 'true')
    const first = shown.find(a => a.closest('.ws-bottom-nav')) ?? shown[0]
    const where = !shown.length ? 'collapsed' : first.closest('.ws-bottom-nav') ? 'bottom' : 'side'
    const anchor = (shown[0] ?? marked[0])?.getBoundingClientRect() ?? null
    // 다른 대화창(기록 팝업·메뉴 창 등)이 열려 있으면 안내 창은 잠시 숨긴다. 메뉴 강조는 그대로 둔다.
    const covered = !!document.querySelector('[role="dialog"][aria-modal="true"]')
    setPlace(old => old.where === where && old.covered === covered && same(old.anchor, anchor) ? old : { where, anchor, covered })
  }, [step])

  useLayoutEffect(() => {
    const frame = requestAnimationFrame(locate)
    const root = document.getElementById('class-journal')
    // 메뉴 창을 열고 닫거나 화면이 바뀌어도 강조 위치를 다시 잡는다.
    const observer = new MutationObserver(() => locate())
    if (root) observer.observe(root, { childList: true, subtree: true })
    window.addEventListener('resize', locate)
    window.addEventListener('scroll', locate, true)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('resize', locate)
      window.removeEventListener('scroll', locate, true)
      for (const el of document.querySelectorAll('[data-parent-guide-target]')) el.removeAttribute('data-parent-guide-target')
    }
  }, [locate])

  useLayoutEffect(() => {
    const el = card.current
    if (!el) return
    const update = () => setSize(old => old.width === el.offsetWidth && old.height === el.offsetHeight ? old : { width: el.offsetWidth, height: el.offsetHeight })
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // 단계가 바뀔 때마다 안내 제목으로 초점을 옮긴다.
  useEffect(() => { title.current?.focus() }, [index])

  // Esc로 건너뛰기. 다른 대화창(메뉴 창 등)이 열려 있으면 그 창이 먼저 닫힌다.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || document.querySelector('[role="dialog"][aria-modal="true"]')) return
      event.preventDefault()
      finish.current(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return <section ref={card} className="parent-guide" role="dialog" aria-modal="false" aria-label="학부모 첫 사용 안내"
    aria-describedby="parent-guide-body" data-where={place.where} hidden={place.covered} style={position(place, size)}>
    <p className="parent-guide-count">{index + 1} / {parentGuideSteps.length}</p>
    <h2 ref={title} tabIndex={-1}>{step.title}</h2>
    <p id="parent-guide-body">{step.body}</p>
    <p className="parent-guide-place">{parentGuidePlace(step.targets, place.where)}</p>
    <div className="parent-guide-actions">
      {last ? <>
        <button type="button" className="cj-primary" onClick={() => onFinish(true)}>기기 등록하러 가기</button>
        <button type="button" className="cj-secondary" onClick={() => onFinish(false)}>나중에</button>
      </> : <>
        <button type="button" className="cj-primary" onClick={() => setIndex(index + 1)}>다음</button>
        <button type="button" className="cj-secondary" onClick={() => onFinish(false)}>건너뛰기</button>
      </>}
    </div>
  </section>
}

const same = (a: DOMRect | null, b: DOMRect | null) =>
  a === b || (!!a && !!b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height)

const GAP = 12, EDGE = 12
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, Math.max(min, max)))
/** 강조 메뉴 옆(오른쪽) → 위(하단 바) → 아래(머리글 '메뉴') 순으로 놓고 화면 밖으로 나가지 않게 한다. */
function position({ where, anchor }: Place, { width, height }: { width: number; height: number }) {
  if (!anchor || !width) return { top: EDGE, right: EDGE }
  const vw = window.innerWidth, vh = window.innerHeight
  if (where === 'side' && anchor.right + GAP + width <= vw - EDGE)
    return { left: anchor.right + GAP, top: clamp(anchor.top + anchor.height / 2 - height / 2, EDGE, vh - height - EDGE) }
  if (where === 'bottom') return { left: clamp(anchor.left + anchor.width / 2 - width / 2, EDGE, vw - width - EDGE), top: clamp(anchor.top - GAP - height, EDGE, vh - height - EDGE) }
  return { left: clamp(anchor.right - width, EDGE, vw - width - EDGE), top: clamp(anchor.bottom + GAP, EDGE, vh - height - EDGE) }
}
