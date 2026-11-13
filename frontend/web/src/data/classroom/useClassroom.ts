import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import type {
  AnswerContent,
  Attempt,
  Child,
  DemoScenario,
  Draft,
  Feedback,
  Period,
  Reflection,
  Report,
} from '../../domain/classroom.ts'
import { apiFetch, notifyAuthChange, setAccessToken, unlockParentSession } from '../apiClient.ts'
import { createApiGateway } from './apiGateway.ts'
import { getAttemptComparison, getThinkingActivities, saveReflection, saveSelfAssessment } from './learningApi.ts'
import { sharingApi } from './sharingApi.ts'
import { demoEmailLogin } from './demoLogin.ts'
import { calendarPeriods } from '../../domain/classroom.ts'
import { pollFeedback } from './feedbackPolling.ts'
// 목 여부와 무관하게 HTTP/SSE/Query 경로는 동일하다. MSW가 네트워크 경계만 가로챈다.
const gateway = createApiGateway()
let restoration: ReturnType<typeof gateway.restore> | undefined
export function restoreSession(fresh = false) {
  if (fresh) restoration = undefined
  if (!restoration) {
    const pending = gateway.restore().finally(() => {
      if (restoration === pending) restoration = undefined
    })
    restoration = pending
  }
  return restoration
}
export const isDemo = typeof import.meta.env !== 'undefined' && import.meta.env.DEV && import.meta.env.VITE_API_MOCK === 'true'
export const displayPeriods = calendarPeriods(
  isDemo ? new Date('2026-10-26T12:00:00+09:00') : new Date(),
)
export function setDemoScenario(value: DemoScenario) {
  if (isDemo) window.dispatchEvent(new CustomEvent('sagomungchi:mock-scenario', { detail: value }))
}
export function useAuthentication() {
  const cache = useQueryClient()
  const login = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) => {
      // 실제 모드는 Google 인증 링크로 로그인하므로 이메일 로그인이 없다 (#97)
      if (!isDemo) throw new Error('이메일 로그인은 개발 시연에서만 제공합니다.')
      return demoEmailLogin(email, password)
    },
    onSuccess: () => cache.clear(),
  })
  // #369: 등록된 관리자 ID·비밀번호 로그인. 실제·목업 모두 같은 경로이며, 권한·시작 화면은 /me로 다시 읽는다.
  const adminLogin = useMutation({
    mutationFn: async ({ loginId, password }: { loginId: string; password: string }) => {
      const raw = (await apiFetch<Record<string, unknown>>('/auth/admin/login', {
        method: 'POST',
        body: JSON.stringify({ loginId, password }),
      })) ?? {}
      if (raw.role !== 'ADMIN' || typeof raw.accessToken !== 'string') throw new Error('관리자 로그인 응답이 계약과 다릅니다.')
      setAccessToken(raw.accessToken, 'ADMIN')
      const next = await restoreSession(true)
      notifyAuthChange(next.role)
      return next
    },
    onSuccess: () => cache.clear(),
  })
  // #415: 학부모 ID·비밀번호 로그인·가입. 성공하면 관리자 로그인과 같이 /me로 세션·시작 화면을 다시 읽는다.
  const parentLogin = useMutation({
    mutationFn: ({ loginId, password }: { loginId: string; password: string }) => passwordSession('/auth/parent/login', { loginId, password }),
    onSuccess: () => cache.clear(),
  })
  const parentSignup = useMutation({
    mutationFn: (data: { loginId: string; password: string; name: string }) => passwordSession('/auth/parent/signup', data),
    onSuccess: () => cache.clear(),
  })
  const logout = useMutation({ mutationFn: () => gateway.logout(), onSettled: () => cache.clear() })
  const enter = useMutation({
    mutationFn: (child: Child) => gateway.enterStudent(child),
    onSuccess: () => cache.clear(),
  })
  // 학생 화면 → 학부모 화면: 보호자 비밀번호로 잠긴 학부모 세션을 풀고 /me로 세션을 다시 읽는다.
  const unlock = useMutation({
    mutationFn: async (password: string) => {
      await unlockParentSession(password)
      return restoreSession(true)
    },
    onSuccess: () => cache.clear(),
  })
  return { login, adminLogin, parentLogin, parentSignup, logout, enter, unlock }
}
async function passwordSession(path: '/auth/parent/login' | '/auth/parent/signup', body: Record<string, string>) {
  const raw = (await apiFetch<Record<string, unknown>>(path, { method: 'POST', body: JSON.stringify(body) })) ?? {}
  if (raw.role !== 'PARENT' || typeof raw.accessToken !== 'string') throw new Error('학부모 로그인 응답이 계약과 다릅니다.')
  setAccessToken(raw.accessToken, 'PARENT')
  const next = await restoreSession(true)
  notifyAuthChange(next.role)
  return next
}
export function useMockInvalidation() {
  const cache = useQueryClient()
  useEffect(() => {
    if (!isDemo) return
    const invalidate = () => {
      void cache.invalidateQueries({ queryKey: ['student-home'] })
      void cache.invalidateQueries({ queryKey: ['missions'] })
      void cache.invalidateQueries({ queryKey: ['records'] })
    }
    window.addEventListener('sagomungchi:mock-invalidate', invalidate)
    return () => window.removeEventListener('sagomungchi:mock-invalidate', invalidate)
  }, [cache])
}
export function useChildren(enabled: boolean) {
  return useQuery({
    queryKey: ['children'],
    queryFn: () => gateway.children(),
    enabled,
    retry: false,
  })
}
export function useMissions(child: Child | undefined) {
  return useQuery({
    queryKey: ['missions', child?.id, child?.grade],
    queryFn: () => gateway.missions(child!),
    enabled: !!child,
    retry: false,
  })
}
export function useStudentHome(child: Child | undefined) {
  return useQuery({
    queryKey: ['student-home', child?.id],
    queryFn: () => gateway.home(child!),
    enabled: !!child,
    retry: false,
  })
}
export function useMission(id: string, child: Child) {
  return useQuery({
    queryKey: ['mission', child.id, child.grade, id],
    queryFn: () => gateway.mission(id, child),
    retry: false,
  })
}
export function useRecords(child: Child | undefined, role: 'STUDENT' | 'PARENT', period: Period) {
  return useQuery({
    queryKey: ['records', role, child?.id, period.from, period.to],
    queryFn: () => gateway.records(child!, role, period),
    enabled: !!child,
    retry: false,
  })
}
/** 학생 생각 활동. 'records' 아래 키라 시도 시작·제출·마무리·돌아보기 뒤 함께 다시 읽힌다. */
export function useThinkingActivities(child: Child | undefined, period: Period) {
  return useQuery({
    queryKey: ['records', 'thinking-activities', child?.id, period.from, period.to],
    queryFn: ({ signal }) => getThinkingActivities(child!, period, signal),
    enabled: !!child,
    retry: false,
  })
}
export function useAttempt(id: string | null) {
  return useQuery({
    queryKey: ['attempt', id],
    queryFn: () => gateway.attempt(id!),
    enabled: !!id,
    retry: false,
  })
}
export function usePublicRecord(child: Child | undefined, id: string | null, period?: Period) {
  return useQuery({
    queryKey: ['public-record', child?.id, id, period],
    queryFn: () => gateway.record(child!, id!, period),
    enabled: !!child && !!id,
    retry: false,
  })
}
export function useLearningActions() {
  const cache = useQueryClient()
  const polling = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      polling.current?.abort()
    },
    [],
  )
  const update = (a: Attempt) => {
    cache.setQueryData(['attempt', a.attemptId], a)
    void cache.invalidateQueries({ queryKey: ['records'] })
    void cache.invalidateQueries({ queryKey: ['missions'] })
    void cache.invalidateQueries({ queryKey: ['student-home'] })
    // 학습 완료는 포인트·주간 테마 상태를 바꿀 수 있다(core 적립, P21).
    if (a.status === 'COMPLETED') {
      void cache.invalidateQueries({ queryKey: ['weekly-theme'] })
      void cache.invalidateQueries({ queryKey: ['points'] })
      void cache.invalidateQueries({ queryKey: ['community'] })
    }
  }
  const start = useMutation({
    mutationFn: ({
      mission,
      child,
      context,
    }: {
      mission: import('../../domain/classroom.ts').Mission
      child: Child
      context?: import('../../domain/retention.ts').AttemptContext
    }) => gateway.start(mission, child, context),
    onSuccess: (a: Attempt) => {
      update(a)
      void cache.invalidateQueries({ queryKey: ['weekly-theme'] })
    },
  })
  const save = useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: Draft }) => gateway.saveDraft(id, draft),
    onSuccess: (draft, { id }) =>
      cache.setQueryData<Attempt>(['attempt', id], (a) => (a ? { ...a, draft } : a)),
  })
  const hint = useMutation({ mutationFn: (id: string) => gateway.hint(id) })
  const submit = useMutation({
    mutationFn: ({
      id,
      answer,
      key,
      followupId,
    }: {
      id: string
      answer: AnswerContent
      key: string
      followupId?: string
    }) => gateway.submit(id, answer, key, followupId),
    onSuccess: update,
  })
  const feedback = useMutation({
    mutationFn: ({ attempt, answerId }: { attempt: Attempt; answerId: string }) => {
      polling.current?.abort()
      const controller = new AbortController()
      polling.current = controller
      return pollFeedback(
        gateway,
        attempt.attemptId,
        answerId,
        (f: Feedback) =>
          cache.setQueryData<Attempt>(['attempt', attempt.attemptId], (previous) =>
            previous
              ? {
                  ...previous,
                  answers: previous.answers.map((a) =>
                    a.answerId === answerId ? { ...a, feedback: f } : a,
                  ),
                }
              : previous,
          ),
        controller.signal,
      )
    },
    onSuccess: (f, { attempt, answerId }) => {
      cache.setQueryData<Attempt>(['attempt', attempt.attemptId], (previous) =>
        previous
          ? {
              ...previous,
              answers: previous.answers.map((a) =>
                a.answerId === answerId ? { ...a, feedback: f } : a,
              ),
            }
          : previous,
      )
      void cache.invalidateQueries({ queryKey: ['records'] })
    },
    onError: () => {
      void cache.invalidateQueries({ queryKey: ['attempt'] })
      void cache.invalidateQueries({ queryKey: ['records'] })
    },
  })
  const finish = useMutation({ mutationFn: (id: string) => gateway.finish(id), onSuccess: update })
  const reflect = useMutation({
    mutationFn: ({ id, reflection }: { id: string; reflection: Reflection }) =>
      saveReflection(id, reflection).then(() => gateway.attempt(id)),
    onSuccess: update,
  })
  return { start, save, hint, submit, feedback, finish, reflect }
}
export function useReport(child: Child | undefined, period: Period, revision?: number) {
  return useQuery({
    queryKey: ['report', child?.id, period.from, period.to, revision ?? 'latest'],
    queryFn: () => gateway.report(child!, period, revision),
    enabled: !!child,
    retry: false,
  })
}
export function useParentActions() {
  const cache = useQueryClient()
  const regenerate = useMutation({
    mutationFn: (report: Report) => gateway.regenerate(report),
    onSuccess: (report) => {
      cache.setQueryData(
        ['report', report.childId, report.period.from, report.period.to, 'latest'],
        report,
      )
    },
  })
  const analyze = useMutation({
    mutationFn: ({ child, period, question }: { child: Child; period: Period; question: string }) =>
      gateway.analyze(child, period, question),
  })
  return { regenerate, analyze }
}

