import type { LearningMission } from '../../domain/learning.ts'
import { comparisonAnswerText } from '../../domain/learning.ts'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type React from 'react'
import { useSession } from '../auth/sessionContext.ts'
import { useBlocker, useNavigate } from 'react-router'
import { ReportProblem } from '../service/ReportProblem.tsx'
import { useAttempt, useAttemptComparison, useLearningActions, isDemo } from '../../data/classroom/useClassroom.ts'
import { DraftConflictError } from '../../data/classroom/errors.ts'
import {
  answerText,
  blankAnswer,
  canAddAnswer,
  canFinish,
  latestFeedback,
  validateAnswer,
  studentThinkingLabels,
} from '../../domain/classroom.ts'
import type { AnswerContent, Attempt, Draft, Reflection } from '../../domain/classroom.ts'
import { ErrorNotice, MemoCanvas, Modal } from '../shared/ClassroomParts.tsx'
import { MissionScene } from './MissionScene.tsx'
import { Companion } from './world/Companion.tsx'
import { MissionDone } from './world/MissionDone.tsx'
import { useRetryPlan } from './world/useRetryPlan.ts'
import { SpeechBubble } from './world/SpeechBubble.tsx'
import { Bulb, FeedbackWaiting } from './world/FeedbackWaiting.tsx'
import { WordHelpPanel } from './WordHelpPanel.tsx'
import { useLook } from './world/lookContext.ts'
import { companionLabel } from '../../domain/studentLook.ts'
import { WAITING_HEADLINE, difficultyLabel, feedbackHeadline, followupLabel } from './world/missionSteps.ts'
import './world/mission-guide.css'
import './world/work.css'
import { ApiError } from '../../data/apiClient.ts'
import { appendMemo, memoTargets } from '../../domain/memoTransfer.ts'
import { hasTypedText, markInput, measureTiming, startRound } from '../../domain/answerTiming.ts'
import type { AnswerTiming, TimingRound } from '../../domain/answerTiming.ts'

