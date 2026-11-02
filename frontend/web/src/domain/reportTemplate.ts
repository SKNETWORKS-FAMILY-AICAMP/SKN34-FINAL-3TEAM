export const sectionLabels = {
  thinkingTypes: '생각 유형', changes: '전후 변화', reflections: '돌아보기',
  quotes: '원문 인용', narrative: '요약', eveningQuestion: '저녁 질문',
} as const
export const metricLabels = {
  ATTEMPTS: '답변 제출 시도 수', COMPLETED: '완료한 시도 수', UNASSISTED: '도움 없이 시작한 비율',
} as const
export const toneLabels = { DEFAULT: '기본형', EASY: '쉬운 설명형', CONCISE: '간결형' } as const
export interface ReportTemplateSettings {
  sectionOrder: (keyof typeof sectionLabels)[]
  highlightMetrics: (keyof typeof metricLabels)[]
  tone: keyof typeof toneLabels
}
export interface ReportTemplateSnapshot { settings: ReportTemplateSettings; revision: number }
export type ReportTemplateProposal =
  | { proposalId: string; settings: ReportTemplateSettings; expiresAt: string; clarification?: never }
  | { clarification: string; proposalId?: never }

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('리포트 설정 응답을 확인하지 못했습니다.')
  return value as Record<string, unknown>
}
function settings(value: unknown): ReportTemplateSettings {
  const v = object(value)
  const order = v.sectionOrder, metrics = v.highlightMetrics
  if (Object.keys(v).sort().join(',') !== 'highlightMetrics,sectionOrder,tone' ||
      !Array.isArray(order) || order.length !== 6 || new Set(order).size !== 6 ||
      !order.every((key) => Object.hasOwn(sectionLabels, key)) ||
      !Array.isArray(metrics) || new Set(metrics).size !== metrics.length ||
      !metrics.every((key) => Object.hasOwn(metricLabels, key)) ||
      typeof v.tone !== 'string' || !Object.hasOwn(toneLabels, v.tone))
    throw new Error('허용되지 않은 리포트 설정 응답입니다.')
  return v as unknown as ReportTemplateSettings
}
export function templateSnapshot(value: unknown): ReportTemplateSnapshot {
  const v = object(value)
  if (!Number.isSafeInteger(v.revision) || (v.revision as number) < 0)
    throw new Error('리포트 설정 버전을 확인하지 못했습니다.')
  return { settings: settings(v.settings), revision: v.revision as number }
}
export function templateProposal(value: unknown): ReportTemplateProposal {
  const v = object(value)
  if (typeof v.clarification === 'string' && v.clarification.trim() && !v.proposalId && !v.settings)
    return { clarification: v.clarification }
  if (typeof v.proposalId !== 'string' || !v.proposalId || typeof v.expiresAt !== 'string' ||
      !Number.isFinite(Date.parse(v.expiresAt)) || v.clarification != null)
    throw new Error('리포트 변경안을 확인하지 못했습니다.')
  return { proposalId: v.proposalId, settings: settings(v.settings), expiresAt: v.expiresAt }
}
