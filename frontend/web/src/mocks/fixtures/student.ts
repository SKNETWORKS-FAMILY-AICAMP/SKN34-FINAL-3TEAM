import { createDemoGateway } from '../../data/classroom/demoGateway.ts'
import { blankAnswer } from '../../domain/classroom.ts'
import type { AnswerContent, Attempt, Draft, Mission } from '../../domain/classroom.ts'

// 기존 가상 학생/자체 문항 저장소를 MSW 안에서만 재사용한다. 앱 데이터 경로에 주입하지 않는다.
export const fixtureStore = createDemoGateway()
export const mockSubmissionReceipts = new Map<
  string,
  {
    signature: string
    response: {
      answerId: string
      attemptId: string
      version: number
      followupId?: string
      submittedAt: string
      feedback: { status: 'PENDING' }
    }
  }
>()
const fixtureKey = 'sagomungchi:msw-fixture:v1'
if (typeof sessionStorage !== 'undefined') {
  try {
    const raw = sessionStorage.getItem(fixtureKey)
    if (raw) {
      const data = JSON.parse(raw)
      if (
        Array.isArray(data.attempts) &&
        Array.isArray(data.keys) &&
        Array.isArray(data.reports) &&
        Number.isInteger(data.serial)
      ) {
        fixtureStore.restoreSnapshot(data)
        if (Array.isArray(data.requests))
          for (const [k, v] of data.requests) mockSubmissionReceipts.set(k, v)
      }
    }
  } catch {
    /* 손상된 개발 fixture는 읽지 않습니다. */
  }
}
export function persistFixtureState() {
  if (typeof sessionStorage !== 'undefined') {
    try {
      sessionStorage.setItem(
        fixtureKey,
        JSON.stringify({
          ...fixtureStore.snapshot(),
          requests: [...mockSubmissionReceipts.entries()],
        }),
      )
    } catch {
      /* 저장소 차단 시 새로고침 복원만 제한됩니다. */
    }
  }
}
export function wireDraft(d: Draft) {
  return {
    version: Number(d.version.replaceAll('"', '')),
    content: { answer: d.answer, memo: d.memo },
    savedAt: d.savedAt,
  }
}
export function wireAttempt(a: Attempt) {
  const { draft, reveal, revealKind, checklist, ...data } = a
  return {
    ...data,
    ...(draft ? { draft: wireDraft(draft) } : {}),
    ...(a.finishedAt && reveal ? { reveal, revealKind, checklist } : {}),
  }
}
export function normalizeAnswer(raw: Record<string, unknown>, mission?: Mission): AnswerContent {
  const inputType = (raw.inputType ?? mission?.inputType) as AnswerContent['inputType']
  const blank = blankAnswer(inputType)
  const fields = [
    'text',
    'finalAnswer',
    'steps',
    'essay',
    'choiceIds',
    'assignments',
    'dictatedByGuardian',
  ] as const
  for (const field of fields)
    if (raw[field] !== undefined) Object.assign(blank, { [field]: raw[field] })
  return blank
}