/** onCompleted: 돌아보기까지 저장해 학습을 마무리한 직후(없으면 onBack). 엔딩이 되면 이야기의 끝으로 보내는 데 쓴다(#440). */
export function StudentWorkPage({ attemptId, onBack, onHome, onCompleted }: { attemptId: string; onBack: () => void; onHome?: () => void; onCompleted?: () => void }) {
  // 한 화면 고정(st-fit)을 뺌: 낮은 창의 마무리·돌아보기에서 흰 종이가 틀 안에서 스크롤하던 것을 페이지 전체 스크롤로(사용자 결정 2026-11-16)
  return <main className="sw-page" aria-label="미션 풀이"><StudentWorkContent attemptId={attemptId} onBack={onBack} onHome={onHome ?? onBack} onCompleted={onCompleted ?? onBack} /></main>
}
function StudentWorkContent({ attemptId, onBack, onHome, onCompleted }: { attemptId: string; onBack: () => void; onHome: () => void; onCompleted: () => void }) {
  const query = useAttempt(attemptId)
  if (query.isPending)
    return (
      <div className="cj-empty" role="status">
        저장된 활동을 읽고 있어요.
      </div>
    )
  if (!query.data || query.error)
    // 없는 시도 등으로 열지 못하면 메뉴가 숨겨진 막다른 화면이 되므로 돌아가는 버튼을 둔다(#648)
    return (
      <div className="st-work-missing">
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch()
          }}
        />
        <div className="st-work-missing-actions">
          <button type="button" className="st-button st-primary" onClick={onHome}>홈으로</button>
          <button type="button" className="st-button" onClick={onBack}>내 공책으로</button>
        </div>
      </div>
    )
  return <StudentEditor key={attemptId} a={query.data} onBack={onBack} onCompleted={onCompleted} />
}
function StudentEditor({ a, onBack, onCompleted }: { a: Attempt; onBack: () => void; onCompleted: () => void }) {
  const { session } = useSession()
  const navigate = useNavigate()
  const attemptId = a.attemptId,
    actions = useLearningActions(),
    saveDraft = actions.save.mutateAsync
  const [draft, setDraft] = useState<Draft | null>(
    () =>
      a?.draft ?? (a ? { answer: blankAnswer(a.mission.inputType), memo: '', version: '0' } : null),
  )
  const [dirty, setDirty] = useState(false),
    [saveState, setSaveState] = useState<'SAVED' | 'DIRTY' | 'SAVING' | 'FAILED' | 'CONFLICT'>(
      'SAVED',
    )
  const [saveError, setSaveError] = useState<unknown>(null),
    [error, setError] = useState<unknown>(null)
  const [memo, setMemo] = useState(false),
    [hint, setHint] = useState(''),
    [words, setWords] = useState(false),
    [more, setMore] = useState(false)
  const [memoTarget, setMemoTarget] = useState(''),
    [memoError, setMemoError] = useState('')
  const [conflict, setConflict] = useState<Draft | null>(null),
    [backup, setBackup] = useState<Draft | null>(null)
  const [doneNow, setDoneNow] = useState(false),
    // 돌아보기를 막 저장함: 미션 완료 화면(#807, 시안 SC-02-012)을 띄운다
    [difficulty, setDifficulty] = useState<Reflection['difficulty'] | ''>(''),
    [reflection, setReflection] = useState('')
  const editVersion = useRef(0),
    // 같은 키로 다시 보낼 때 처음 잰 시간을 그대로 보낸다(core 멱등 비교가 본문 전체라 값이 바뀌면 422, P28)
    submission = useRef<{ signature: string; key: string; timing: AnswerTiming } | null>(null)
  // 생각·작성 시간 측정(P28): 답변 차례(최초·되묻기마다)의 표시 시각과 첫 입력 시각
  const timing = useRef<TimingRound | null>(null)
  const timingRound = latestFeedback(a)?.followup?.followupId ?? `v${a.answers.length}`
  const draftRef = useRef(draft)
  draftRef.current = draft
  useEffect(() => {
    if (timing.current?.round === timingRound) return
    // 화면을 열 때 답 칸에 복원된 글이 있으면 새로고침 뒤 이어하기라 첫 입력 시각을 모른다(null)
    const resumed = !timing.current && !!draftRef.current && hasTypedText(draftRef.current.answer)
    timing.current = startRound(timingRound, performance.now(), resumed)
  }, [timingRound])
  const resumedFeedback = useRef<string | null>(null)
  const title = useRef<HTMLHeadingElement>(null)
  const result = useRef<HTMLDivElement>(null)
  const [focusAnswerId, setFocusAnswerId] = useState<string | null>(null)
  useEffect(() => { title.current?.focus() }, [])
  const requestFeedback = actions.feedback.mutateAsync
  useEffect(() => {
    const last = a.answers.at(-1)
    if (
      !last ||
      // feedback은 공개 계약상 필수지만, 화면을 연 채로 시도 기록이 바뀌어(목업 시험의 feedback: null 등) 비어 와도
      // 이어받기 효과가 화면 전체를 오류 화면으로 바꾸지 않게 한다(#847 렌더 오류 "reading 'status'")
      !['PENDING', 'RUNNING'].includes(last.feedback?.status ?? '') ||
      resumedFeedback.current === last.answerId ||
      actions.submit.isPending ||
      actions.feedback.isPending
    )
      return
    resumedFeedback.current = last.answerId
    void requestFeedback({ attempt: a, answerId: last.answerId }).catch(setError)
  }, [a, requestFeedback, actions.submit.isPending, actions.feedback.isPending])
  const [notice, setNotice] = useState('')
  const [retryAction, setRetryAction] = useState<(() => Promise<unknown>) | null>(null)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const blocker = useBlocker((dirty || saveState === 'SAVING') && !a.finishedAt)
  const stay = () => {
    setLeaveOpen(false)
    if (blocker.state === 'blocked') blocker.reset()
  }
  const exit = () => {
    if (blocker.state === 'blocked') blocker.proceed()
    else onBack()
  }
  useEffect(
    () => () => {
      window.speechSynthesis?.cancel()
    },
    [],
  )
  useEffect(() => {
    if (!dirty) return
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])
  function back() {
    if (dirty || saveState === 'SAVING') setLeaveOpen(true)
    else onBack()
  }
  const store = useCallback(
    async (snapshot: Draft, version: number) => {
      setSaveState('SAVING')
      setSaveError(null)
      try {
        const saved = await saveDraft({ id: attemptId, draft: snapshot })
        setDraft((current) =>
          current ? { ...current, version: saved.version, savedAt: saved.savedAt } : saved,
        )
        if (editVersion.current === version) {
          setDirty(false)
          setSaveState('SAVED')
          return true
        } else {
          setSaveState('DIRTY')
          return false
        }
      } catch (e) {
        setSaveError(e)
        if (e instanceof DraftConflictError) {
          setConflict(e.latest)
          setLeaveOpen(false)
          setSaveState('CONFLICT')
        } else setSaveState('FAILED')
        return false
      }
    },
    [attemptId, saveDraft],
  )
  useEffect(() => {
    if (
      !dirty ||
      !draft ||
      !a ||
      a.finishedAt ||
      a.status === 'COMPLETED' ||
      ['FAILED', 'CONFLICT', 'SAVING'].includes(saveState) ||
      actions.submit.isPending
    )
      return
    const timer = setTimeout(() => {
      void store(structuredClone(draft), editVersion.current)
    }, 600)
    return () => clearTimeout(timer)
    // 저장 요청의 내부 상태가 아니라 입력과 명시적인 저장 상태로 제어합니다.
  }, [dirty, draft, a, saveState, actions.submit.isPending, store])
  const change = (answer: AnswerContent) => {
    // 직접 입력·'시작 문장'·'메모를 답에 넣기' 모두 첫 입력으로 본다(보호자 받아쓰기 표시·고르기는 글이 아니라 제외)
    if (timing.current && draft) timing.current = markInput(timing.current, draft.answer, answer, performance.now())
    editVersion.current++
    setDraft((current) => (current ? { ...current, answer } : current))
    setDirty(true)
    if (!['FAILED', 'CONFLICT', 'SAVING'].includes(saveState)) setSaveState('DIRTY')
  }
  // 대기 표시 시작 시각(#847): 처음 요청·"피드백 다시 받기"는 요청을 보낸 시각. 없으면 마지막 답의 submittedAt(이어받기)
  const [waitStart, setWaitStart] = useState<{ answerId: string; at: number } | null>(null)
  async function feedback() {
    if (!a?.answers.length) return
    setError(null)
    // "다시 확인하기"(RUNNING)는 같은 처리를 다시 보는 것이라 시작 시각을 그대로 둔다
    const last = a.answers.at(-1)!
    if (last.feedback?.status === 'FAILED') setWaitStart({ answerId: last.answerId, at: Date.now() })
    try {
      await actions.feedback.mutateAsync({ attempt: a, answerId: a.answers.at(-1)!.answerId })
    } catch (e) {
      setRetryAction(() => feedback)
      setError(e)
    }
  }
  // 자동 저장(입력 600ms 뒤) 중에 "다 썼어요"를 누르면 그 클릭을 기억해 두었다가 저장이 끝나면 보낸다.
  // 예전에는 저장 중 버튼이 잠겨 그 사이 누른 클릭이 아무 반응 없이 사라졌다(실서버 E2E 2026-11-16 발견).
  // 저장과 제출이 동시에 나가지 않게 하는 원래 목적은 그대로다
  const [submitQueued, setSubmitQueued] = useState(false)
  useEffect(() => {
    // 저장이 끝나는 순간 한 번만 보낸다(sendQueued는 렌더마다 새로 만들어지는 함수라 의존성에 넣지 않음)
    if (submitQueued && saveState !== 'SAVING' && !actions.save.isPending) void sendQueued()
  }, [submitQueued, saveState, actions.save.isPending]) // eslint-disable-line react-hooks/exhaustive-deps
  async function sendQueued() {
    setSubmitQueued(false)
    if (saveState !== 'CONFLICT') await submit()
  }
  async function submit() {
    if (!draft || !a) return
    const message = validateAnswer(draft.answer, a.mission)
    if (message) {
      setError(
        new ApiError({ status: 422, code: 'ANSWER_INCOMPLETE', title: message, retryable: false }),
      )
      return
    }
    const signature = JSON.stringify({
      answer: draft.answer,
      followupId: latestFeedback(a)?.followup?.followupId,
    })
    if (submission.current?.signature !== signature)
      submission.current = {
        signature,
        key: crypto.randomUUID(),
        timing: measureTiming(timing.current, draft.answer, performance.now()),
      }
    setError(null)
    setNotice('')
    try {
      const saved = await actions.submit.mutateAsync({
        id: a.attemptId,
        answer: draft.answer,
        key: submission.current!.key,
        followupId: latestFeedback(a)?.followup?.followupId,
        timing: submission.current!.timing,
      })
      resumedFeedback.current = saved.answers.at(-1)!.answerId
      setFocusAnswerId(saved.answers.at(-1)!.answerId)
      setDirty(false)
      setSaveState('SAVED')
      setMore(false)
      setDraft((current) =>
        current
          ? {
              ...current,
              version: saved.draft?.version ?? current.version,
              answer: blankAnswer(a.mission.inputType),
            }
          : null,
      )
      // 답변 저장이 끝난 뒤 같은 answerId의 피드백을 별도 요청한다.
      setWaitStart({ answerId: saved.answers.at(-1)!.answerId, at: Date.now() })
      try {
        await actions.feedback.mutateAsync({
          attempt: saved,
          answerId: saved.answers.at(-1)!.answerId,
        })
      } catch (e) {
        setRetryAction(() => feedback)
        setError(e)
      }
    } catch (e) {
      setRetryAction(() => submit)
      setError(e)
    }
  }
  async function finish() {
    if (!a) return
    setError(null)
    try {
      if (dirty && draft && !(await store(structuredClone(draft), editVersion.current))) return
      await actions.finish.mutateAsync(a.attemptId)
    } catch (e) {
      setRetryAction(() => finish)
      setError(e)
    }
  }
  async function complete() {
    if (!a || !difficulty) {
      setNotice('이번 활동이 어땠는지 하나 골라 주세요.')
      return
    }
    try {
      await actions.reflect.mutateAsync({
        id: a.attemptId,
        reflection: { difficulty, text: reflection },
      })
      // 바로 공책으로 가지 않고 미션 완료 화면(엔딩이 됐으면 그 화면이 onCompleted로 이야기의 끝으로 보냄, #807)
      setDoneNow(true)
    } catch (e) {
      setRetryAction(() => complete)
      setError(e)
    }
  }
  const { companion, worn } = useLook()
  const finishRef = useRef<HTMLDivElement>(null)
  const howwasAlert = useRef<HTMLParagraphElement>(null)
  // 끝낸 문제의 다시 풀기: 테마 문제는 토요일·프리미엄 일요일만 오늘 장면으로 THEME_REVIEW, 평일은 안내(#807, 사용자 결정 2026-11-23)
  const retry = useRetryPlan(!!a.themeScene, a.mission.id, session?.child?.id, a.status === 'COMPLETED')
  useEffect(() => { if (notice) howwasAlert.current?.scrollIntoView({ block: 'nearest' }) }, [notice])
  // '더 보기'는 창 대신 그 칸을 펼침: 펼친 동안은 한 화면 맞춤을 풀어 이어 붙임(칸 안 자름), '접기'로 되돌림(사용자 결정 2026-11-23)
  const [expandedBy, setExpandedBy] = useState<string | null>(null)
  const fit = useFitHeight(finishRef, !!a?.finishedAt)
  const fitHeight = expandedBy ? null : fit.height
  // 세 칸은 펼친 동안에도 유지(높이 제한만 풂)
  const fitWide = fit.wide && (fit.height != null || !!expandedBy)
  // 판정 신고는 판정 ID로, 판정 전이면 신고하지 않음 (learning #146)
  const reportJudgmentId = latestFeedback(a)?.judgment?.judgmentId
  // retryable:false면 다시 요청해도 같은 실패라 재요청 버튼 대신 안내 (api-spec 3.2)
  const feedbackFinal = error instanceof ApiError && error.problem.retryable === false
  const f = latestFeedback(a),
    writing = !a.finishedAt && (a.answers.length === 0 || more) && canAddAnswer(a),
    guide = writing && draft ? writingGuide(draft.answer, more, a.mission.choices?.length ?? 0) : null,
    // 테마 문제의 그날 대화 마지막 줄(뭉치가 오늘 문제로 잇는 말, 마지막 줄은 늘 뭉치 — #782·#807). 대화가 없거나 EXTRA면 없음
    hook = a.themeScene?.dialogue.at(-1) ?? null
  useEffect(() => {
    if (!focusAnswerId || writing || !result.current) return
    result.current.focus()
    setFocusAnswerId(null)
  }, [focusAnswerId, writing])
  // 피드백 대기(#847): 마지막 답이 PENDING·RUNNING이거나 피드백 요청 중. 저장 중 눌러 기다리는 것(submitQueued)과
  // 답을 보내는 중(submit)은 아직 답 쓰기 화면이라 버튼 문구만 바꾼다. "다시 확인하기"가 뜬 RUNNING도 대기 표시를 같이 보인다
  const lastAnswer = a.answers.at(-1)
  const waiting = !a.finishedAt && !!f && (f.status === 'PENDING' || f.status === 'RUNNING' || actions.feedback.isPending)
  const waitStartedAt = waitStart && waitStart.answerId === lastAnswer?.answerId ? waitStart.at : undefined
  // 대기 화면 "움직임 줄이기"(#847, WCAG 2.2.2 "5초 넘게 움직이는 것은 멈출 수 있어야", 이슈 지침 "MissionScene 방식"):
  // 기본은 OS 설정을 따르고, 체크하면 멈춘 그림 + 문구만. MissionScene처럼 OS가 줄이기면 체크를 풀 수 없다.
  // 이 화면에 머무는 동안은 다음 답의 대기에도 그대로 둔다
  const [reduceMotion, setReduceMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const changed = () => setReduceMotion(media.matches)
    media.addEventListener('change', changed)
    return () => media.removeEventListener('change', changed)
  }, [])
  // 결과가 오면 상자는 바로 보여 주고 그 위에 "찾았다!"와 켜지는 전구("?"가 전구로)를 0.5초 겹친다(움직임 줄이기면 켜진 전구 그림만)
  const wasWaiting = useRef(false)
  const [found, setFound] = useState(false)
  useEffect(() => {
    const arrived = wasWaiting.current && !waiting && f?.status === 'DONE'
    wasWaiting.current = waiting
    if (!arrived) return
    setFound(true)
    const timer = setTimeout(() => setFound(false), 550)
    return () => {
      clearTimeout(timer)
      setFound(false)
    }
  }, [waiting, f?.status])
  const pending =
    actions.submit.isPending ||
    actions.feedback.isPending ||
    actions.finish.isPending ||
    actions.reflect.isPending ||
    actions.save.isPending
  const targets = draft ? memoTargets(draft.answer) : []
  const selectedMemoTarget = targets.some((t) => t.id === memoTarget)
    ? memoTarget
    : targets[0]?.id ?? ''
  const read = (text: string = a.mission.question) => {
    if (!window.speechSynthesis) {
      setNotice('이 화면에서는 읽어 주기를 쓸 수 없어요.')
      return
    }
    window.speechSynthesis.cancel()
    const voice = new SpeechSynthesisUtterance(text)
    voice.lang = 'ko-KR'
    window.speechSynthesis.speak(voice)
  }
  const saveLine = (
    <div className="ux-save-line sw-save" role="status">
      {!a.finishedAt && draft && (
        <span>
          {
            {
              SAVED: isDemo ? '저장했어요(모의)' : '저장했어요',
              DIRTY: '아직 저장 전이에요',
              SAVING: '저장하고 있어요',
              FAILED: '저장하지 못했어요. 쓴 글은 그대로 있어요.',
              CONFLICT: '다른 곳에서 쓴 글이 있어요. 어느 쪽을 쓸지 골라 주세요.',
            }[saveState]
          }
        </span>
      )}
      {!a.finishedAt && draft?.savedAt && (
        <time dateTime={draft.savedAt}>
          마지막 저장 ·{' '}
          {new Date(draft.savedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
        </time>
      )}
    </div>
  )
  const memoToggle = (
    <button type="button" className="sw-memo-toggle" aria-pressed={memo} disabled={!!a.finishedAt} onClick={() => setMemo(!memo)}>
      생각 메모 · 나만 보기
    </button>
  )
  // 생각 메모(시안 MissionWrite 노란 쪽지): 답 칸을 가리지 않고 아래에 같이 펼친다
  const memoPanel = memo && draft && (
    <section className="sw-memo" aria-label="생각 메모">
      <strong className="sw-memo-title">생각 메모 · 나만 보기</strong>
      <MemoCanvas />
      <label className="cj-field">
        글 메모
        <textarea
          data-testid="private-memo"
          value={draft.memo}
          maxLength={1200}
          disabled={!!a.finishedAt}
          onChange={(e) => {
            editVersion.current++
            setDraft({ ...draft, memo: e.target.value })
            setDirty(true)
            if (!['FAILED', 'CONFLICT', 'SAVING'].includes(saveState))
              setSaveState('DIRTY')
          }}
        />
      </label>
      {targets.length ? (
        <>
          <label className="cj-field">
            옮길 답변 칸
            <select
              aria-label="옮길 답변 칸"
              value={selectedMemoTarget}
              onChange={(e) => {
                setMemoTarget(e.target.value)
                setMemoError('')
              }}
            >
              {targets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          {!writing && (
            <p>답을 쓰는 중에만 옮길 수 있어요.</p>
          )}
          <button
            type="button"
            className="sw-memo-move"
            disabled={!writing || pending || saveState === 'CONFLICT' || !draft.memo.trim()}
            onClick={() => {
              try {
                change(appendMemo(draft.answer, draft.memo, selectedMemoTarget))
                setMemoError('')
                setNotice('메모를 답에 붙였어요.')
                setMemo(false)
              } catch (e) {
                setMemoError(e instanceof Error ? e.message : '메모를 옮기지 못했어요. 다시 해 볼까요?')
              }
            }}
          >
            메모를 답에 옮기기
          </button>
          {memoError && <p role="alert">{memoError}</p>}
        </>
      ) : (
        <p>이 문제는 답 칸에서 직접 골라 주세요.</p>
      )}
    </section>
  )
  const alerts = (
    <>
      {/* 마무리 화면의 안내(난이도 안 고름)는 어땠나요 칸 안에 띄운다 */}
      {notice && !(a.finishedAt && a.status !== 'COMPLETED') && (
        <p className="ux-error" role="alert">
          {notice}
        </p>
      )}
      <ErrorNotice
        error={error}
        retry={
          retryAction
            ? () => {
                void retryAction()
              }
            : undefined
        }
      />
      <ErrorNotice
        error={saveError}
        retry={
          saveState === 'FAILED'
            ? () => {
                setSaveState('DIRTY')
                setDirty(true)
              }
            : undefined
        }
      />
      {saveState === 'CONFLICT' && !conflict && (
        <button
          type="button"
          className="cj-secondary"
          onClick={() => {
            if (saveError instanceof DraftConflictError) setConflict(saveError.latest)
          }}
        >
          다시 비교하기
        </button>
      )}
      {backup && (
        <details className="ux-backup">
          <summary>바꾸기 전 글 보기</summary>
          <p>{answerText(backup.answer)}</p>
        </details>
      )}
    </>
  )
  // 판정 결과 오류 신고(learning #146): 결과를 보여 주는 칸 아래에 둔다
  const report = reportJudgmentId && (
    <div className="sw-report">
      <ReportProblem targetType="JUDGMENT" targetId={reportJudgmentId}/>
    </div>
  )
  // 고르기·순서·분류는 정답 키로 전부 맞음/전부 아님이라 스티커·형광펜이 뜻이 없음(FeedbackFacade.withAnswerKey)
  const thoughtful = !CLOSED_TYPES.includes(a.mission.inputType)
  // 스티커를 누른 요소만 그 근거 구절에 형광펜(평소엔 칠 없음, 사용자 결정 2026-11-20)
  const [lit, setLit] = useState<string | null>(null)
  const onLit = (id: string) => setLit((cur) => (cur === id ? null : id))
  const marks = thoughtful ? foundMarks(a.checklist ?? [], a.answers.map((v) => v.text)) : []
  const answerVersions = (compact = false) => a.answers.map((v, i) => (
    <section className="ux-answer-version sw-version" key={v.answerId} aria-label={v.version === 1 ? '처음 남긴 답' : `덧붙인 답 ${v.version - 1}`}>
      {!(compact && a.answers.length === 1) && <small>{v.version === 1 ? '처음 남긴 답' : `덧붙인 답 ${v.version - 1}`}</small>}
      <p className="cj-quote">{highlight(v.text, (compact ? marks
        : thoughtful ? foundMarks(v.feedback.judgment?.elements ?? [], [v.text]) : []).filter((m) => m.id === lit))}</p>
      {!compact && v.feedback.judgment && (
        <FeedbackEvidence feedback={v.feedback} text={v.text} inputType={a.mission.inputType} lit={lit} onLit={onLit} />
      )}
      {/* 마지막 답의 되묻기는 오른쪽 피드백 상자가 보여 주므로 이전 답의 되묻기만(같은 질문 두 번 방지). 마무리 칸(compact)은 글만(시안 Finish) */}
      {!compact && v.feedback.followup && i < a.answers.length - 1 && (
        <div className="ux-timeline-question sw-asked">
          <small>{followupLabel(v.feedback.followup.type)}</small>
          <p>{v.feedback.followup.question}</p>
        </div>
      )}
    </section>
  ))
  return (
    <section className="st-work sw-work" aria-label="미션 작성기">
      <header className="mg-top sw-top">
        <div className="sw-head">
          <button type="button" className="mg-back" onClick={back}>
            <span aria-hidden="true">← </span>공책으로
          </button>
          <div className="sw-title">
            <h1 ref={title} tabIndex={-1}>{a.mission.title}</h1>
            <span>
              {studentThinkingLabels[a.mission.thinkingType]} · {a.mission.subject} · 초{a.mission.grade}
              {isDemo ? ' · 화면 시연' : ''}
            </span>
          </div>
        </div>
      </header>
      {writing && draft ? (
        // 답 쓰기(시안 MissionWrite → #807 설계 캔버스 MissionWriteTalk): 왼쪽 그림·'오늘의 문제' 상자, 오른쪽 답 칸·도우미 말풍선
        <div className="sw-body sw-body-write">
          <section className="sw-side" aria-label="질문">
            <MissionScene mission={a.mission} />
            <div className="sw-qbox">
              <span className="sw-qtag" aria-hidden="true">{a.themeScene ? '오늘의 문제' : '문제'}</span>
              {/* 테마 문제는 그날 대화 마지막 줄(뭉치가 오늘 문제로 잇는 말)을 함께: 문제 글은 대화에 나온 사건 맥락을 빼고 만들어진다(#807) */}
              {hook && <p className="sw-hook">{hook.speaker} · {hook.text}</p>}
              <h2 className="sw-question">
                <span className="st-visually-hidden">{companionLabel(companion)}의 질문</span>
                {a.mission.question}
              </h2>
              <button type="button" className="sw-read" onClick={() => read()}>
                질문 읽어 주기
              </button>
            </div>
          </section>
          <div className="sw-write">
          <section className="sw-panel" aria-labelledby="sw-panel-title">
            <div className="sw-panel-head">
              <h2 id="sw-panel-title">{more ? '더 말해 보기' : panelTitle[a.mission.inputType]}</h2>
              <div className="sw-toolbar" role="group" aria-label="작성 도구">
                {saveLine}
                {memoToggle}
              </div>
            </div>
            {more && f?.followup && (
              <div className="sw-ask">
                <span className="sw-ask-face" aria-hidden="true">
                  <Companion kind={companion} size={60} worn={worn} decorative />
                </span>
                <div>
                  <span className="sw-chip">{followupLabel(f.followup.type)}</span>
                  <p className="sw-ask-text">{f.followup.question}</p>
                  {report}
                </div>
              </div>
            )}
            <AnswerFields answer={draft.answer} mission={a.mission} onChange={change} guide />
            <div className="sw-submit-row">
              <button
                type="button"
                className="mg-start sw-submit"
                // 초안 자동 저장(actions.save) 중에는 잠그지 않고 누르면 저장 뒤 보낸다(위 submitQueued)
                disabled={(pending && !actions.save.isPending) || saveState === 'CONFLICT' || submitQueued}
                aria-busy={submitQueued}
                onClick={() => {
                  if (saveState === 'SAVING' || actions.save.isPending) setSubmitQueued(true)
                  else void submit()
                }}
              >
                {submitQueued
                  ? '저장하고 보내는 중이에요'
                  : actions.submit.isPending
                    ? '보내는 중이에요'
                    : a.answers.length ? '더해서 보내기' : doneLabel[a.mission.inputType]}
                <span aria-hidden="true"> →</span>
              </button>
            </div>
            {alerts}
            {memoPanel}
          </section>
            <div className="sw-helper">
              <button
                type="button"
                className="sw-helper-face sw-word-trigger"
                aria-expanded={words}
                aria-controls={words ? 'student-word-help' : undefined}
                onClick={() => setWords(open => !open)}
              >
                <Companion kind={companion} size={72} worn={worn} decorative />
                <span>낱말 물어보기</span>
              </button>
              <SpeechBubble tail="left" className="sw-bubble" role="status">
                {hint ? (
                  <>
                    <span className="sw-chip">생각 열기</span>
                    <p>{hint}</p>
                  </>
                ) : guide ? (
                  <p>{guide.line}</p>
                ) : (
                  <p>막히면 ‘생각 열기’를 눌러 봐!</p>
                )}
                {/* 시작 문장과 생각 열기를 한 줄에(말풍선이 길어져 1440×900 한 화면을 넘지 않게) */}
                <div className="sw-bubble-row">
                  {!hint && guide && guide.starters.length > 0 && (
                    <div className="sw-starters" role="group" aria-label="이렇게 시작해 봐">
                      {guide.starters.map((s) => (
                        <button type="button" key={s.text} className="sw-starter" data-optional={s.optional || undefined}
                          onClick={() => change(s.apply(draft.answer))}>
                          {s.text}
                        </button>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    className="sw-hint"
                    onClick={() => {
                      void actions.hint.mutateAsync(a.attemptId).then(setHint).catch(setError)
                    }}
                  >
                    생각 열기
                  </button>
                </div>
              </SpeechBubble>
            </div>
            {words && <WordHelpPanel attemptId={a.attemptId} companion={companion} />}
          </div>
        </div>
      ) : !a.finishedAt ? (
        // 피드백(시안 Feedback): 왼쪽 내가 쓴 답, 오른쪽 피드백 상자와 되묻기
        <div className="sw-body sw-body-feedback">
          <section className="sw-answers" aria-label="내가 쓴 답">
            <p className="sw-qline"><b>오늘의 문제</b>{a.mission.question}</p>
            <div className="sw-toolbar" role="group" aria-label="작성 도구">
              {(memo || saveState !== 'SAVED') && saveLine}
              {memoToggle}
            </div>
            {answerVersions()}
            {memoPanel}
          </section>
          <section className="sw-feedback-panel" aria-label="피드백">
            {/* 상자와 움직임 줄이기 체크박스를 묶는 칸: 결과 때는 없는 것처럼(display: contents), 대기 중에는 그림·말풍선 너비만큼 줄어
                체크박스가 그 오른쪽 아래에 붙는다(#847). 늘 같은 칸이라 상자(읽기 영역)가 다시 그려지지 않는다 */}
            <div className="sw-feedback-group" data-waiting={waiting || undefined}>
            {f && (
              // 화면 읽기 영역은 이 상자 하나: 대기 표시도 안에 넣어 결과가 오면 같은 영역의 내용이 바뀌며 읽힌다(#847)
              <div ref={result} tabIndex={-1} className="ux-feedback sw-feedback" role="status" data-waiting={waiting || undefined}>
                {found && (
                  <span className="sw-found" aria-hidden="true" data-reduce={reduceMotion || undefined}>
                    <Bulb />
                    찾았다!
                  </span>
                )}
                <div className="sw-feedback-head">
                  {/* 대기 중에는 대기 제목("피드백 다시 받기"를 누른 직후 아직 FAILED여도 실패 제목 대신) */}
                  <h2>{waiting ? WAITING_HEADLINE : feedbackHeadline(f)}</h2>
                  {!waiting && f.judgment?.trial && (
                    <small className="sw-trial">AI 채점(시범){isDemo ? ' · 실제 모델 호출 없음' : ''}</small>
                  )}
                </div>
                {waiting && (
                  <FeedbackWaiting
                    key={`${lastAnswer?.answerId}:${waitStartedAt ?? 'resume'}`}
                    companion={companion}
                    worn={worn}
                    startedAt={waitStartedAt}
                    submittedAt={lastAnswer?.submittedAt}
                    reduce={reduceMotion}
                  />
                )}
                {f.judgment?.m2Notices?.map((notice) => (
                  <p key={notice}>{notice}</p>
                ))}
                {f.judgment?.result === 'HELD' && (
                  <p>질문을 다시 읽고 생각을 조금 더 써 볼까요?</p>
                )}
                {f.followup && (
                  <div className="sw-ask">
                    <span className="sw-ask-face" aria-hidden="true">
                      <Companion kind={companion} size={60} worn={worn} decorative />
                    </span>
                    <div>
                      <span className="sw-chip">{followupLabel(f.followup.type)}</span>
                      <p className="sw-ask-text">{f.followup.question}</p>
                      <small className="sw-source">
                        {f.followup.source === 'BANK'
                          ? '질문 은행'
                          : f.followup.source === 'LLM_RETRY'
                            ? '재생성된 질문'
                            : 'AI 질문'}
                        {isDemo ? ' · 시연 예시' : ''}
                      </small>
                    </div>
                  </div>
                )}
              </div>
            )}
            {/* 대기 화면 움직임 줄이기(화면설계서 SC-02-010 미션 장면처럼 그림 아래 오른쪽 작게). 읽기 영역(상자) 밖에 둬서
                대기 표시가 들어올 때 체크박스 이름까지 함께 읽히지 않게 한다 */}
            {waiting && (
              <label className="sw-wait-motion">
                <input
                  type="checkbox"
                  checked={reduceMotion}
                  onChange={(e) => setReduceMotion(e.target.checked || window.matchMedia('(prefers-reduced-motion: reduce)').matches)}
                />
                움직임 줄이기
              </label>
            )}
            </div>
            <div className="sw-actions">
              {f?.status === 'FAILED' && !waiting && feedbackFinal && (
                <p role="status">지금은 피드백을 받을 수 없어요. 답은 저장했어요.</p>
              )}
              {f?.status === 'FAILED' && !waiting && !feedbackFinal && (
                <button
                  type="button"
                  className="mg-start sw-go"
                  disabled={pending}
                  onClick={() => {
                    void feedback()
                  }}
                >
                  피드백 다시 받기
                </button>
              )}
              {f?.status === 'RUNNING' && !pending && (
                <button
                  type="button"
                  className="mg-read"
                  onClick={() => {
                    void feedback()
                  }}
                >
                  다시 확인하기
                </button>
              )}
              {canFinish(a) && (
                <button
                  type="button"
                  className="mg-read"
                  disabled={pending}
                  onClick={() => {
                    void finish()
                  }}
                >
                  {a.answers.length < 3 ? '마무리 보기' : '마무리하기'}
                </button>
              )}
              {canAddAnswer(a) && a.answers.length > 0 && (
                <button type="button" className="mg-start sw-go" onClick={() => setMore(true)}>
                  질문에 답하기
                </button>
              )}
            </div>
            {report}
            {alerts}
          </section>
        </div>
      ) : (
        // 마무리(D안, 사용자 결정 2026-11-23): 오늘의 문제 → 내 답 | 예시 답(정답)·생각 스티커 → 어땠나요(난이도 필수) → '미션 완료하기'.
        // 예전의 자기 확인(FN-LRN-13)·이전 답 비교 창·돌아보기 창은 빼고, 이전 답은 '저번엔' 한 줄과 스티커 '새로!'로 보여 준다
        <div className="sw-finish" ref={finishRef} data-fit={fitHeight ? '' : undefined} data-wide={fitWide ? '' : undefined} style={fitHeight ? { height: fitHeight } : undefined}>
          <p className="sw-qline"><b>오늘의 문제</b>{a.mission.question}</p>
          <h2 className="st-visually-hidden">마무리 · {a.revealKind === 'ANSWER' ? '정답과 비교해 보세요' : '예시 답과 비교해 보세요'}</h2>
          <div className="sw-reveal">
            <ClampCard className="sw-card" label="내 답" expanded={expandedBy === '내 답'} onMore={() => setExpandedBy('내 답')} onLess={() => { setExpandedBy(null); window.scrollTo({ top: 0 }) }} head={<strong>내 답</strong>} foot={report} after={<PrevAnswer attempt={a} />}>
              {answerVersions(true)}
              {f?.judgment?.m2Notices?.map((notice) => (
                <p key={notice}>{notice}</p>
              ))}
            </ClampCard>
            <ClampCard className="sw-card sw-card-reveal" label={a.revealKind === 'ANSWER' ? '정답' : '이렇게 쓸 수도 있어요'}
              expanded={expandedBy === 'reveal'} onMore={() => setExpandedBy('reveal')} onLess={() => { setExpandedBy(null); window.scrollTo({ top: 0 }) }}
              head={<strong>{a.revealKind === 'ANSWER' ? '정답' : '이렇게 쓸 수도 있어요'}</strong>}
              after={thoughtful && !fitWide && <ThoughtStickers attempt={a} lit={lit} onLit={onLit} />}
              foot={a.reveal && <button type="button" className="sw-read sw-read-reveal" onClick={() => read(a.reveal)}>읽어 주기</button>}>
              {/* 정답형(고르기·순서·분류·풀이)은 게시 때 예시 답이 필수가 아니라 비어 있을 수 있다(learning Mission 게시 검사) */}
              {a.reveal ? <p className="cj-quote">{a.reveal}</p>
                : <p className="sw-reveal-none">{a.revealKind === 'ANSWER' ? '이 문제는 정답 글이 따로 없어요.' : '이 문제는 예시 답이 따로 없어요.'}</p>}
            </ClampCard>
          </div>
          {/* 세 칸 배치에서는 스티커를 두 카드 아래 한 줄 띠로(예시 답 칸이 좁아 스티커가 예시 답을 밀어내지 않게) */}
          {thoughtful && fitWide && <div className="sw-wide-stickers"><ThoughtStickers attempt={a} lit={lit} onLit={onLit} /></div>}

          {a.status === 'COMPLETED' && (
            <section className="sw-ideas sw-howwas sw-howwas-done" aria-label="돌아보기 완료">
              <p>
                <strong>돌아보기 완료 · {a.reflection ? difficultyLabel(a.reflection.difficulty) : ''}</strong>
                {a.reflection?.text && <span>{a.reflection.text}</span>}
              </p>
              {retry.kind === 'EXTRA' && (
                <button type="button" className="mg-start sw-go" disabled={actions.start.isPending || !session?.child}
                  onClick={() => { if (session?.child) void actions.start.mutateAsync({ mission: a.mission, child: session.child })
                    .then(next => navigate(`/student/attempts/${encodeURIComponent(next.attemptId)}`)).catch(() => {}) }}>
                  이 미션 다시 풀기
                </button>
              )}
              {retry.kind === 'SCENE' && (
                <button type="button" className="mg-start sw-go" onClick={() => navigate(`/student/theme/scene/${retry.day}`)}>
                  이 미션 다시 풀기
                </button>
              )}
              {retry.kind === 'SATURDAY' && <p className="sw-retry-note">토요일에 다시 풀 수 있어요.</p>}
              <ErrorNotice error={actions.start.error} />
            </section>
          )}
          {a.status !== 'COMPLETED' && (
            <section className="sw-ideas sw-howwas" aria-labelledby="sw-howwas-title">
              <div className="sw-reflect">
                <div className="sw-howwas-l">
                  <h3 id="sw-howwas-title">이번 활동은 어땠나요? <small>하나 골라 주세요</small></h3>
                  <input className="sw-howwas-input" aria-label="달라진 점 (선택)" value={reflection} onChange={(e) => setReflection(e.target.value)} maxLength={1200}
                    placeholder="달라진 생각 한 줄 (안 써도 돼요)" />
                </div>
                <div className="cj-difficulties" role="group" aria-label="난이도">
                  {(['쉬웠어', '보통', '어려웠어'] as const).map((d) => (
                    <button type="button" key={d} data-level={d} aria-pressed={difficulty === d} disabled={pending}
                      onClick={() => { setDifficulty(d); setNotice('') }}><span className="sw-face" aria-hidden="true">{FACES[d]}</span>{difficultyLabel(d)}</button>
                  ))}
                </div>
                {/* 칸 높이가 고정된 세 칸 배치에서도 안내가 보이게 그 칸 안에서 스크롤 */}
                {notice && <p role="alert" ref={howwasAlert}>{notice}</p>}
              </div>
            </section>
          )}
          {a.status !== 'COMPLETED' && (
            // 난이도는 필수(FN-LRN-12). 고르기와 넘어가기를 나눠, 카드 밖 아래 오른쪽 단추로 미션 완료(사용자 결정 2026-11-23)
            <div className="sw-finish-next">
              <button type="button" className="mg-start sw-go" disabled={pending} onClick={() => { void complete() }}>
                미션 완료하기<span aria-hidden="true"> →</span>
              </button>
            </div>
          )}
          {alerts}
        </div>
      )}
      {(leaveOpen || blocker.state === 'blocked') && draft && (
        <Modal title="아직 저장하지 못한 입력이 있어요." onClose={stay}>
          <p>
            저장하고 나갈까요? 저장하지 않으면 쓴 글이 사라져요.
          </p>
          <ErrorNotice error={saveError} />
          <div className="cj-modal-actions">
            <button type="button" className="cj-secondary" onClick={stay}>
              계속 작성
            </button>
            <button
              type="button"
              className="cj-primary"
              disabled={saveState === 'SAVING' || saveState === 'CONFLICT'}
              onClick={() => {
                void store(structuredClone(draft), editVersion.current).then((saved) => {
                  if (saved) exit()
                })
              }}
            >
              저장하고 나가기
            </button>
            <button
              type="button"
              className="cj-secondary"
              disabled={saveState === 'SAVING'}
              onClick={exit}
            >
              저장하지 않고 나가기
            </button>
          </div>
        </Modal>
      )}
      {conflict && draft && (
        <Modal title="다른 화면에 더 최신 초안이 있어요." onClose={() => setConflict(null)}>
          <h3>현재 입력</h3>
          <p className="cj-quote">{answerText(draft.answer)}</p>
          <p>글 메모: {draft.memo || '없음'}</p>
          <h3>서버의 최신 초안</h3>
          <p className="cj-quote">{answerText(conflict.answer)}</p>
          <p>글 메모: {conflict.memo || '없음'}</p>
          <div className="cj-modal-actions">
            <button
              type="button"
              className="cj-secondary"
              onClick={() => {
                setBackup(structuredClone(draft))
                // 다른 곳에서 쓴 글로 바꾸면 이 화면의 첫 입력 시각이 맞지 않으므로 이번 답은 시간 없음(P28)
                if (timing.current && hasTypedText(conflict.answer)) timing.current = { ...timing.current, resumed: true }
                setDraft(conflict)
                setConflict(null)
                setDirty(false)
                setSaveState('SAVED')
                setSaveError(null)
              }}
            >
              다른 곳에서 쓴 글 쓰기
            </button>
            <button
              type="button"
              className="cj-primary"
              onClick={() => {
                setBackup(structuredClone(conflict))
                setDraft({ ...draft, version: conflict.version })
                setConflict(null)
                setSaveState('DIRTY')
                setSaveError(null)
                setDirty(true)
              }}
            >
              지금 쓴 글로 저장
            </button>
          </div>
        </Modal>
      )}
      {doneNow && <MissionDone attempt={a} childId={session?.child?.id} onEnding={onCompleted} />}
    </section>
  )
}

/** 되묻기 종류 이름(시안 Feedback의 노란 꼬리표) */
/**
 * 답 쓰기 도우미(시안 MissionWrite 말풍선, 화면 안 규칙·AI 호출 없음, 사용자 의견 2026-11-15 "칸이 커서 어떻게 써야 할지 모를 것 같아").
 * 글쓰기·주장 글에서 지금 쓴 만큼에 따라 한마디와 시작 문장 단추를 준다. 단추를 누르면 그 칸 끝에 문장이 붙는다(○○는 학생이 바꿔 씀).
 * 낱말은 권유 기준일 뿐 판정이 아니다.
 */
type Starter = { text: string; optional?: boolean; apply: (a: AnswerContent) => AnswerContent }
/** 입력 방식마다 답 칸 제목과 끝 버튼(사용자 결정 2026-11-19 #807): 고르는 문제에 "쓰기·다 썼어요"가 나오지 않게 */
const panelTitle: Record<AnswerContent['inputType'], string> = {
  NARRATIVE: '내 생각 쓰기', SOLUTION_STEPS: '풀이 쓰기', ESSAY: '내 생각 쓰기',
  CHOICE: '답 고르기', ORDERING: '순서 정하기', CLASSIFICATION: '나누기',
}
const doneLabel: Record<AnswerContent['inputType'], string> = {
  NARRATIVE: '다 썼어요', SOLUTION_STEPS: '다 썼어요', ESSAY: '다 썼어요',
  CHOICE: '이걸로 할래요', ORDERING: '이 순서로 할래요', CLASSIFICATION: '다 나눴어요',
}
const plain = (s: string) => s.replace(/\s/g, '').length
const append = (prev: string, add: string) => (prev.trim() ? prev.replace(/\s*$/, ' ') : '') + add
function writingGuide(v: AnswerContent, more: boolean, choices = 0): { line: string; starters: Starter[] } | null {
  // 고르기·순서·분류: 시작 문장 없이 할 일만(사용자 의견 2026-11-19 "고르기 문제면 처음에 시작할 때 어려울 것 같아", #807)
  if (v.inputType === 'CHOICE')
    return { line: v.choiceIds.length ? '왜 그게 맞는지 한 번 더 생각해 보고 보내 줘!' : '보기를 하나씩 읽어 보고 맞는 것을 골라 봐.', starters: [] }
  if (v.inputType === 'ORDERING')
    return { line: !v.choiceIds.length ? '먼저인 것부터 차례로 눌러 봐.' : v.choiceIds.length < choices ? '다음은 무엇일까? 이어서 눌러 봐.' : '순서가 맞는지 처음부터 읽어 보고 보내 줘!', starters: [] }
  if (v.inputType === 'CLASSIFICATION')
    return { line: !v.assignments.length ? '하나씩 보고 어느 쪽인지 눌러 봐.' : v.assignments.length < choices ? '아직 안 나눈 것이 있어.' : '다 나눴어! 맞는지 한 번 더 보고 보내 줘.', starters: [] }
  if (v.inputType === 'NARRATIVE') {
    const n = plain(v.text)
    const add = (text: string, optional = false): Starter => ({ text, optional, apply: (a) => ({ ...a, text: append(a.text, text) }) })
    if (n === 0)
      return more
        ? { line: '뭉치 질문에 이렇게 시작해 봐!', starters: [add('그건 ○○ 때문이에요.')] }
        : { line: '뭐부터 쓸지 모르겠으면 이렇게 시작해 봐!', starters: [add('나는 ○○라고 생각해요.')] }
    if (!/왜냐하면|때문|이유/.test(v.text)) return { line: '왜 그렇게 생각했는지도 써 볼까?', starters: [add('왜냐하면 ○○ 때문이에요.')] }
    if (n < 10) return { line: '조금만 더 써 볼까? 한두 문장이면 충분해!', starters: [] }
    return { line: '좋아! 다 썼으면 뭉치에게 보내 줘. 더 쓰고 싶으면 이것도 좋아.', starters: /다르게|다른 친구|다른 생각/.test(v.text) ? [] : [add('다르게 생각하면 ○○일 수도 있어요.', true)] }
  }
  if (v.inputType === 'SOLUTION_STEPS') {
    const put = (i: number, text: string): Starter => ({ text, apply: (a) => ({ ...a, steps: a.steps.map((s, j) => (j === i ? append(s, text) : s)) }) })
    const empty = v.steps.findIndex((s) => !s.trim())
    if (empty === 0) return { line: '먼저 무엇을 구하는지 써 볼까?', starters: [put(0, '구하려는 것은 ○○이에요.')] }
    if (empty > 0) return { line: '어떻게 계산했는지 식으로 써 봐!', starters: [put(empty, '○○ 방법으로 계산하면 ○ = ○ 이에요.')] }
    if (!v.finalAnswer.trim()) return { line: '마지막으로 최종 답 칸에 답을 써 줘!', starters: [] }
    return { line: '좋아! 답이 맞는지 한 번 더 보고 뭉치에게 보내 줘.', starters: [] }
  }
  if (v.inputType === 'ESSAY') {
    const e = v.essay
    const set = (text: string, put: (a: AnswerContent) => AnswerContent): Starter => ({ text, apply: put })
    if (!e.claim.trim()) return { line: '먼저 내 주장을 한 문장으로 써 봐!', starters: [set('나는 ○○ 쪽이 좋다고 생각해요.', (a) => ({ ...a, essay: { ...a.essay, claim: append(a.essay.claim, '나는 ○○ 쪽이 좋다고 생각해요.') } }))] }
    const empty = e.reasons.findIndex((r) => !r.trim())
    if (empty >= 0) {
      const text = empty === 0 ? '첫째, ○○ 때문이에요.' : '둘째, ○○ 때문이에요.'
      return { line: `이유 ${empty + 1}을 써 볼까?`, starters: [set(text, (a) => ({ ...a, essay: { ...a.essay, reasons: a.essay.reasons.map((r, i) => (i === empty ? append(r, text) : r)) as [string, string] } }))] }
    }
    if (!e.rebuttal.trim()) return { line: '다르게 생각하는 친구에게 한마디 해 볼까?', starters: [set('○○라고 생각할 수도 있지만, ○○', (a) => ({ ...a, essay: { ...a.essay, rebuttal: append(a.essay.rebuttal, '○○라고 생각할 수도 있지만, ○○') } }))] }
    return { line: '좋아! 다 썼으면 뭉치에게 보내 줘.', starters: [] }
  }
  return null
}

export function AnswerFields({
  answer: v,
  mission,
  onChange,
  guide = false,
}: {
  answer: AnswerContent
  mission: LearningMission
  onChange: (a: AnswerContent) => void
  /** 학생 답 쓰기: 빈 칸 안내와 글자 수(시안 MissionWrite "한두 문장이면 충분해요"), 붙여넣기 막기(P28). 관리자 미리보기는 그대로 */
  guide?: boolean
}) {
  // 학생 답변 칸만 붙여넣기·끌어다 놓기 막기(P28, 안내 문구 없음·입력 내용 유지). 관리자 미리보기(guide 없음)와 메모·돌아보기는 그대로
  const noPaste = guide
    ? { onPaste: (e: { preventDefault: () => void }) => e.preventDefault(), onDrop: (e: { preventDefault: () => void }) => e.preventDefault() }
    : {}
  const field = (label: string, value: string, setter: (value: string) => void, placeholder?: string) => (
    <label className="cj-field">
      {label}
      <textarea
        aria-label={label}
        value={value}
        placeholder={guide ? placeholder : undefined}
        onChange={(e) => setter(e.target.value)}
        maxLength={2400}
        {...noPaste}
      />
    </label>
  )
  return (
    <div className="ux-answer-fields">
      {v.inputType === 'NARRATIVE' &&
        field('내 생각과 이유', v.text, (text) => onChange({ ...v, text }), '뭉치가 알려 준 문장으로 시작하거나 자유롭게 써 봐요')}
      {v.inputType === 'NARRATIVE' && guide && (
        <small className="sw-count" aria-live="polite">{v.text.replace(/\s/g, '').length ? `공백 빼고 ${v.text.replace(/\s/g, '').length}자` : '한두 문장이면 충분해요'}</small>
      )}
      {v.inputType === 'SOLUTION_STEPS' && (
        <>
          {/* 시안 Main·Problems 순서: 풀이 단계 다음에 최종 답 */}
          {Array.from({ length: Math.max(v.steps.length, mission.inputTemplate?.length ?? 0) }, (_, i) => v.steps[i] ?? '').map((step, i) => (
            <div key={i}>
              {field(mission.inputTemplate?.[i] || `풀이 ${i + 1}`, step, (value) =>
                onChange({ ...v, steps: Array.from({ length: Math.max(v.steps.length, mission.inputTemplate?.length ?? 0) }, (_, j) => i === j ? value : v.steps[j] ?? '') }),
                // 수학 풀이 틀(기능 명세 1.5: 무엇을 구하나요·어떻게 구할까요·계산·확인해 보기)을 칸 안내로
                i === 0 ? '무엇을 구하나요? 어떻게 구할까요?' : '계산한 식을 쓰고, 답이 맞는지 다시 봐요.',
              )}
            </div>
          ))}
          <label className="cj-field">
            최종 답
            <span className="ux-answer-unit">
              <input aria-label="최종 답" inputMode="decimal" value={v.finalAnswer}
                maxLength={120} onChange={(e) => onChange({ ...v, finalAnswer: e.target.value })} {...noPaste} />
              {mission.answerUnit && <span aria-label="답 단위">{mission.answerUnit}</span>}
            </span>
            {mission.answerUnit && <small>숫자만 써 주세요.</small>}
          </label>
        </>
      )}
      {v.inputType === 'ESSAY' && (
        <>
          {field(mission.inputTemplate?.[0] || '내 주장', v.essay.claim, (claim) =>
            onChange({ ...v, essay: { ...v.essay, claim } }),
          )}
          {v.essay.reasons.map((reason, i) => (
            <div key={i}>
              {field(mission.inputTemplate?.[i + 1] || `이유 ${i + 1}`, reason, (value) =>
                onChange({
                  ...v,
                  essay: {
                    ...v.essay,
                    reasons: v.essay.reasons.map((s, j) => (i === j ? value : s)) as [
                      string,
                      string,
                    ],
                  },
                }),
              )}
            </div>
          ))}
          {field(mission.inputTemplate?.[3] || '다른 의견에 답하기', v.essay.rebuttal, (rebuttal) =>
            onChange({ ...v, essay: { ...v.essay, rebuttal } }),
          )}
        </>
      )}
      {['CHOICE', 'ORDERING'].includes(v.inputType) && (
        <div className="ux-choices" role="group" aria-label="답 고르기">
          {mission.choices?.map((choice) => (
            <button
              type="button"
              key={choice.id}
              className="cj-secondary"
              aria-pressed={v.choiceIds.includes(choice.id)}
              onClick={() =>
                onChange({
                  ...v,
                  choiceIds:
                    v.inputType === 'CHOICE'
                      ? [choice.id]
                      : v.choiceIds.includes(choice.id)
                        ? v.choiceIds.filter((id) => id !== choice.id)
                        : [...v.choiceIds, choice.id],
                })
              }
            >
              {v.inputType === 'ORDERING' && v.choiceIds.includes(choice.id)
                ? `${v.choiceIds.indexOf(choice.id) + 1}. `
                : ''}
              {choice.label}
            </button>
          ))}
        </div>
      )}
      {v.inputType === 'ORDERING' && (
        <>
          <ol aria-label="선택한 순서">
            {v.choiceIds.map((id) => (
              <li key={id}>{mission.choices?.find((c) => c.id === id)?.label}</li>
            ))}
          </ol>
          <button
            type="button"
            className="cj-secondary"
            onClick={() => onChange({ ...v, choiceIds: [] })}
          >
            순서 다시 고르기
          </button>
        </>
      )}
      {v.inputType === 'CLASSIFICATION' && (
        // 항목마다 무리 이름 단추(시안 InputTypes 분류하기). 같은 단추를 다시 누르면 고른 것을 뺀다
        <div className="ux-classification">
          {mission.choices?.map((c) => {
            const current = v.assignments.find((a) => a.choiceId === c.id)?.categoryId ?? ''
            return (
              <div className="ux-class-row" key={c.id}>
                <span>{c.label}</span>
                <div role="group" aria-label={c.label}>
                  {mission.categories?.map((g) => (
                    <button
                      type="button"
                      key={g.id}
                      className="cj-secondary"
                      aria-pressed={current === g.id}
                      onClick={() =>
                        onChange({
                          ...v,
                          assignments: [
                            ...v.assignments.filter((a) => a.choiceId !== c.id),
                            ...(current === g.id ? [] : [{ choiceId: c.id, categoryId: g.id }]),
                          ],
                        })
                      }
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <label className="ux-guardian">
        <input
          type="checkbox"
          checked={v.dictatedByGuardian}
          onChange={(e) => onChange({ ...v, dictatedByGuardian: e.target.checked })}
        />
        보호자가 아이의 말을 그대로 적었어요.
      </label>
    </div>
  )
}
function FeedbackEvidence({
  feedback,
  text,
  inputType,
  lit,
  onLit,
}: {
  feedback: import('../../domain/classroom.ts').Feedback
  text: string
  inputType: AnswerContent['inputType']
  lit: string | null
  onLit: (id: string) => void
}) {
  const judgment = feedback.judgment
  if (!judgment || CLOSED_TYPES.includes(inputType)) return null
  // 결과 이름만(#440 26번): '판정'은 내부 말이라 빼고, 보류일 때는 피드백 상자가 이미 '답을 잘 받았어요.'라고 해서 이름을 안 보인다.
  // 'AI 채점(시범)' 표시는 기능명세 FN-JDG-03이라 그대로 둠(#440 27번 보류)
  // 근거 상자 대신 생각 스티커(사용자 결정 2026-11-20, 구절은 위 답 글의 형광펜). 결과 이름(정답 등)은 오른쪽 피드백 상자와 겹쳐 뺌, 'AI 채점(시범)'은 오른쪽 피드백 상자에 있어 여기선 안 겹치게(FN-JDG-03)
  return <Stickers items={judgment.elements ?? []} texts={[text]} label="피드백 생각" lit={lit} onLit={onLit} />
}

/**
 * 한 화면에 맞춘 마무리의 카드: 칸 높이를 넘으면 '더 보기', 누르면 창 없이 그 칸을 펼치고 '접기'로 되돌림(사용자 결정 2026-11-23).
 * 펼침 상태는 부모가 쥔다(펼친 동안 한 화면 맞춤을 풂). 이어 붙이는 화면은 칸을 자르지 않아 '더 보기'가 생기지 않음
 */
function ClampCard({ className, label, head, foot, after, expanded, onMore, onLess, children }: { className: string; label: string; head: ReactNode; foot?: ReactNode; after?: ReactNode; expanded: boolean; onMore: () => void; onLess: () => void; children: ReactNode }) {
  const body = useRef<HTMLDivElement>(null)
  const [over, setOver] = useState(false)
  useLayoutEffect(() => {
    const el = body.current
    if (!el) return
    const check = () => setOver(el.scrollHeight > el.clientHeight + 2)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const more = expanded
    ? <button type="button" className="sw-more" aria-expanded="true" onClick={onLess}>접기</button>
    : over && <button type="button" className="sw-more" aria-expanded="false" onClick={onMore}>더 보기</button>
  return (
    <section className={className} aria-label={label}>
      {head}
      <div ref={body} className="sw-clamp" data-over={over || undefined}>{children}</div>
      {after}
      <div className="sw-clamp-foot">
        {foot}
        {more}
      </div>
    </section>
  )
}

/** 다시 푼 문제만 내 답 아래 '저번엔' 한 줄(이전 답 비교 창 대신, 사용자 결정 2026-11-23)(날짜·판정·답변 번호 없이 저번 마지막 답 글만, 처음 푼 문제는 없음) */
function PrevAnswer({ attempt }: { attempt: Attempt }) {
  const cmp = useAttemptComparison(attempt).data
  const prev = cmp?.previous
  const last = prev?.answers.at(-1)
  if (!prev || !last) return null
  const text = comparisonAnswerText(last, prev.mission)
  return (
    <p className="sw-prev" title={text}>
      <b>저번엔</b>
      <span>{text}</span>
    </p>
  )
}

/**
 * 마무리 영역을 화면 남은 높이에 맞춘다(PC·태블릿). 카드는 그 안에서 줄어들고 넘치면 '더 보기'.
 * 아래 줄 배치는 너비 760px 초과·높이 800px 이상·남은 높이 400px(카드마다 두세 줄이 보이는 최소) 이상, 세 칸 배치(`wide`)는
 * 너비 960px 이상·높이 800px 미만·남은 높이 480px 이상일 때 맞춘다. 그 밖은 맞추지 않고 아래로 이어 붙인다(휴대폰·아주 낮은 화면).
 */
function useFitHeight(ref: React.RefObject<HTMLDivElement | null>, enabled: boolean) {
  const [fit, setFit] = useState<{ height: number | null; wide: boolean }>({ height: null, wide: false })
  useLayoutEffect(() => {
    if (!enabled) return
    const fit = () => {
      const el = ref.current
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      // 마무리 영역 아래에 실제로 붙는 것은 감싼 칸들의 아래 안쪽 여백·테두리뿐(.st-world 최소 높이로 생기는 빈 곳은 세지 않음)
      let pad = 0
      // 바깥 파란 틀(.st-world) 아래 여백은 화면 밖으로 내려가도 됨 — 흰 종이 안쪽 여백까지만
      for (let node = el.parentElement; node && !node.classList.contains('st-world'); node = node.parentElement) {
        const cs = getComputedStyle(node)
        pad += parseFloat(cs.paddingBottom) + parseFloat(cs.borderBottomWidth)
      }
      const avail = Math.floor(window.innerHeight - top - pad)
      // 높이 800px 이상은 아래 줄 배치로 맞춤. 낮고 넓은 화면(가로 태블릿·낮은 노트북)은 어땠나요를 오른쪽 칸으로 옮긴 세 칸 배치로 맞춤.
      // 그 밖(휴대폰·좁고 낮은 화면)은 이어 붙임(사용자 결정 2026-11-23)
      const w = window.innerWidth, h = window.innerHeight
      const wide = w >= 960 && h < 800
      setFit((p) => {
        const next = { height: (w > 760 && h >= 800 && avail >= 400) || (wide && avail >= 480) ? avail : null, wide }
        return p.height === next.height && p.wide === next.wide ? p : next
      })
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [enabled, ref])
  return enabled ? fit : NO_FIT
}
const NO_FIT = { height: null, wide: false }

const CLOSED_TYPES: AnswerContent['inputType'][] = ['CHOICE', 'ORDERING', 'CLASSIFICATION']
const FACES = { 쉬웠어: '😄', 보통: '🙂', 어려웠어: '😥' } as const
type Mark = { quote: string; n: number; id: string }
/** 공백을 \s+로 바꿔 찾음(ai verifier.is_verbatim처럼 공백 차이 허용) */
const loose = (q: string) => new RegExp(q.trim().split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+'))
const found = (e: import('../../domain/classroom.ts').FeedbackElement, texts: string[]) =>
  e.satisfied && !!e.quote?.trim() && texts.some((t) => loose(e.quote!).test(t))
/** 찾은 요소만 순서대로 번호(스티커와 형광펜이 같은 번호·색) */
function foundMarks(items: import('../../domain/classroom.ts').FeedbackElement[], texts: string[]): Mark[] {
  return items.filter((e) => found(e, texts)).map((e, k) => ({ quote: e.quote!, n: k + 1, id: e.elementId }))
}
/** 찾은 구절에만 밑줄 형광펜 + 끝에 작은 번호(그 번호 스티커와 짝) */
function highlight(text: string, marks: Mark[]): ReactNode {
  if (!marks.length) return text
  const out: ReactNode[] = []
  let rest = text, key = 0
  while (rest) {
    let best: { at: number; len: number; n: number } | null = null
    for (const m of marks) {
      const hit = loose(m.quote).exec(rest)
      if (hit && (!best || hit.index < best.at)) best = { at: hit.index, len: hit[0].length, n: m.n }
    }
    if (!best) { out.push(rest); break }
    if (best.at) out.push(rest.slice(0, best.at))
    out.push(<mark key={key++} className="sw-hl" data-n={best.n}>{rest.slice(best.at, best.at + best.len)}</mark>)
    rest = rest.slice(best.at + best.len)
  }
  return out
}

/**
 * 들어가면 좋은 생각을 스티커로(사용자 결정 2026-11-20)(FN-LRN-11: 근거 구절이 확인된 요소만 체크, 구절은 위 형광펜).
 * 확인 못 한 것은 점선 — AI가 놓쳤을 수도 있어 "안 썼다"가 아니라 "뭉치가 아직 못 찾은" 것으로 말한다.
 */
function ThoughtStickers({ attempt, lit, onLit }: { attempt: Attempt; lit: string | null; onLit: (id: string) => void }) {
  // 다시 푼 문제: 같은 기준일 때만 이번에 새로 찾은 생각에 '새로!'(FN-LRN-11·#207 확인 항목 변화)
  const cmp = useAttemptComparison(attempt).data
  const fresh = new Set(cmp?.state === 'COMPARABLE' ? cmp.elements.filter((e) => e.change === 'ADDED').map((e) => e.elementId) : [])
  return <Stickers items={attempt.checklist ?? []} texts={attempt.answers.map((v) => v.text)} label="마무리 체크리스트" title="들어가면 좋은 생각" lit={lit} onLit={onLit} fresh={fresh} />
}
function Stickers({ items, texts, label, title, lit, onLit, fresh }: { items: import('../../domain/classroom.ts').FeedbackElement[]; texts: string[]; label: string; title?: string; lit: string | null; onLit: (id: string) => void; fresh?: Set<string> }) {
  if (!items.length) return null
  const yes = items.filter((e) => found(e, texts))
  const no = items.filter((e) => !found(e, texts))
  return (
    <div className="sw-stickers-wrap" aria-label={label} role="group">
      {title && <h3 className="sw-stick-title">{title}</h3>}
      {yes.length > 0 && (
        <div className="sw-stick-row">
          <b>뭉치가 찾았어 <small className="sw-stick-tip">눌러 봐</small></b>
          <ul className="sw-stickers">
            {yes.map((e, k) => (
              <li key={e.elementId} data-checked data-n={k + 1} data-lit={lit === e.elementId || undefined} data-evidence-verified="true">
                <button type="button" aria-pressed={lit === e.elementId} onClick={() => onLit(e.elementId)}
                  aria-label={`${e.label} — 내 답에서 찾은 곳: ${e.quote}`}>
                  <span className="sw-stick-n" aria-hidden="true">{k + 1}</span>{e.label}
                  {fresh?.has(e.elementId) && <span className="sw-new">새로!</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {no.length > 0 && (
        <div className="sw-stick-row sw-stick-row-no">
          <b>아직 못 찾았어</b>
          <ul className="sw-stickers">
            {no.map((e) => <li key={e.elementId} data-evidence-verified="false">{e.label}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