/** 마무리한 시도의 이전·이번 답 비교(학생). 마무리 전에는 묻지 않는다. */
export function useAttemptComparison(attempt: Attempt) {
  return useQuery({ queryKey: ['attempt-comparison', attempt.attemptId], enabled: !!attempt.finishedAt,
    retry: false, queryFn: ({ signal }) => getAttemptComparison(attempt.attemptId, signal) })
}
/** 학생 자기 점검 저장. 저장 뒤 서버 값으로 화면을 맞추는 일은 onSaved가 한다. */
export function useSaveSelfAssessment(attemptId: string, onSaved: (rows: Awaited<ReturnType<typeof saveSelfAssessment>>) => void) {
  return useMutation({
    mutationFn: (checks: { elementId: string; checked: boolean }[]) => saveSelfAssessment(attemptId, checks),
    onSuccess: onSaved,
  })
}
/** 학생 본인의 답 공개 설정 조회·저장. 바꾸면 공유 브라우저에 남은 학부모 원문 캐시를 지운다. */
export function useStudentSharing(childId: string) {
  const cache = useQueryClient()
  const key = ['sharing-preferences', 'STUDENT', childId]
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => sharingApi.get(childId, 'STUDENT', signal), retry: false })
  const save = useMutation({ mutationFn: (enabled: boolean) => sharingApi.save(childId, enabled),
    onSuccess: value => {
      cache.setQueryData(key, value)
      // Shared-browser caches must not retain parent originals after a change.
      cache.removeQueries({ predicate: q => ['parent', 'records', 'report', 'public-record'].includes(String(q.queryKey[0])) })
    } })
  return { query, save }
}
