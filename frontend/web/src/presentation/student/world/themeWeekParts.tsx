import { useState } from 'react'
import type { ReactNode } from 'react'
import { candidateFacts } from '../../../domain/retention.ts'
import type { WeeklyTheme, WeeklyThemeDay } from '../../../domain/retention.ts'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { SpeechBubble } from './SpeechBubble.tsx'

/** 그날 단서의 근거(#647): 특징 이름과 후보별 값. 특징 표가 없으면 그리지 않는다. */
export function ClueFacts({ day, compact = false }: { day: WeeklyThemeDay; compact?: boolean }) {
  if (!day.clueFeature || !day.clueFacts?.length) return null
  return (
    // 한 문단으로(한 화면에 담기게): "도토리를 먹나요 · 다람쥐 우체부 먹어요 · 고양이 빵집 주인 안 먹어요 …"
    <p className={compact ? 'tw-facts tw-facts-compact' : 'tw-facts'}>
      <b className="tw-facts-name">{day.clueFeature}</b>
      {day.clueFacts.map((f) => (
        <span key={f.candidate} data-out={day.rulesOut?.includes(f.candidate) || undefined}>
          {f.candidate} <b>{f.value}</b>
        </span>
      ))}
    </p>
  )
}

/** 후보 카드에 붙는 "알아낸 것"(#647). */
export function CandidateFacts({ theme, candidate }: { theme: WeeklyTheme; candidate: string }) {
  // 엔딩 뒤에는 특징 표 전체(#715 1번): 단서로 못 얻은 특징은 "엔딩 뒤 공개"로 구분
  const facts = candidateFacts(theme, candidate)
  if (!facts.length) return null
  return (
    <ul className="tw-known" aria-label={`${candidate}에 대해 알아낸 것`}>
      {facts.map((f) => (
        <li key={f.feature} data-revealed={!f.learned || undefined}>
          {f.feature} · <b>{f.value}</b>
          {!f.learned && <small className="tw-known-tag"> 엔딩 뒤 공개</small>}
        </li>
      ))}
    </ul>
  )
}

/** 화면 아래 동행 캐릭터 말풍선(시안 mb-dock). "괜찮아"로 접으면 "도와줘" 작은 버튼으로 다시 부른다. */
export function BuddyBubble({ text, children }: { text: string; children?: ReactNode }) {
  const { companion, worn } = useLook()
  const [hidden, setHidden] = useState(false)
  if (hidden)
    return (
      <button type="button" className="tw-buddy-mini" onClick={() => setHidden(false)} aria-label="동행 캐릭터 부르기">
        <span aria-hidden="true">
          <Companion kind={companion} worn={worn} size={48} decorative />
        </span>
        도와줘
      </button>
    )
  return (
    <div className="tw-buddy">
      <span className="tw-buddy-face" aria-hidden="true">
        <Companion kind={companion} worn={worn} size={84} decorative />
      </span>
      <SpeechBubble tail="left" className="tw-bubble" role="status" aria-live="polite">
        <p>{text}</p>
        <div className="tw-bubble-actions">
          {children}
          <button type="button" className="tw-bubble-btn" onClick={() => setHidden(true)}>
            괜찮아
          </button>
        </div>
      </SpeechBubble>
    </div>
  )
}
