import { useCallback, useEffect, useRef, useState } from 'react'
import { useBlocker } from 'react-router'
import { ArrowLeft, Check, Lightbulb, NotebookPen, Pencil, Volume2 } from 'lucide-react'
import { useAttempt, useLearningActions, isDemo } from '../../data/classroom/useClassroom.ts'
import { DraftConflictError } from '../../data/classroom/errors.ts'
import {
  answerText,
  blankAnswer,
  canAddAnswer,
  canFinish,
  inputLabels,
  latestFeedback,
  validateAnswer,
  isVerifiedElement,
  thinkingLabels,
} from '../../domain/classroom.ts'
import type { AnswerContent, Attempt, Draft, Reflection } from '../../domain/classroom.ts'
import { ActivityPaper, ErrorNotice, MemoCanvas, Modal } from '../shared/ClassroomParts.tsx'
import { MissionScene } from './MissionScene.tsx'
import { Companion } from './world/Companion.tsx'
import { useLook } from './world/lookContext.ts'
import { STAGE_LABELS, companionLabel, missionStage } from '../../domain/studentLook.ts'
import type { MissionStage } from '../../domain/studentLook.ts'
import { ApiError } from '../../data/apiClient.ts'
import { appendMemo, memoTargets } from '../../domain/memoTransfer.ts'

