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
            {!ownLens && <Magnifier side={side} />}
          </span>
        </span>
      </button>
      <SpeechBubble tail="left" className="sw-wait-bubble" aria-hidden="true">
        <p>{poked ? POKE_LINE : step.line}</p>
      </SpeechBubble>
      <span className="st-visually-hidden">{step.line}</span>
    </div>
  )
}

/** 돋보기(#847, 직접 그린 SVG). 쥐는 곳이 아래쪽 끝, 왼쪽에 들 때는 좌우를 뒤집는다 */
export function Magnifier({ side = 'right', className = 'sw-wait-glass' }: { side?: 'left' | 'right'; className?: string }) {
  return (
    <svg className={className} data-side={side} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <g transform={side === 'left' ? 'translate(64 0) scale(-1 1)' : undefined}>
        <line x1="36" y1="36" x2="54" y2="56" stroke="#3A2A20" strokeWidth="11" strokeLinecap="round" />
        <line x1="36" y1="36" x2="54" y2="56" stroke="#B8551C" strokeWidth="6" strokeLinecap="round" />
        <circle cx="25" cy="25" r="17" fill="#DDF3FB" fillOpacity="0.85" stroke="#3A2A20" strokeWidth="5" />
        <path d="M16 21a10 10 0 0 1 9-7" fill="none" stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round" />
      </g>
    </svg>
  )
}
