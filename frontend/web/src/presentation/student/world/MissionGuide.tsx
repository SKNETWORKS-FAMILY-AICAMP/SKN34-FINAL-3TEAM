import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../data/apiClient.ts'
import { isDemo, useMission } from '../../../data/classroom/useClassroom.ts'
import type { Child, InputType, Mission } from '../../../domain/classroom.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { SceneArt } from '../MissionScene.tsx'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { STEPS } from './missionSteps.ts'
import { SpeechBubble } from './SpeechBubble.tsx'
import './mission-guide.css'

/** "이렇게 써요": 입력 방식마다 쓸 칸(답 칸 이름과 같은 뜻, 규칙 기반). 점선 칩은 꼭 쓰지 않아도 되는 칸 */
const PARTS: Record<InputType, { label: string; optional?: boolean }[]> = {
  NARRATIVE: [{ label: '내 생각' }, { label: '이유' }],
  SOLUTION_STEPS: [{ label: '풀이 과정' }, { label: '최종 답' }],
  ESSAY: [{ label: '내 주장' }, { label: '이유 두 가지' }, { label: '다른 의견에 답하기' }],
  CHOICE: [{ label: '알맞은 것 고르기' }],
  ORDERING: [{ label: '순서대로 놓기' }],
  CLASSIFICATION: [{ label: '무리 지어 나누기' }],
}

/** 미션 그림: 미션 장면 그림(정적 우선) → 시연 모음 그림 조각 → 기본 장면 그림 */
function GuideArt({ mission }: { mission: Mission }) {
  const uri = mission.staticSceneUri || mission.sceneUri
  if (uri && /^(https?:\/\/|\/[^/])/.test(uri)) return <img className="mg-art-img" src={uri} alt={mission.question} />
  if (isDemo) {
    // 공책 그림(ActivityPaper)과 같은 조각: 시연 모음 그림의 가로 절반·세로 43%
    const x = mission.scene === 'science' || mission.scene === 'korean' ? '100%' : '0%'
    const y = mission.scene === 'english' || mission.scene === 'korean' ? '77.2%' : '0%'
    return (
      <div
        className="mg-art-img mg-art-atlas"
        role="img"
        aria-label={mission.question}
        style={{ backgroundPosition: `${x} ${y}` }}
      />
    )
  }
  return (
    <div className="mg-art-img mg-art-svg">
      <SceneArt mission={mission} />
    </div>
  )
}

/**
 * 미션 안내 화면(시안 MissionGuide, #589·#648). 학생 틀 안 전체 화면: 왼쪽 큰 그림, 오른쪽 질문·쓰는 법·도우미 말풍선·시작.
 * 무료 학생의 추가 문제(EXTRA)는 시작할 때 403 PREMIUM_REQUIRED가 와서 안내만 보여 준다(결제 유도 문구 없음, #487).
 */
export function MissionGuide({
  id,
  child,
  backLabel,
  onClose,
  onStart,
  pending,
  error,
}: {
  id: string
  child: Child
  /** 돌아가기 버튼 이름(미션 고르기에서 열면 "미션 고르기", 홈에서 열면 "홈") */
  backLabel: string
  onClose: () => void
  onStart: (m: Mission) => Promise<void>
  pending: boolean
  error: unknown
}) {
  const { companion, worn } = useLook()
  const query = useMission(id, child)
  const m = query.data
  const premiumOnly = error instanceof ApiError && error.problem?.code === 'PREMIUM_REQUIRED'
  const [speaking, setSpeaking] = useState(false)
  const title = useRef<HTMLHeadingElement>(null)
  useEffect(() => () => window.speechSynthesis?.cancel(), [])
  // 화면이 바뀌면 제목으로 초점을 옮기고(화면 읽기 프로그램), Esc로 닫는다(예전 안내 창과 같은 조작, #640)
  useEffect(() => {
    if (m) title.current?.focus()
  }, [m])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])
  const read = () => {
    if (!m || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const voice = new SpeechSynthesisUtterance(`${m.title}. ${m.question}`)
    voice.lang = 'ko-KR'
    voice.onend = () => setSpeaking(false)
    setSpeaking(true)
    window.speechSynthesis.speak(voice)
  }
  return (
    <main className="mg-page" aria-labelledby="mg-title">
      <div className="mg-top">
        <button type="button" className="mg-back" onClick={onClose}>
          ← {backLabel}
        </button>
        <ol className="mg-steps" aria-label="미션 단계">
          {STEPS.map((s, i) => (
            <li key={s} aria-current={i === 0 ? 'step' : undefined}>
              {i + 1} {s}
            </li>
          ))}
        </ol>
      </div>
      {query.isPending && <p role="status">미션을 불러오고 있어요.</p>}
      <ErrorNotice error={query.error} retry={() => void query.refetch()} />
      {m && (
        <div className="mg-body">
          <figure className="mg-art">
            <GuideArt mission={m} />
          </figure>
          <section className="mg-side">
            <span className="mg-tag">
              {studentThinkingLabels[m.thinkingType]} · {m.subject} · 초{m.grade}
            </span>
            <h1 id="mg-title" className="mg-title" ref={title} tabIndex={-1}>
              {m.title}
            </h1>
            <p className="mg-question">{m.question}</p>
            <div className="mg-parts">
              <strong>이렇게 써요</strong>
              <ul>
                {PARTS[m.inputType].map((p) => (
                  <li key={p.label} data-optional={p.optional || undefined}>
                    {p.label}
                  </li>
                ))}
              </ul>
            </div>
            <div className="mg-helper">
              <span className="mg-helper-face" aria-hidden="true">
                <Companion kind={companion} size={56} worn={worn} decorative />
              </span>
              <SpeechBubble tail="left" className="mg-bubble"><p>10분이면 충분해요. 막히면 ‘생각 열기’를 눌러 봐!</p></SpeechBubble>
            </div>
            {premiumOnly ? (
              <div className="st-premium-note" role="status">
                <strong>생각 유형별 더 풀어 보기는 프리미엄에서 열려요.</strong>
                <p>이번 주 테마 문제는 그대로 풀 수 있어요. 홈에서 오늘 문제를 풀어 볼까요?</p>
              </div>
            ) : (
              <ErrorNotice error={error} />
            )}
            <div className="mg-actions">
              <button type="button" className="mg-read" onClick={read} aria-pressed={speaking}>
                {speaking ? '읽는 중…' : '질문 읽어 주기'}
              </button>
              {premiumOnly ? (
                <button type="button" className="mg-start" onClick={onClose}>
                  닫기
                </button>
              ) : (
                <button type="button" className="mg-start" aria-label="미션 시작하기" disabled={pending} onClick={() => void onStart(m)}>
                  {pending ? '여는 중…' : '시작하기 →'}
                </button>
              )}
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