export function StudentWorkPage({ attemptId, onBack }: { attemptId: string; onBack: () => void }) {
  const query = useAttempt(attemptId)
  if (query.isPending)
    return (
      <div className="cj-empty" role="status">
        저장된 활동을 읽고 있어요.
      </div>
    )
  if (!query.data || query.error)
    return (
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch()
        }}
      />
    )
  return <StudentEditor key={attemptId} a={query.data} onBack={onBack} />
}
function StudentEditor({ a, onBack }: { a: Attempt; onBack: () => void }) {
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
    [more, setMore] = useState(false)
  const [memoTarget, setMemoTarget] = useState(''),
    [memoError, setMemoError] = useState('')
  const [conflict, setConflict] = useState<Draft | null>(null),
    [backup, setBackup] = useState<Draft | null>(null)
  const [reflectOpen, setReflectOpen] = useState(false),
    [difficulty, setDifficulty] = useState<Reflection['difficulty'] | ''>(''),
    [reflection, setReflection] = useState('')
  const editVersion = useRef(0),
    submission = useRef<{ signature: string; key: string } | null>(null)
  const resumedFeedback = useRef<string | null>(null)
  const requestFeedback = actions.feedback.mutateAsync
  useEffect(() => {
    const last = a.answers.at(-1)
    if (
      !last ||
      !['PENDING', 'RUNNING'].includes(last.feedback.status) ||
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
    editVersion.current++
    setDraft((current) => (current ? { ...current, answer } : current))
    setDirty(true)
    if (!['FAILED', 'CONFLICT', 'SAVING'].includes(saveState)) setSaveState('DIRTY')
  }
  async function feedback() {
    if (!a?.answers.length) return
    setError(null)
    try {
      await actions.feedback.mutateAsync({ attempt: a, answerId: a.answers.at(-1)!.answerId })
    } catch (e) {
      setRetryAction(() => feedback)
      setError(e)
    }
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
      submission.current = { signature, key: crypto.randomUUID() }
    setError(null)
    setNotice('')
    try {
      const saved = await actions.submit.mutateAsync({
        id: a.attemptId,
        answer: draft.answer,
        key: submission.current!.key,
        followupId: latestFeedback(a)?.followup?.followupId,
      })
      resumedFeedback.current = saved.answers.at(-1)!.answerId
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
      setReflectOpen(false)
      onBack()
    } catch (e) {
      setRetryAction(() => complete)
      setError(e)
    }
  }
  const { companion } = useLook()
  const stage = missionStage(a)
  const f = latestFeedback(a),
    writing = !a.finishedAt && (a.answers.length === 0 || more) && canAddAnswer(a)
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
  return (
    <section className="cj-editor st-work" aria-label="미션 작성기">
      <header className="st-work-top">
        <button type="button" className="st-back" onClick={back}>
          <ArrowLeft aria-hidden="true" />
          공책으로
        </button>
        <ol className="st-steps" aria-label="미션 진행 단계">
          {(Object.keys(STAGE_LABELS) as MissionStage[]).map((s, i, all) => {
            const at = all.indexOf(stage)
            return (
              <li key={s} aria-current={s === stage ? 'step' : undefined} data-done={i < at || undefined}>
                {i < at && <Check aria-hidden="true" />}
                {STAGE_LABELS[s]}
              </li>
            )
          })}
        </ol>
      </header>
      <div className="st-paper st-work-paper">
        <div className="ux-answer-paper">
          <div className="ux-paper-question">
            <p className="st-kicker">
              {a.mission.subject} · {thinkingLabels[a.mission.thinkingType]} · 초등 {a.mission.grade}학년
              {isDemo ? ' · 화면 시연' : ''}
            </p>
            <h1>{a.mission.title}</h1>
            <div className="st-ask">
              <Companion kind={companion} size={64} decorative />
              <div className="st-say">
                <span className="st-visually-hidden">{companionLabel(companion)}의 질문</span>
                <h2>{a.mission.question}</h2>
                <small>{memo ? '생각 메모 · 나만 보기' : inputLabels[a.mission.inputType]}</small>
              </div>
            </div>
            <MissionScene mission={a.mission} />
            <div className="st-tools" role="group" aria-label="작성 도구">
              <button type="button" aria-label="답변 쓰기" aria-pressed={!memo} onClick={() => setMemo(false)}>
                <NotebookPen aria-hidden="true" />
                답변
              </button>
              <button
                type="button"
                aria-label="생각 메모"
                aria-pressed={memo}
                onClick={() => setMemo(true)}
                disabled={!!a.finishedAt}
              >
                <Pencil aria-hidden="true" />
                메모
              </button>
              <button
                type="button"
                aria-label="생각 열기"
                disabled={!!a.finishedAt}
                onClick={() => {
                  void actions.hint.mutateAsync(a.attemptId).then(setHint).catch(setError)
                }}
              >
                <Lightbulb aria-hidden="true" />
                생각 열기
              </button>
              <button
                type="button"
                aria-label="질문 읽기"
                onClick={() => {
                  if (!window.speechSynthesis) {
                    setNotice('이 브라우저에서는 읽어주기를 지원하지 않습니다.')
                    return
                  }
                  window.speechSynthesis.cancel()
                  const voice = new SpeechSynthesisUtterance(a.mission.question)
                  voice.lang = 'ko-KR'
                  window.speechSynthesis.speak(voice)
                }}
              >
                <Volume2 aria-hidden="true" />
                읽어 주기
              </button>
            </div>
            {hint && (
              <div className="st-ask st-hint">
                <Companion kind={companion} size={48} decorative />
                <div className="st-say">
                  <strong>생각 열기</strong>
                  <p>{hint}</p>
                </div>
              </div>
            )}
            {more && f?.followup && (
              <div className="st-ask">
                <Companion kind={companion} size={48} decorative />
                <div className="st-say">
                  <strong>한 걸음 더</strong>
                  <p>{f.followup.question}</p>
                </div>
              </div>
            )}
          </div>
            {memo && draft ? (
              <>
                <div className="ux-private">
                  학생 본인만 보는 메모입니다. 제출·판정·학부모 기록에 포함되지 않아요.
                </div>
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
                    <p>옮긴 글은 답변의 일부로 제출됩니다. 원래 메모는 지우지 않습니다.</p>
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
                      <p>답변을 쓰는 중에만 옮길 수 있습니다. 추가 답변 작성을 시작한 뒤 옮겨 주세요.</p>
                    )}
                    <button
                      type="button"
                      className="cj-secondary"
                      disabled={!writing || pending || saveState === 'CONFLICT' || !draft.memo.trim()}
                      onClick={() => {
                        try {
                          change(appendMemo(draft.answer, draft.memo, selectedMemoTarget))
                          setMemoError('')
                          setNotice('선택한 답변 칸에 글 메모를 덧붙였습니다. 제출 전에 확인해 주세요.')
                          setMemo(false)
                        } catch (e) {
                          setMemoError(e instanceof Error ? e.message : '메모를 옮기지 못했습니다.')
                        }
                      }}
                    >
                      글 메모 전체를 답변으로 옮기기
                    </button>
                    {memoError && <p role="alert">{memoError}</p>}
                  </>
                ) : (
                  <p>고르기·순서·분류 문제에서는 답변 화면에서 직접 골라 주세요. 글 메모를 선택 답으로 자동 변환하지 않습니다.</p>
                )}
              </>
            ) : writing && draft ? (
              <AnswerFields answer={draft.answer} mission={a.mission} onChange={change} />
            ) : (
              <>
                {a.answers.map((v) => (
                  <section className="ux-answer-version" key={v.answerId}>
                    <small>
                      {v.version === 1 ? '처음 남긴 답' : `덧붙인 답 ${v.version - 1}`} · 별도 버전
                      보존
                    </small>
                    <p className="cj-quote">{v.text}</p>
                    {v.feedback.judgment && (
                      <FeedbackEvidence feedback={v.feedback} text={v.text} />
                    )}
                    {v.feedback.followup && (
                      <div className="ux-timeline-question">
                        <small>
                          {v.feedback.followup.type === 'ONE_STEP_MORE'
                            ? '한 걸음 더'
                            : v.feedback.followup.type === 'LOOK_AGAIN'
                              ? '다시 살펴보기'
                              : '더 말해 보기'}
                        </small>
                        <p>{v.feedback.followup.question}</p>
                      </div>
                    )}
                  </section>
                ))}
                {f && (
                  <div className="ux-feedback" role="status">
                    <strong>
                      {f.status === 'DONE'
                        ? f.judgment?.result === 'HELD'
                          ? '판정 보류 · 답변은 기록했어요.'
                          : f.judgment?.result === 'CORRECT'
                            ? '정답을 확인했어요.'
                            : '한 번 더 살펴볼까요?'
                        : f.status === 'FAILED'
                          ? '답변 저장 완료 · 피드백 처리 실패'
                          : '답변 저장 완료 · 피드백 처리 중'}
                    </strong>
                    {f.judgment?.trial && (
                      <small>AI 채점(시범){isDemo ? ' · 실제 모델 호출 없음' : ''}</small>
                    )}
                    {f.judgment?.result === 'HELD' && (
                      <p>
                        지금은 답을 판단하기 어려워요. 작성한 답은 저장했으니 질문을 읽고 생각을 더
                        남겨 보세요.
                      </p>
                    )}
                    {f.followup && !a.finishedAt && (
                      <div className="st-ask">
                        <Companion kind={companion} size={56} decorative />
                        <div className="st-say">
                          <p>{f.followup.question}</p>
                          <small>
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
                {a.finishedAt ? (
                  <>
                    <h3>
                      {a.revealKind === 'ANSWER'
                        ? '정답과 비교해 보세요.'
                        : '예시 답과 비교해 보세요.'}
                    </h3>
                    <p className="cj-quote">{a.reveal}</p>
                    <h3>들어가면 좋은 생각</h3>
                    <ul aria-label="마무리 체크리스트" className="ux-checklist">
                      {(a.checklist ?? []).map((e) => {
                        const checked = isVerifiedElement(
                          e,
                          a.answers.map((v) => v.text),
                        )
                        return (
                          <li key={e.elementId}>
                            <span>
                              {checked ? '✓ 확인했어요' : '아직 확인하지 못했어요'} · {e.label}
                            </span>
                            {checked && <blockquote>{e.quote}</blockquote>}
                          </li>
                        )
                      })}
                    </ul>
                    {!a.checklist?.length && (
                      <p>근거로 확인한 항목이 아직 없습니다. 낮은 결과를 뜻하지는 않아요.</p>
                    )}
                    <ActivityPaper mission={a.mission} text={a.answers.at(-1)?.text} />
                    {a.status === 'COMPLETED' ? (
                      <p>
                        돌아보기 완료 · {a.reflection?.difficulty}
                        <br />
                        {a.reflection?.text}
                      </p>
                    ) : (
                      <button
                        type="button"
                        className="cj-primary"
                        onClick={() => {
                          setReflectOpen(true)
                          setNotice('')
                        }}
                      >
                        돌아보기 남기기
                      </button>
                    )}
                  </>
                ) : (
                  <div className="cj-modal-actions">
                    {f?.status === 'FAILED' && (
                      <button
                        type="button"
                        className="cj-primary"
                        disabled={pending}
                        onClick={() => {
                          void feedback()
                        }}
                      >
                        피드백만 다시 요청
                      </button>
                    )}
                    {f?.status === 'RUNNING' && !pending && (
                      <button
                        type="button"
                        className="cj-secondary"
                        onClick={() => {
                          void feedback()
                        }}
                      >
                        처리 결과 다시 확인
                      </button>
                    )}
                    {canAddAnswer(a) && a.answers.length > 0 && (
                      <button type="button" className="cj-primary" onClick={() => setMore(true)}>
                        질문에 답하기
                      </button>
                    )}
                    {canFinish(a) && (
                      <button
                        type="button"
                        className="cj-secondary"
                        disabled={pending}
                        onClick={() => {
                          void finish()
                        }}
                      >
                        {a.answers.length < 3 ? '이대로 돌아보기' : '마무리하기'}
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
            {notice && !reflectOpen && (
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
          </div>
          <div className="st-actions">
            <div className="ux-save-line" role="status">
              {!a.finishedAt && draft && (
                <span>
                  {
                    {
                      SAVED: isDemo ? '초안 저장 완료(모의)' : '초안 저장 완료',
                      DIRTY: '변경 내용 저장 대기',
                      SAVING: '초안 저장 중',
                      FAILED: '초안 저장 실패 · 입력은 유지됩니다.',
                      CONFLICT: '초안 충돌 · 선택 전에는 덮어쓰지 않아요.',
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
              <small>
                {a.finishedAt
                  ? '마무리한 활동은 답변을 더 제출할 수 없어요.'
                  : '다 쓰기 전에는 정답·예시 답을 보여 주지 않아요.'}
              </small>
            </div>
            {writing && !memo && (
              <button
                type="button"
                className="st-button st-primary"
                disabled={pending || saveState === 'CONFLICT' || saveState === 'SAVING'}
                onClick={() => {
                  void submit()
                }}
              >
                {a.answers.length ? '더해서 보내기' : '다 썼어요'}
              </button>
            )}
          </div>
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
      </div>
      {(leaveOpen || blocker.state === 'blocked') && draft && (
        <Modal title="아직 저장하지 못한 입력이 있어요." onClose={stay}>
          <p>
            저장 후 나가거나, 이 화면에서 계속 작성할 수 있습니다. 저장하지 않고 나가면 현재 입력은
            사라집니다.
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
              초안 저장 후 나가기
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
          <p>선택하기 전에는 어느 쪽도 덮어쓰지 않습니다.</p>
          <div className="cj-modal-actions">
            <button
              type="button"
              className="cj-secondary"
              onClick={() => {
                setBackup(structuredClone(draft))
                setDraft(conflict)
                setConflict(null)
                setDirty(false)
                setSaveState('SAVED')
                setSaveError(null)
              }}
            >
              내 입력을 보관하고 최신 초안 사용
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
              현재 입력으로 저장
            </button>
          </div>
        </Modal>
      )}
      {saveState === 'CONFLICT' && !conflict && (
        <button
          type="button"
          className="cj-secondary"
          onClick={() => {
            if (saveError instanceof DraftConflictError) setConflict(saveError.latest)
          }}
        >
          초안 다시 비교
        </button>
      )}
      {backup && (
        <details className="ux-backup">
          <summary>교체 전 초안 확인</summary>
          <p>{answerText(backup.answer)}</p>
        </details>
      )}
      {reflectOpen && (
        <Modal title="이번 활동은 어땠나요?" onClose={() => setReflectOpen(false)}>
          <div className="cj-difficulties">
            {(['쉬웠어', '보통', '어려웠어'] as const).map((d) => (
              <button
                type="button"
                key={d}
                aria-pressed={difficulty === d}
                onClick={() => setDifficulty(d)}
              >
                {d === '보통' ? '보통이에요' : d === '쉬웠어' ? '쉬웠어요' : '어려웠어요'}
              </button>
            ))}
          </div>
          <label className="cj-field">
            달라진 점 (선택)
            <textarea
              value={reflection}
              onChange={(e) => setReflection(e.target.value)}
              maxLength={1200}
            />
          </label>
          {notice && <p role="alert">{notice}</p>}
          <button
            type="button"
            className="cj-primary"
            disabled={pending}
            onClick={() => {
              void complete()
            }}
          >
            돌아보기 저장하고 완료
          </button>
          <ErrorNotice error={error} />
        </Modal>
      )}
    </section>
  )
}

export function AnswerFields({
  answer: v,
  mission,
  onChange,
}: {
  answer: AnswerContent
  mission: import('../../domain/classroom.ts').Mission
  onChange: (a: AnswerContent) => void
}) {
  const field = (label: string, value: string, setter: (value: string) => void) => (
    <label className="cj-field">
      {label}
      <textarea
        aria-label={label}
        value={value}
        onChange={(e) => setter(e.target.value)}
        maxLength={2400}
      />
    </label>
  )
  return (
    <div className="ux-answer-fields">
      {v.inputType === 'NARRATIVE' &&
        field('내 생각과 까닭', v.text, (text) => onChange({ ...v, text }))}
      {v.inputType === 'SOLUTION_STEPS' && (
        <>
          <label className="cj-field">
            최종 답
            <input
              value={v.finalAnswer}
              maxLength={120}
              onChange={(e) => onChange({ ...v, finalAnswer: e.target.value })}
            />
          </label>
          {v.steps.map((step, i) => (
            <div key={i}>
              {field(`풀이 ${i + 1}`, step, (value) =>
                onChange({ ...v, steps: v.steps.map((s, j) => (i === j ? value : s)) }),
              )}
            </div>
          ))}
        </>
      )}
      {v.inputType === 'ESSAY' && (
        <>
          {field('내 주장', v.essay.claim, (claim) =>
            onChange({ ...v, essay: { ...v.essay, claim } }),
          )}
          {v.essay.reasons.map((reason, i) => (
            <div key={i}>
              {field(`까닭 ${i + 1}`, reason, (value) =>
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
          {field('다른 의견에 답하기', v.essay.rebuttal, (rebuttal) =>
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
        <div className="ux-classification">
          {mission.choices?.map((c) => (
            <label className="cj-field" key={c.id}>
              {c.label}
              <select
                aria-label={c.label}
                value={v.assignments.find((a) => a.choiceId === c.id)?.categoryId ?? ''}
                onChange={(e) =>
                  onChange({
                    ...v,
                    assignments: [
                      ...v.assignments.filter((a) => a.choiceId !== c.id),
                      ...(e.target.value ? [{ choiceId: c.id, categoryId: e.target.value }] : []),
                    ],
                  })
                }
              >
                <option value="">그룹을 골라 주세요</option>
                {mission.categories?.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
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
}: {
  feedback: import('../../domain/classroom.ts').Feedback
  text: string
}) {
  const judgment = feedback.judgment
  if (!judgment) return null
  return (
    <div className="ux-evidence">
      <small>
        판정 ·{' '}
        {
          { CORRECT: '정답', PARTIAL: '부분 정답', RETHINK: '다시 생각', HELD: '판정 보류' }[
            judgment.result
          ]
        }
        {judgment.trial ? ' · AI 채점(시범)' : ''}
      </small>
      <ul>
        {judgment.elements?.map((e) => {
          const verified = isVerifiedElement(e, [text])
          return (
            <li key={e.elementId} data-evidence-verified={verified ? 'true' : 'false'}>
              <span>
                {verified ? '✓ 확인' : '아직 확인하지 못함'} · {e.label}
              </span>
              {verified && <blockquote>{e.quote}</blockquote>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
