import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Conversation, MessageResult, Scope, StreamState } from '../../domain/parent.ts'
import { parentApi } from './api.ts'
import { sharingApi } from '../classroom/sharingApi.ts'
import { guardianTransfers } from '../guardianTransfers.ts'
import { serviceApi } from '../serviceApi.ts'
export function useParentQuery<T>(
  key: unknown[],
  fn: (signal: AbortSignal) => Promise<T>,
  enabled = true,
  poll = false,
) {
  return useQuery({
    queryKey: ['parent', ...key],
    queryFn: ({ signal }) => fn(signal),
    enabled,
    retry: false,
    refetchInterval: (query) =>
      poll &&
      ['RUNNING', 'QUEUED'].includes(
        String((query.state.data as { status?: string } | undefined)?.status),
      )
        ? 1200
        : false,
  })
}
export function useParentMutation<T, V>(fn: (v: V) => Promise<T>) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ['parent'] })
      void cache.invalidateQueries({ queryKey: ['children'] })
    },
  })
}
export function useParentDashboard(scope: Scope, page = 0, recordsEnabled = true) {
  return {
    summary: useParentQuery(['summary', scope], (signal) => parentApi.summary(scope, signal)),
    thinking: useParentQuery(['thinking', scope], (signal) => parentApi.thinking(scope, signal)),
    records: useParentQuery(['records', scope, page], (signal) => parentApi.records(scope, signal, page), recordsEnabled),
  }
}

/** 학생이 정한 답 공개 상태(학부모 화면 안내). 학생이 바꿀 수 있어 볼 때마다 다시 묻는다. */
export function useParentSharingNotice(studentId: string) {
  return useQuery({ queryKey: ['parent', 'sharing-preferences', studentId],
    queryFn: ({ signal }) => sharingApi.get(studentId, 'PARENT', signal), retry: false,
    staleTime: 0, refetchOnWindowFocus: 'always' })
}
/** 보호자 이관 요청 목록. 상대가 수락·거절할 수 있어 5초마다 다시 묻는다. */
export function useGuardianTransferList() {
  return useQuery({ queryKey: ['parent', 'guardian-transfers'], queryFn: ({ signal }) => guardianTransfers.list(signal), refetchInterval: 5000, retry: false })
}
/** 회원 탈퇴 확정. 성공 뒤 토큰을 지우므로 학부모 캐시를 다시 부르지 않는다. */
export function useWithdraw(token: string) {
  return useMutation({ mutationFn: () => serviceApi.withdraw(token) })
}

/**
 * 화면 하나에서 한 번에 하나만 진행하는 요청. 새 요청·abort·화면 이탈 때 이전 요청을 취소하고,
 * 취소된 요청의 결과와 오류는 버린다(undefined로 끝난다). 반환하는 동작은 렌더 사이에 같은 값이다.
 */
function useLatestRequest() {
  const current = useRef<AbortController | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => () => { current.current?.abort() }, [])
  const control = useMemo(() => ({
    abort() { current.current?.abort(); current.current = null; setBusy(false) },
    active: () => current.current !== null,
    async run<T>(send: (signal: AbortSignal) => Promise<T>): Promise<T | undefined> {
      current.current?.abort()
      const abort = new AbortController()
      current.current = abort
      setBusy(true)
      try {
        const value = await send(abort.signal)
        return abort.signal.aborted ? undefined : value
      } catch (e) {
        if (abort.signal.aborted) return undefined
        throw e
      } finally {
        if (current.current === abort) { current.current = null; setBusy(false) }
      }
    },
  }), [])
  return { control, busy }
}

/** 대화를 만들 대상. 일일 리포트에서 시작하면 그 리포트의 자녀·날짜·최신 판으로 고정한다(FN-RPT-16). */
export interface ConversationTarget { childId: string; scope: Scope; dailyReportId?: string }
const createConversation = (t: ConversationTarget) =>
  t.dailyReportId ? parentApi.createForReport(t.childId, t.dailyReportId) : parentApi.create(t.scope)

/**
 * 분석 대화 요청 흐름(대화 생성·SSE 질문·취소·캐시 갱신). 화면은 입력과 표시만 맡는다.
 * 새 질문·설정 대화 시작은 진행 중인 요청을 취소한다. 취소되면 undefined로 끝나고 화면 상태를 건드리지 않는다.
 */
export function useConversationRequests() {
  const cache = useQueryClient(), { control } = useLatestRequest()
  return useMemo(() => {
    const refresh = (...keys: string[]) => { for (const key of keys) void cache.invalidateQueries({ queryKey: ['parent', key] }) }
    return {
      abort: control.abort,
      /** 대화가 없으면 만들고(onCreated) 질문을 보낸다. 스트림 상태는 onState로 넘긴다. */
      ask: (o: { conversationId: string | null; target: ConversationTarget; text: string; scope: Scope; retryId?: string
        onCreated: (c: Conversation) => void; onState: (s: StreamState) => void }) =>
        control.run(async signal => {
          try {
            let conversationId = o.conversationId
            if (!conversationId) {
              const c = await createConversation(o.target)
              if (signal.aborted) return undefined
              conversationId = c.conversationId
              o.onCreated(c)
            }
            let result: MessageResult | undefined
            await parentApi.message(conversationId, o.text, o.scope, s => {
              if (s.phase === 'DONE') result = s.result
              if (!signal.aborted) o.onState(s)
            }, signal, o.retryId)
            if (signal.aborted) return undefined
            refresh('conversation', 'conversations')
            return { conversationId, result }
          } catch (e) {
            if (!signal.aborted) refresh('conversation')
            throw e
          }
        }),
      /** 질문 없이 대화만 만든다(리포트 표시 설정 대화). */
      start: (target: ConversationTarget) =>
        control.run(async signal => {
          const c = await createConversation(target)
          if (!signal.aborted) refresh('conversations')
          return c
        }),
    }
  }, [cache, control])
}

/** 답변이 가리키는 현재 근거 위치 조회. 새로 고르거나 지우면 이전 조회를 취소한다. */
export function useMessageEvidence() {
  const { control, busy } = useLatestRequest()
  const actions = useMemo(() => ({
    abort: control.abort,
    load: (conversationId: string, messageId: string, hasEvidence: boolean) =>
      control.run(signal => hasEvidence ? parentApi.messageEvidence(conversationId, messageId, signal) : Promise.resolve({ items: [] })),
  }), [control])
  return { ...actions, busy }
}

/** 리포트 표시 설정: 현재 설정 조회, 변경안 요청, 확정. 진행 중에는 새 요청을 받지 않는다. */
export function useReportTemplateEditing(conversationId: string) {
  const cache = useQueryClient(), { control, busy } = useLatestRequest()
  const current = useParentQuery(['report-template', conversationId], (signal) => parentApi.reportTemplate(conversationId, signal))
  const actions = useMemo(() => ({
    active: control.active,
    propose: (question: string) => control.run(signal => parentApi.proposeReportTemplate(conversationId, question, signal)),
    confirm: (proposalId: string) => control.run(async signal => {
      const result = await parentApi.confirmReportTemplate(conversationId, proposalId, signal)
      if (!signal.aborted) {
        cache.setQueryData(['parent', 'report-template', conversationId], result)
        void cache.invalidateQueries({ queryKey: ['parent', 'report-template'] })
      }
      return result
    }),
  }), [cache, control, conversationId])
  return { current, busy, ...actions }
}
