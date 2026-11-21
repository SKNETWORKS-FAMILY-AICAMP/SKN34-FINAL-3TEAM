import { useEffect, useRef, useState } from 'react'
import { useLearningActions, useStudentHome } from '../../../data/classroom/useClassroom.ts'
import { useWeeklyTheme } from '../../../data/retention/queries.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import type { Attempt, Child } from '../../../domain/classroom.ts'
import { DAY_LABELS } from '../../../domain/retention.ts'
import type { AttemptContext, ThemeDay } from '../../../domain/retention.ts'
import { readThemeMotion } from '../../../domain/themeMotion.ts'
import { attemptStarted } from '../../../domain/themeScene.ts'
import { MotionEffects } from '../../common/MotionEffects.tsx'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { useReducedMotion } from '../../common/useReducedMotion.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import './today-scene.css'

/** 그림 주소로 쓸 수 있는 값만(절대 주소·사이트 안 경로). 나머지는 그림 없음 */
const imageUrl = (uri: string | undefined) => (uri && /^(https?:\/\/|\/[^/])/.test(uri) ? uri : null)

/**
 * 오늘 장면 `/student/theme/scene/{day}`(user-flow 3.2, 사용자 결정 2026-11-19 #807, 설계 캔버스 TodaySceneTalk).
 * 들어오면 그 요일 테마 문제의 시도를 시작하고(대화가 시도 시작·이어하기 응답 `themeScene`에만 있음, 진행 중 시도가 있으면 그 시도),
 * 그날 그림 위에 대화를 한 줄씩 보여 준다. 그림이나 상자를 누르면 다음 줄. 마지막 대사에서 대화창 오른쪽에 '문제 시작하기'가 나타나고
 * (마지막 대사 상자를 눌러도 넘어감), 다시 풀기(THEME_REVIEW)는 이미 본 이야기라 처음부터 단추를 보여 건너뛸 수 있다(사용자 결정 2026-11-22).
 * 살펴보기는 없음. 대화가 없거나(ai 생성 실패·관리자 테마) 이미 답을 쓴 시도면 장면 없이 바로 답변 작성.
 * 시도 종류는 그 요일을 마무리했으면 THEME_REVIEW, 아니면 THEME_DAY(홈·정답 고르기·되돌아보기와 같은 규칙).
 */
