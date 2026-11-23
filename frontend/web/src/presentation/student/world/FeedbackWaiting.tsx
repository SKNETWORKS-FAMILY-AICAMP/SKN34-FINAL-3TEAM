import { useEffect, useRef, useState } from 'react'
import type { CompanionId } from '../../../domain/studentLook.ts'
import { companionLabel } from '../../../domain/studentLook.ts'
import { Companion } from './Companion.tsx'
import { SpeechBubble } from './SpeechBubble.tsx'
import { wearAssetUrl } from './roomAssets.ts'
import type { WearSlot } from './roomAssets.ts'
import { resumeWaitStart, waitingStep } from './missionSteps.ts'

const POKE_LINE = '조금만 기다려 줘!'
const POKE_MS = 2000
/**
 * 착용 소품이 돋보기 그림이면 그려 넣는 돋보기를 빼서 두 개가 보이지 않게 한다. 착용 값은 아이템 코드가 아니라
 * 그림 키(`look_item.asset_key` = public/student-assets 안 경로)만 오므로 돋보기 그림 파일 경로로 가린다.
 */
const LENS_ACCESSORY = 'looks/acc-lens.svg'

/**
 * 피드백 대기 표시(#847): 고른 친구(착용 포함) + 돋보기 + 단계 문구. 진행 막대·퍼센트 없음.
 * 시작 시각: startedAt(처음 요청·"피드백 다시 받기"의 요청 시각)이 없으면 마지막 답의 submittedAt(새로고침 이어받기, 0~80초로 자름).
 * 쓰는 쪽은 시작 시각이 바뀌면 key를 바꿔 새로 그린다.
 * 화면 읽기: 이 표시는 피드백 상자(role="status") 안에 들어간다. 그림·말풍선은 숨기고(aria-hidden) 단계 문구만 숨김 글자로 둬서
 * 단계가 바뀔 때만 읽힌다(친구를 눌러 바뀐 말은 읽지 않음).
 */
export function FeedbackWaiting({ companion, worn, startedAt, submittedAt }: {
  companion: CompanionId
  worn?: Partial<Record<WearSlot, string | null>>
  startedAt?: number
  submittedAt?: string
}) {
  const [start] = useState(() => startedAt ?? resumeWaitStart(submittedAt, Date.now()))
  const [now, setNow] = useState(() => Date.now())
  const step = waitingStep((now - start) / 1000)
  useEffect(() => {
    // 1초씩 세지 않고 다음 단계 경계에만 깨워 "지금 − 시작 시각"으로 다시 계산한다.
    // 숨은 탭은 타이머가 늦게 돌아서 돌아왔을 때 바로 다시 계산한다. 화면을 떠나면 둘 다 정리
    const sync = () => setNow(Date.now())
    const timer = step.next === null ? undefined : setTimeout(sync, step.next * 1000 + 30)
    document.addEventListener('visibilitychange', sync)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', sync)
    }
  }, [step.index, step.next])
  // 친구를 누르면 한 번 콩 뛰고 말풍선이 잠깐 바뀐다(움직임 줄이기면 CSS가 뛰기만 끈다)
  const [pokes, setPokes] = useState(0)
  const [poked, setPoked] = useState(false)
  const pokeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(pokeTimer.current), [])
  const poke = () => {
    setPokes((n) => n + 1)
    setPoked(true)
    clearTimeout(pokeTimer.current)
    pokeTimer.current = setTimeout(() => setPoked(false), POKE_MS)
  }
  // 착용 소품은 몸 앞쪽(오른쪽)에 든다. 겹치면 소품을 숨기지 않고 돋보기를 반대쪽으로 옮긴다
  // 돋보기를 입었으면 그려 넣는 돋보기는 빼고, 살피기 단계에서는 입은 돋보기를 쥔 곳 기준으로 기울인다(CSS)
  const side = wearAssetUrl(worn?.ACCESSORY) ? 'left' : 'right'
  const ownLens = worn?.ACCESSORY === LENS_ACCESSORY
  return (
    <div className="sw-wait" data-motion={step.motion} data-step={step.index} data-own-lens={ownLens || undefined}>
      <button type="button" className="sw-wait-friend" aria-label={`${companionLabel(companion)}에게 말 걸기`} onClick={poke}>
        <span className="sw-wait-poke" key={pokes} data-poked={pokes > 0 || undefined} aria-hidden="true">
          <span className="sw-wait-pose">
            <Companion kind={companion} size={120} worn={worn} decorative />
            {/* 공책 넘기기 단계에서는 그려 넣는 돋보기를 내려놓는다(입은 돋보기 소품은 아이템이라 그대로) */}
            {!ownLens && step.motion !== 'notebook' && <Magnifier side={side} />}
            {step.motion === 'notebook' && <Notebook />}
          </span>
        </span>
        <span className="sw-wait-ground" aria-hidden="true" />
      </button>
      <SpeechBubble tail="left" className="sw-wait-bubble" aria-hidden="true">
        <p>{poked ? POKE_LINE : step.line}</p>
      </SpeechBubble>
      <span className="st-visually-hidden">{step.line}</span>
    </div>
  )
}

