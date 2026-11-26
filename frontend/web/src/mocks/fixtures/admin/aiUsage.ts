import type { Period } from '../../../domain/classroom.ts'
import type { UsageGroupBy, UsageItem } from '../../../domain/admin/operations.ts'

/**
 * 관리자 AI 사용량 목업(#1051). core `llm_usage` 행 모양만 흉내 낸 합성 기록이며
 * 프롬프트·응답 원문, 학생 ID, 업무 ID는 만들지 않는다(NFR-SEC-05).
 * 같은 날짜는 언제 만들어도 같은 기록이 나오도록 날짜로 씨앗을 정한다.
 */
interface UsageRow {
  callType: string
  model: string
  promptVersion: string | null
  latencyMs: number
  inputTokens: number | null
  outputTokens: number | null
  costUsd: number | null
  billedExternally: boolean
  success: boolean
  errorCode: string | null
  day: string
}
interface Profile {
  callType: string; model: string; promptVersion: string | null; perDay: number; base: number; spread: number
  input: number | null; output: number | null; price: [number, number] | 'external' | 'zero'; failEvery: number
}
// 단가는 core application.yml(#651)과 같은 100만 토큰당 USD
const profiles: Profile[] = [
  { callType: 'JUDGMENT', model: 'gpt-6-luna', promptVersion: 'judge@3', perDay: 18, base: 900, spread: 2600, input: 1800, output: 420, price: [0.1, 0.5], failEvery: 23 },
  { callType: 'FOLLOWUP', model: 'gpt-6-luna', promptVersion: 'followup@2', perDay: 10, base: 700, spread: 1800, input: 1200, output: 260, price: [0.1, 0.5], failEvery: 31 },
  { callType: 'ANALYSIS', model: 'gpt-6.1-terra', promptVersion: 'analysis@1', perDay: 6, base: 1800, spread: 5200, input: 2600, output: 900, price: [1, 5], failEvery: 17 },
  { callType: 'WORD_HELP', model: 'gpt-6-luna', promptVersion: 'word-help@1', perDay: 8, base: 500, spread: 900, input: 400, output: 120, price: [0.1, 0.5], failEvery: 0 },
  { callType: 'REPORT_EXPLANATION', model: 'gemma-4-26b-a4b-it-qat-awq-int4@local', promptVersion: 'report-explain@2', perDay: 3, base: 4200, spread: 9000, input: 3000, output: 700, price: 'external', failEvery: 11 },
  { callType: 'M2', model: 'm2-klue-essay@3.1-1112b', promptVersion: null, perDay: 14, base: 60, spread: 140, input: null, output: null, price: 'zero', failEvery: 0 },
]
const errorCodes = ['TIMEOUT', 'PROVIDER_ERROR', 'RATE_LIMITED']

function seeded(seed: string) {
  let h = 2166136261
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) ^ Math.imul(h ^ (h >>> 13), 3266489909)) >>> 0) / 4294967296
}
function days(period: Period) {
  const out: string[] = []
  for (let d = new Date(period.from + 'T00:00:00Z'); d <= new Date(period.to + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1))
    out.push(d.toISOString().slice(0, 10))
  return out
}
export function usageRows(period: Period): UsageRow[] {
  return days(period).flatMap(day => profiles.flatMap(p => {
    const random = seeded(day + p.callType)
    const count = p.perDay + Math.floor(random() * 5)
    return Array.from({ length: count }, (_, i) => {
      const failed = p.failEvery > 0 && random() * p.failEvery < 1
      // 지연은 오른쪽 꼬리가 긴 분포(제곱)로 만들어 p95가 평균보다 크게 벌어지게 한다
      const latencyMs = Math.round(p.base + p.spread * random() ** 2 + (failed ? p.spread : 0))
      const cost = p.price === 'zero' ? 0 : p.price === 'external' ? null
        : (p.price[0] * (p.input ?? 0) + p.price[1] * (p.output ?? 0)) / 1_000_000
      return {
        callType: p.callType, model: p.model, promptVersion: i % 9 === 8 && p.promptVersion ? p.promptVersion.replace(/@\d+$/, '@1') : p.promptVersion,
        latencyMs, inputTokens: p.input, outputTokens: p.output, costUsd: cost, billedExternally: p.price === 'external',
        success: !failed, errorCode: failed ? errorCodes[Math.floor(random() * errorCodes.length)] : null, day,
      }
    })
  }))
}

/** core `percentile_cont`와 같은 선형 보간 연속 백분위 */
export function percentile(sorted: number[], p: number) {
  const at = p * (sorted.length - 1), lo = Math.floor(at), hi = Math.ceil(at)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo)
}
const keyOf: Record<UsageGroupBy, (r: UsageRow) => string | null> = {
  CALL_TYPE: r => r.callType, MODEL: r => r.model, PROMPT_VERSION: r => r.promptVersion, ERROR_CODE: r => r.errorCode, DAY: r => r.day,
}
/** core `LlmUsageRepository.summarize`와 같은 규칙으로 묶는다: key 오름차순·null은 끝, 비용·토큰은 하나라도 비면 null */
export function summarizeUsage(rows: UsageRow[], groupBy: UsageGroupBy, callType: string | null): UsageItem[] {
  const groups = new Map<string | null, UsageRow[]>()
  for (const r of rows) {
    if (callType && r.callType !== callType) continue
    const k = keyOf[groupBy](r)
    groups.set(k, [...(groups.get(k) ?? []), r])
  }
  const sum = (xs: UsageRow[], f: (r: UsageRow) => number | null) => xs.some(r => f(r) == null) ? null : xs.reduce((s, r) => s + f(r)!, 0)
  return [...groups.entries()]
    .sort(([a], [b]) => a == null ? 1 : b == null ? -1 : a < b ? -1 : a > b ? 1 : 0)
    .map(([key, xs]) => {
      const latencies = xs.map(r => r.latencyMs).sort((a, b) => a - b)
      const unpriced = xs.filter(r => r.costUsd == null && !r.billedExternally).length
      return {
        key, callType: groupBy === 'CALL_TYPE' ? key : null,
        calls: xs.length, failures: xs.filter(r => !r.success).length,
        latencyMs: latencies.reduce((s, v) => s + v, 0) / xs.length,
        p50LatencyMs: percentile(latencies, 0.5), p95LatencyMs: percentile(latencies, 0.95),
        inputTokens: sum(xs, r => r.inputTokens), outputTokens: sum(xs, r => r.outputTokens),
        costUsd: unpriced ? null : Number(xs.reduce((s, r) => s + (r.costUsd ?? 0), 0).toFixed(6)),
        unpricedCalls: unpriced, externallyBilledCalls: xs.filter(r => r.billedExternally).length,
      }
    })
}
