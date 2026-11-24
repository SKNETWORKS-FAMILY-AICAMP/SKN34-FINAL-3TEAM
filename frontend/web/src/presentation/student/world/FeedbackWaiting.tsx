import { useEffect, useState } from 'react'
import type { CompanionId } from '../../../domain/studentLook.ts'
import { companionLabel } from '../../../domain/studentLook.ts'
import { Companion } from './Companion.tsx'
import { SpeechBubble } from './SpeechBubble.tsx'
import { wearAssetUrl } from './roomAssets.ts'
import type { WearSlot } from './roomAssets.ts'
import { resumeWaitStart, waitingStep } from './missionSteps.ts'

/** 누를 때마다 차례로 바뀌는 반응(사용자 의견 2026-11-23) */
const POKE_REACTIONS = ['hop', 'squish', 'heart'] as const
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
 * 단계가 바뀔 때만 읽힌다(친구를 눌러도 문구는 바뀌지 않음).
 */
export function FeedbackWaiting({ companion, worn, startedAt, submittedAt, reduce = false }: {
  companion: CompanionId
  worn?: Partial<Record<WearSlot, string | null>>
  startedAt?: number
  submittedAt?: string
  /** 움직임 줄이기(OS 설정 또는 화면 안 체크박스): 멈춘 그림 + 문구만. 말풍선 문구는 그대로 바뀐다 */
  reduce?: boolean
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
  // 친구를 누를 때마다 차례로 다른 반응(콩 → 뽀잉(눌렸다 펴기) → 하트 뿅 → 다시 처음)만 한다. 말풍선은 단계 문구 그대로
  // (사용자 의견 2026-11-23: 눌렀을 때 단계 문구가 2초 사라졌음). 움직임 줄이기면 CSS가 반응을 모두 끈다. 키보드 Enter·Space도 버튼이라 같다
  const [pokes, setPokes] = useState(0)
  const reaction = pokes > 0 ? POKE_REACTIONS[(pokes - 1) % POKE_REACTIONS.length] : undefined
  const poke = () => setPokes((n) => n + 1)
  // 착용 소품은 몸 앞쪽(오른쪽)에 든다. 겹치면 소품을 숨기지 않고 돋보기를 반대쪽으로 옮긴다
  // 돋보기를 입었으면 그려 넣는 돋보기는 빼고, 살피기 단계에서는 입은 돋보기를 쥔 곳 기준으로 기울인다(CSS)
  const side = wearAssetUrl(worn?.ACCESSORY) ? 'left' : 'right'
  const ownLens = worn?.ACCESSORY === LENS_ACCESSORY
  return (
    <div className="sw-wait" data-motion={step.motion} data-step={step.index} data-own-lens={ownLens || undefined} data-reduce={reduce || undefined}>
      {/* 주변: 상자 위쪽을 아주 천천히 지나가는 작은 구름(연하게, 제목 뒤) */}
      <Cloud />
      <button type="button" className="sw-wait-friend" aria-label={`${companionLabel(companion)}에게 말 걸기`} onClick={poke}>
        <span className="sw-wait-poke" key={pokes} data-poked={reaction} aria-hidden="true">
          {reaction === 'heart' && <Heart />}
          {/* pose: 단계 움직임(공책 볼 때 고개 따라가기·갸웃·기지개), breath: 늘 숨쉬기(위아래 2px) */}
          <span className="sw-wait-pose">
            <span className="sw-wait-breath">
              <Companion kind={companion} size={120} worn={worn} decorative />
              {/* 살피기(0초~)는 돋보기를 눈앞에 대고 투명 렌즈로 친구 눈이 그대로 비친다. 공책 단계에서는 내려놓는다(입은 돋보기 소품은 아이템이라 그대로) */}
              {!ownLens && step.motion !== 'notebook' && <Magnifier side={side} clear={step.motion === 'look'} />}
              {step.motion === 'tilt' && <span className="sw-wait-q">?</span>}
            </span>
          </span>
          {/* 공책은 고개를 따라 돌지 않게 pose 밖에 둔다 */}
          {step.motion === 'notebook' && <Notebook />}
        </span>
        <span className="sw-wait-ground" aria-hidden="true" />
        {/* 친구 양옆 발치에 풀 덩이 둘이 땅 선에 붙어 천천히 살랑(발 자리는 비움) */}
        <Tuft className="sw-wait-tuft sw-wait-tuft-1" />
        <Tuft className="sw-wait-tuft sw-wait-tuft-2" />
      </button>
      <SpeechBubble tail="left" className="sw-wait-bubble" aria-hidden="true">
        <p>{step.line}</p>
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
function Magnifier({ side = 'right', className = 'sw-wait-glass', clear = false }: {
  side?: 'left' | 'right'
  className?: string
  /**
   * 눈앞에 대고 볼 때 투명 렌즈: 렌즈 안에 따로 눈을 그리지 않고 뒤의 친구 눈이 원래 크기로 비친다
   * (사용자 의견 2026-11-23: 렌즈 안 2배 큰 눈이 징그러워 보임)
   */
  clear?: boolean
}) {
  return (
    <svg className={className} data-side={side} data-clear={clear || undefined} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <g transform={side === 'left' ? 'translate(64 0) scale(-1 1)' : undefined}>
        <line x1="12" y1="52" x2="28" y2="36" stroke="#3A2A20" strokeWidth={lens(7)} strokeLinecap="round" />
        <line x1="12" y1="52" x2="28" y2="36" stroke="#B8551C" strokeWidth={lens(3.5)} strokeLinecap="round" />
        <circle cx="39" cy="25" r="15" fill="#D6F1FC" fillOpacity={clear ? 0.45 : 0.92} stroke="#3A2A20" strokeWidth={lens(4.5)} />
        <path d="M32 21a8 8 0 0 1 6-5" fill="none" stroke="#FFFFFF" strokeWidth={lens(3)} strokeLinecap="round" />
      </g>
    </svg>
  )
}

/**
 * 누르기 반응 하트(뿅). 그림 칸 = 친구 칸 너비의 22%(work.css .sw-wait-heart), viewBox 24 → 선 두께를 착용 아이템(3)과 같게 환산
 */
function Heart() {
  return (
    <svg className="sw-wait-heart" viewBox="0 0 24 22" aria-hidden="true" focusable="false">
      <path d="M12 20 C5 15 2 11 2 7.5 C2 4.5 4.3 2.5 7 2.5 C9 2.5 10.9 3.7 12 5.6 C13.1 3.7 15 2.5 17 2.5 C19.7 2.5 22 4.5 22 7.5 C22 11 19 15 12 20 Z"
        fill="#FF8FA3" stroke="#3A2A20" strokeWidth={itemStroke(3, 24, 0.22)} strokeLinejoin="round" />
    </svg>
  )
}

/**
 * 풀 덩이 하나: 한 뿌리에서 잎 세 장이 모여 난 모양(사용자 의견 2026-11-24: 따로 선 잎 셋이 진한 갈색 테두리로 가시처럼 보여 어색함).
 * 땅 선에 붙여 두고 테두리는 진한 초록. 그림 칸 = 친구 칸 너비의 14%(work.css .sw-wait-tuft), viewBox 24 → 선 두께를 착용 아이템(3)과 같게 환산
 */
function Tuft({ className }: { className: string }) {
  const w = itemStroke(3, 24, 0.14)
  return (
    <svg className={className} viewBox="0 0 24 16" aria-hidden="true" focusable="false">
      <g fill="#A8DB8A" stroke="#4E8A34" strokeWidth={w} strokeLinejoin="round">
        <path d="M11 16 C7 13 4 10 2.5 5 C6 7 9 10 12 16 Z" />
        <path d="M13 16 C17 13 20 10 21.5 5 C18 7 15 10 12 16 Z" />
        <path d="M10.5 16 C9.5 11 10 5 12 0.8 C14 5 14.5 11 13.5 16 Z" />
      </g>
    </svg>
  )
}

/** 상자 위쪽을 지나가는 작은 구름. 연하게(선 #3A2A20를 옅게), 크기 44×24px */
function Cloud() {
  return (
    <svg className="sw-wait-cloud" viewBox="0 0 44 24" aria-hidden="true" focusable="false">
      <path d="M10 21 C5 21 3 17.5 4.5 14.5 C5.5 12 8 11 10 11.5 C11 6.5 15.5 4 20 5 C23.5 2 30 3 32 8 C36.5 7.5 40 11 39 15 C41 17.5 39.5 21 36 21 Z"
        fill="#FFFFFF" fillOpacity="0.9" stroke="#3A2A20" strokeOpacity="0.3" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

/**
 * 결과 전구(#847, 사용자 의견 2026-11-23): 15초부터 머리 위에 뜨던 "?"가 결과가 오면 전구로 바뀌며 켜진다("찾았다!"와 같이 0.5초).
 * 피드백 화면 "생각 열기" 버튼(연노랑 바탕)과 어울리게 노란 유리 + #3A2A20 선. 움직임이 없을 때의 모습은 켜진 전구(움직임 줄이기도 이 그림)
 */
export function Bulb() {
  return (
    <svg className="sw-found-bulb" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <text className="sw-found-q" x="16" y="22" textAnchor="middle" fontSize="20" fontWeight="700" fill="#3A2A20">?</text>
      <g className="sw-found-light">
        <g className="sw-found-rays" stroke="#F2A65A" strokeWidth="2" strokeLinecap="round">
          <path d="M16 1.5 V4 M4.5 6 L6.5 8 M27.5 6 L25.5 8 M1.5 15 H4 M28 15 H30.5" />
        </g>
        <path d="M16 6 C10.5 6 7.5 10 7.5 14 C7.5 17 9.5 19 11 20.5 C11.8 21.3 12 22.3 12 23.5 H20 C20 22.3 20.2 21.3 21 20.5 C22.5 19 24.5 17 24.5 14 C24.5 10 21.5 6 16 6 Z"
          fill="#FFE45C" stroke="#3A2A20" strokeWidth="2" strokeLinejoin="round" />
        <path d="M12.5 11.5 C13.3 9.8 14.6 9 16 8.8" fill="none" stroke="#FFFFFF" strokeWidth="1.6" strokeLinecap="round" />
        <rect x="12" y="23.5" width="8" height="4.5" rx="1.5" fill="#C9D3DB" stroke="#3A2A20" strokeWidth="2" />
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