export function TodayScene({ child, day, onHome, onProblem }: {
  child: Child
  day: ThemeDay
  onHome: () => void
  /** 답변 작성으로(주소를 바꿔치기해 뒤로 가기가 장면으로 돌아오지 않게) */
  onProblem: (attemptId: string) => void
}) {
  const themeQuery = useWeeklyTheme(child.id)
  const homeQuery = useStudentHome(child)
  const learning = useLearningActions()
  const reduce = useReducedMotion()
  const theme = themeQuery.error ? null : (themeQuery.data ?? null)
  const today = theme?.days.find((d) => d.day === day) ?? null
  const mission = today ? homeQuery.data?.missions.find((m) => m.id === today.missionId) : undefined
  const open = !!today && today.state === 'OPEN'
  const context: AttemptContext = today?.attemptStatus === 'COMPLETED' ? 'THEME_REVIEW' : 'THEME_DAY'
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [step, setStep] = useState(0)
  const [badImage, setBadImage] = useState<string | null>(null)
  const started = useRef(false)
  // 시작할 때 보낸 종류. 시작 뒤 주간 테마가 다시 오면 그 요일이 '푸는 중'으로 바뀌어 context가 THEME_DAY로 보이므로 따로 둔다
  const [startedAs, setStartedAs] = useState<AttemptContext | null>(null)
  const start = () => {
    if (!mission) return
    started.current = true
    const as = context
    learning.start.mutateAsync({ mission, child, context: as }).then((a) => { setStartedAs(as); setAttempt(a) }, () => { started.current = false })
  }
  // 요일·미션을 알면 한 번 시작(같은 미션 진행 중 시도가 있으면 learning이 그 시도를 돌려줌)
  useEffect(() => {
    if (open && mission && !started.current && !attempt) start()
  }, [open, mission, attempt]) // eslint-disable-line react-hooks/exhaustive-deps
  const lines = attempt?.themeScene?.dialogue ?? []
  const skip = !!attempt && (lines.length === 0 || attemptStarted(attempt))
  // 대화 상자가 올라오기 전(제목 연출 2.4초 + 올라오기 0.45초)에는 누르기를 받지 않는다(보지 못한 첫 대사를 넘기지 않게). 움직임 줄이기면 바로
  const showing = !!attempt && !skip
  const [risen, setRisen] = useState(false)
  useEffect(() => {
    if (!showing || reduce) return
    const timer = window.setTimeout(() => setRisen(true), 2850)
    return () => window.clearTimeout(timer)
  }, [showing, reduce])
  const ready = reduce || risen
  // 대화가 없거나 이미 답을 쓴 시도는 장면 없이 바로 문제(부모가 다시 그려도 한 번만 넘김)
  const left = useRef(false)
  useEffect(() => {
    if (!attempt || !skip || left.current) return
    left.current = true
    onProblem(attempt.attemptId)
  }, [attempt, skip, onProblem])

  if (themeQuery.isPending || homeQuery.isPending) return <main className="ts-stage"><QueryStateNotice state="PROCESSING" /></main>
  if (!open || (homeQuery.data && !mission))
    return (
      <main className="st-paper st-sheet ts-closed">
        <ErrorNotice error={themeQuery.error ?? homeQuery.error} retry={() => { void themeQuery.refetch(); void homeQuery.refetch() }} />
        {!themeQuery.error && !homeQuery.error && <p className="st-empty">아직 열리지 않은 문제예요.</p>}
        <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
      </main>
    )
  if (!attempt || skip)
    return (
      <main className="ts-stage" aria-busy={!learning.start.error}>
        {learning.start.error ? (
          <div className="ts-error">
            <ErrorNotice error={learning.start.error} retry={start} />
            <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
          </div>
        ) : (
          <p className="ts-wait" role="status">오늘 장면을 준비하고 있어요.</p>
        )}
      </main>
    )

  const m = attempt.mission
  const raw = imageUrl(reduce ? m.staticSceneUri || m.sceneUri : m.sceneUri || m.staticSceneUri)
  const image = raw && raw !== badImage ? raw : null
  const motion = readThemeMotion(m.sceneMotion)
  const last = lines.length - 1
  const current = lines[Math.min(step, last)]
  // 말꼬리는 그 화자 위치가 있을 때만(ai 움직임 speakers, 그림 너비 %). 가장자리에서 넘치지 않게
  const at = motion?.speakers[current.speaker]
  const tail = at ? Math.max(6, Math.min(94, at.x)) : null
  const title = today?.title ?? m.title
  const next = () => {
    if (!ready) return
    if (step < last) setStep(step + 1)
    else onProblem(attempt.attemptId)
  }
  const label = `${DAY_LABELS[day]}요일`
  // 처음 푸는 문제는 대화를 다 넘긴 뒤에만, 다시 풀기는 처음부터. 대화 상자가 올라오기 전에는 숨김(보지 못한 대사를 건너뛰지 않게)
  // 다시 풀기 여부는 시도 응답이 아니라 시작할 때 보낸 종류로 판단(learning 시도 응답에는 종류 칸이 없음)
  const canStart = ready && (step >= last || startedAs === 'THEME_REVIEW')

  return (
    <main className="ts-stage ts-scene" aria-label="오늘 장면">
      {image && <img className="ts-bg" src={image} alt="" aria-hidden="true" />}
      <div className="ts-top">
        <button type="button" className="ts-chip" onClick={onHome}>← 홈</button>
        <h1 className="ts-chip ts-title"><span>{label}</span>{title}</h1>
      </div>
      <div className="ts-col">
        <div className="ts-frame">
          {image ? (
            <div className={reduce ? 'ts-art' : 'ts-art ts-cam'}>
              <img src={image} alt={`${label} 장면`} onError={() => setBadImage(raw)} />
              {!reduce && motion && motion.effects.length > 0 && <MotionEffects effects={motion.effects} />}
            </div>
          ) : (
            <div className="ts-noimg" role="img" aria-label={raw ? '그림을 불러오지 못함' : '그림 없음'}>
              {raw && <strong>그림을 불러오지 못했어요</strong>}
              {raw && <span>대화와 문제는 그대로 이어서 할 수 있어요.</span>}
            </div>
          )}
          {!reduce && (
            <div className="ts-intro" aria-hidden="true">
              <span>{label} · {studentThinkingLabels[m.thinkingType]}</span>
              <strong>{title}</strong>
            </div>
          )}
          <button type="button" className="ts-advance" onClick={next} aria-label={step < last ? '다음 대사' : '문제로 넘어가기'} />
        </div>
        <div className={reduce ? 'ts-talk' : 'ts-talk ts-rise'}>
          {tail !== null && <span className="ts-tail" aria-hidden="true" style={{ left: `${tail}%` }} />}
          <span className="ts-name">{current.speaker}</span>
          <div className="ts-row">
            <button type="button" className="ts-box" onClick={next} data-ready={ready}>
              <span className="ts-line" aria-live="polite">{current.text}</span>
              <span className="ts-pos">{Math.min(step, last) + 1} / {lines.length}{step < last ? ' · 다음 ▼' : ''}</span>
            </button>
            {canStart && (
              <button type="button" className="ts-start" onClick={() => onProblem(attempt.attemptId)}>
                문제 시작하기<span aria-hidden="true"> →</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
