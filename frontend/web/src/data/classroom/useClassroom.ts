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
import { createApiGateway } from './apiGateway.ts'
import { calendarPeriods } from '../../domain/classroom.ts'
import { pollFeedback } from './feedbackPolling.ts'
// 목 여부와 무관하게 HTTP/SSE/Query 경로는 동일하다. MSW가 네트워크 경계만 가로챈다.
const gateway = createApiGateway()
let restoration: ReturnType<typeof gateway.restore> | undefined
export function restoreSession(fresh = false) {
  if (fresh) restoration = undefined
  return (restoration ??= gateway.restore().catch((error) => {
    throw error
  }))
}
export const isDemo = import.meta.env.DEV && import.meta.env.VITE_API_MOCK === 'true'
export const displayPeriods = calendarPeriods(
  isDemo ? new Date('2026-10-26T12:00:00+09:00') : new Date(),
)
export function setDemoScenario(value: DemoScenario) {
  if (isDemo) window.dispatchEvent(new CustomEvent('sagomungchi:mock-scenario', { detail: value }))
}
export function useAuthentication() {
  const cache = useQueryClient()
  const login = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      gateway.login(email, password),
    onSuccess: () => cache.clear(),
  })
  const logout = useMutation({ mutationFn: () => gateway.logout(), onSettled: () => cache.clear() })
  const enter = useMutation({
    mutationFn: (child: Child) => gateway.enterStudent(child),
    onSuccess: () => cache.clear(),
  })
  return { login, logout, enter }
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
export function useAttempt(id: string | null) {
  return useQuery({
    queryKey: ['attempt', id],
    queryFn: () => gateway.attempt(id!),
    enabled: !!id,
    retry: false,
  })
}
export function usePublicRecord(child: Child | undefined, id: string | null) {
  return useQuery({
    queryKey: ['public-record', child?.id, id],
    queryFn: () => gateway.record(child!, id!),
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
  }
  const start = useMutation({
    mutationFn: ({
      mission,
      child,
    }: {
      mission: import('../../domain/classroom.ts').Mission
      child: Child
    }) => gateway.start(mission, child),
    onSuccess: update,
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
      gateway.reflect(id, reflection),
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