/**
 * 선 두께 기준: 착용 아이템 그림(가로 60, 소품 배율 1)은 친구 그림 좌표(FRIEND_VIEWBOX 가로 184)에서 그대로 그려진다.
 * 대기 그림은 친구 칸 너비의 비율로 크기를 정하므로(work.css) 착용 아이템과 같은 두께가 되게 그림 단위로 바꾼다.
 */
const FRIEND_UNITS = 184
const itemStroke = (width: number, viewBox: number, boxRatio: number) =>
  Math.round(((width * viewBox) / (FRIEND_UNITS * boxRatio)) * 100) / 100
/** 돋보기 그림 칸 = 친구 칸 너비의 50%(work.css .sw-wait-glass), viewBox 64 */
const LENS_BOX = 0.5
const lens = (w: number) => itemStroke(w, 64, LENS_BOX)

/**
 * 돋보기(#847, 직접 그린 SVG). 몸 앞 오른쪽에서 들고 있는 모양: 쥐는 곳(왼쪽 아래 손잡이 끝)이 몸에 걸치고
 * 렌즈는 오른쪽 위 바깥을 향한다(사용자 의견 2026-11-23 "얼굴 옆에 떠 있지 말고"). 왼쪽에 들 때는 좌우를 뒤집는다.
 * 선 두께는 착용 돋보기 소품(looks/acc-lens.svg: 테 4.5, 손잡이 7·3.5, 반짝임 3)과 같게. 렌즈는 연한 하늘색 + 작은 반사광
 */
export function Magnifier({ side = 'right', className = 'sw-wait-glass' }: { side?: 'left' | 'right'; className?: string }) {
  return (
    <svg className={className} data-side={side} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <g transform={side === 'left' ? 'translate(64 0) scale(-1 1)' : undefined}>
        <line x1="12" y1="52" x2="28" y2="36" stroke="#3A2A20" strokeWidth={lens(7)} strokeLinecap="round" />
        <line x1="12" y1="52" x2="28" y2="36" stroke="#B8551C" strokeWidth={lens(3.5)} strokeLinecap="round" />
        <circle cx="39" cy="25" r="15" fill="#D6F1FC" fillOpacity="0.92" stroke="#3A2A20" strokeWidth={lens(4.5)} />
        <path d="M32 21a8 8 0 0 1 6-5" fill="none" stroke="#FFFFFF" strokeWidth={lens(3)} strokeLinecap="round" />
      </g>
    </svg>
  )
}

/**
 * 펼친 작은 공책(#847 5초 단계, 사용자 의견 2026-11-23). 친구 앞쪽 아래에 두고 오른쪽 책장이 책등을 축으로 넘어간다(CSS).
 * 그림 칸 = 친구 칸 너비의 60/184(work.css .sw-wait-book), viewBox 60이라 선 두께 3이 착용 아이템 선(3)과 같다. 선 색 #3A2A20
 */
const PAGE_LEFT = 'M30 21 Q19 15 7 19 V45 Q19 41 30 47 Z'
const PAGE_RIGHT = 'M30 21 Q41 15 53 19 V45 Q41 41 30 47 Z'
function Notebook() {
  return (
    <svg className="sw-wait-book" viewBox="0 0 60 60" aria-hidden="true" focusable="false">
      <path d="M4 22 V49 Q17 45 30 51 Q43 45 56 49 V22" fill="#A8774F" stroke="#3A2A20" strokeWidth="3" strokeLinejoin="round" />
      <path d={PAGE_LEFT} fill="#FFFDF5" stroke="#3A2A20" strokeWidth="3" strokeLinejoin="round" />
      <path d={PAGE_RIGHT} fill="#FFFDF5" stroke="#3A2A20" strokeWidth="3" strokeLinejoin="round" />
      <g stroke="#3A2A20" strokeOpacity="0.35" strokeWidth="2" strokeLinecap="round">
        <path d="M12 26 Q19 24 25 27 M12 32 Q19 30 25 33 M12 38 Q17 36.5 21 38.5" fill="none" />
        <path d="M35 27 Q41 24 48 26 M35 33 Q41 30 48 32" fill="none" />
      </g>
      <path className="sw-wait-page" d={PAGE_RIGHT} fill="#FFF8E6" stroke="#3A2A20" strokeWidth="3" strokeLinejoin="round" />
    </svg>
  )
}
