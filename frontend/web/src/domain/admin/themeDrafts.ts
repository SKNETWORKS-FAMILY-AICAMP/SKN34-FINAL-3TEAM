import { inputLabels } from '../classroom.ts'
import type { InputType, ThinkingType } from '../classroom.ts'
import { THINKING_ORDER } from '../studentLook.ts'
import { THEME_GRADE_LABELS } from './retention.ts'
import type { ThemeGrade } from './retention.ts'
import { draftStatusLabels } from './missionStandards.ts'
import type { MissionDraftStatus } from './missionStandards.ts'

/**
 * 테마 초안 (api-spec 4.1 `/internal/admin/theme-drafts…`, learning OpenAPI `ThemeDraft`, #438·#439).
 * core는 learning 응답을 그대로 넘기므로 웹이 읽을 때 검사한다. draftId·status는 필수, 그 밖 칸은 없거나 모양이 다르면
 * 비운 값으로 두어 상세 일부가 깨져도 상태 확인·버리기는 할 수 있게 한다.
 */
export type ThemeDraftStatus = MissionDraftStatus
export const themeDraftLabels = draftStatusLabels
export const themeDraftSourceLabels = { AUTO: '주간 자동', ADMIN: '관리자 요청' } as const
export type ThemeDraftSource = keyof typeof themeDraftSourceLabels
export interface ThemeDraftRequest {
  grade: ThemeGrade
  weekStart: string
  topic?: string
  missions?: { thinkingType: ThinkingType; standardCodes: string[]; inputType: InputType }[]
}
export type ThemeSceneName = 'INTRO' | 'MON' | 'TUE' | 'WED' | 'THU' | 'FRI' | 'OUTRO'
export const THEME_SCENES: ThemeSceneName[] = ['INTRO', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'OUTRO']
export const sceneLabels: Record<ThemeSceneName, string> = {
  INTRO: '시작 이야기', MON: '월요일', TUE: '화요일', WED: '수요일', THU: '목요일', FRI: '금요일', OUTRO: '종료 이야기',
}
/** 실패 단계(ai THEME·MISSION·REVIEW·IMAGE, learning 검사 LEARNING, AI 호출 실패 AI_CALL) */
export const failureStageLabels: Record<string, string> = {
  THEME: '줄거리', MISSION: '요일 문제', REVIEW: '검토', IMAGE: '그림', VIDEO: '영상', LEARNING: '서비스 검사', AI_CALL: 'AI 호출',
}
export interface ThemeDraftScene { scene: ThemeSceneName; imageUrl: string | null; videoUrl: string | null; motion: unknown }
/**
 * 부분 다시 생성 대상 14개(#537, 사용자 결정 2026-11-17, learning ThemeDraftRules.REGEN_TARGETS·ai RegenTarget과 같은 값).
 * 같이 바뀌는 범위는 ai가 정한다: 시작·종료 그림은 컷 그림 4장과 영상까지, 요일 미션은 대화·그림까지
 */
export type RegenKind = 'VIDEO' | 'IMAGE' | 'MISSION'
export type RegenTarget = `${RegenKind}:${ThemeSceneName}`
export const REGEN_TARGETS: RegenTarget[] = [
  'VIDEO:INTRO', 'VIDEO:OUTRO', 'IMAGE:INTRO', 'IMAGE:OUTRO',
  'IMAGE:MON', 'IMAGE:TUE', 'IMAGE:WED', 'IMAGE:THU', 'IMAGE:FRI',
  'MISSION:MON', 'MISSION:TUE', 'MISSION:WED', 'MISSION:THU', 'MISSION:FRI',
]
/** 장면 칸마다 보이는 버튼 종류(시작·종료는 영상·그림, 요일은 그림·미션) */
export const regenKindsOf = (scene: ThemeSceneName): RegenKind[] => scene === 'INTRO' || scene === 'OUTRO' ? ['VIDEO', 'IMAGE'] : ['IMAGE', 'MISSION']
export const regenButtonLabels: Record<RegenKind, string> = { VIDEO: '영상 다시 생성', IMAGE: '그림 다시 생성', MISSION: '미션 다시 생성' }
const regenSceneNames: Record<ThemeSceneName, string> = { INTRO: '시작', OUTRO: '종료', MON: '월요일', TUE: '화요일', WED: '수요일', THU: '목요일', FRI: '금요일' }
const regenKindNames: Record<RegenKind, string> = { VIDEO: '영상', IMAGE: '그림', MISSION: '미션' }
const splitTarget = (target: RegenTarget) => target.split(':') as [RegenKind, ThemeSceneName]
/** "시작 영상"·"월요일 미션" */
export function regenTargetLabel(target: RegenTarget): string {
  const [kind, scene] = splitTarget(target)
  return `${regenSceneNames[scene]} ${regenKindNames[kind]}`
}
/** 확인 창 문구: 같이 바뀌는 범위를 말한다 */
export function regenConfirmText(target: RegenTarget): string {
  const [kind, scene] = splitTarget(target), name = regenSceneNames[scene]
  const scope = kind === 'VIDEO' ? `${name} 영상만 다시 만들까요? 그림·글은 그대로 둡니다.`
    : kind === 'IMAGE' && (scene === 'INTRO' || scene === 'OUTRO') ? `${name} 컷 그림 4장과 ${name} 영상을 다시 만들까요?`
    : kind === 'IMAGE' ? `${name} 그림만 다시 만들까요?`
    : `${name} 미션과 대화, 그림을 다시 만들까요? 다른 요일은 그대로 둡니다.`
  return `${scope} 새 초안으로 만들고 지금 초안은 그대로 남습니다.`
}
export interface ThemeDraftDay { day: ThemeSceneName; thinkingType: ThinkingType | null; place: string; clue: string; rulesOut: string[] }
export interface ThemeDraftMission { day: ThemeSceneName; thinkingType: ThinkingType | null; title: string; question: string; guide: string | null }
export interface ThemeDraftContent {
  theme: { title: string; intro: string; outro: string; bigQuestion: string; candidates: string[]; answer: string; days: ThemeDraftDay[] } | null
  missions: ThemeDraftMission[]
  dialogues: { day: ThemeSceneName; lines: { speaker: string; text: string }[] }[]
  warnings: { stage: string; item: string; reason: string }[]
}
export interface ThemeDraft {
  draftId: string
  status: ThemeDraftStatus
  source: ThemeDraftSource | null
  grade: ThemeGrade | null
  weekStart: string | null
  plannedWeek?: string | null
  weekLocked: boolean
  adoptionWeekLocked: boolean
  attempts: number
  maxAttempts: number
  input: {
    topic: string | null
    missions: { thinkingType: ThinkingType | null; inputType: InputType | null; standardCodes: string[] }[]
    /** 부분 다시 생성으로 만든 초안만(#537): 재료를 가진 원래 초안과 대상 */
    regenerate: { baseDraftId: string; targets: RegenTarget[] } | null
  }
  checkResults: { attempt: number; failures: { stage: string; reasons: string[] }[] }[]
  draft: ThemeDraftContent | null
  scenes: ThemeDraftScene[]
  failureCode: string | null
  versions: { prompt: string | null; model: string | null }
  themeId: string | null
  createdAt: string | null
  updatedAt: string | null
  /** 지금 다시 만들 수 있는 대상(#537). 없거나 모르는 값은 빈 배열·제외 */
  regenerableTargets: RegenTarget[]
}

const rec = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const arr = (v: unknown) => (Array.isArray(v) ? v : [])
const str = (v: unknown) => (typeof v === 'string' ? v : '')
const strOrNull = (v: unknown) => (typeof v === 'string' && v ? v : null)
const int = (v: unknown) => (Number.isInteger(v) && Number(v) >= 0 ? Number(v) : 0)
const scene = (v: unknown): ThemeSceneName | null => (THEME_SCENES as unknown[]).includes(v) ? (v as ThemeSceneName) : null
const thinking = (v: unknown): ThinkingType | null => (THINKING_ORDER as unknown[]).includes(v) ? (v as ThinkingType) : null
const regenTargets = (v: unknown): RegenTarget[] => [...new Set(arr(v).filter((t): t is RegenTarget => (REGEN_TARGETS as unknown[]).includes(t)))]

function content(raw: unknown): ThemeDraftContent | null {
  if (!raw || typeof raw !== 'object') return null
  const d = rec(raw), t = d.theme && typeof d.theme === 'object' ? rec(d.theme) : null
  return {
    theme: t ? {
      title: str(t.title), intro: str(t.intro), outro: str(t.outro), bigQuestion: str(t.bigQuestion),
      candidates: arr(t.candidates).filter((c): c is string => typeof c === 'string'), answer: str(t.answer),
      days: arr(t.days).flatMap((x) => {
        const v = rec(x), day = scene(v.day)
        return day ? [{ day, thinkingType: thinking(v.thinkingType), place: str(v.place), clue: str(v.clue),
          rulesOut: arr(v.rulesOut).filter((c): c is string => typeof c === 'string') }] : []
      }),
    } : null,
    missions: arr(d.missions).flatMap((x) => {
      const v = rec(x), day = scene(v.day), g = rec(v.draft)
      return day ? [{ day, thinkingType: thinking(v.thinkingType), title: str(g.title), question: str(g.question), guide: strOrNull(g.guide) }] : []
    }),
    dialogues: arr(d.dialogues).flatMap((x) => {
      const v = rec(x), day = scene(v.day)
      return day ? [{ day, lines: arr(v.lines).flatMap((l) => {
        const line = rec(l)
        return typeof line.speaker === 'string' && typeof line.text === 'string' ? [{ speaker: line.speaker, text: line.text }] : []
      }) }] : []
    }),
    warnings: arr(d.warnings).flatMap((x) => {
      const v = rec(x)
      return typeof v.reason === 'string' ? [{ stage: str(v.stage), item: str(v.item), reason: v.reason }] : []
    }),
  }
}

export function themeDraftOf(raw: unknown): ThemeDraft {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('테마 초안 응답을 확인하지 못했습니다.')
  const value = raw as Record<string, unknown>
  if (typeof value.draftId !== 'string' || !value.draftId || typeof value.status !== 'string' || !Object.hasOwn(themeDraftLabels, value.status))
    throw new Error('테마 초안 응답을 확인하지 못했습니다.')
  const input = rec(value.input), versions = rec(value.versions)
  return {
    draftId: value.draftId,
    status: value.status as ThemeDraftStatus,
    source: Object.hasOwn(themeDraftSourceLabels, str(value.source)) ? (value.source as ThemeDraftSource) : null,
    grade: Object.hasOwn(THEME_GRADE_LABELS, str(value.grade)) ? (value.grade as ThemeGrade) : null,
    weekStart: /^\d{4}-\d{2}-\d{2}$/.test(str(value.weekStart)) ? str(value.weekStart) : null,
    ...(Object.hasOwn(value, 'plannedWeek') ? { plannedWeek: strOrNull(value.plannedWeek) } : {}),
    weekLocked: value.weekLocked === true,
    adoptionWeekLocked: value.adoptionWeekLocked === true,
    attempts: int(value.attempts),
    maxAttempts: int(value.maxAttempts),
    input: {
      topic: strOrNull(input.topic),
      missions: arr(input.missions).map((x) => {
        const v = rec(x)
        return { thinkingType: thinking(v.thinkingType), inputType: Object.hasOwn(inputLabels, str(v.inputType)) ? (v.inputType as InputType) : null,
          standardCodes: arr(v.standardCodes).filter((c): c is string => typeof c === 'string') }
      }),
      regenerate: regenerateOf(input.regenerate),
    },
    checkResults: arr(value.checkResults).map((x) => {
      const v = rec(x)
      return { attempt: int(v.attempt), failures: arr(v.failures).map((f) => {
        const w = rec(f)
        return { stage: str(w.stage), reasons: arr(w.reasons).filter((r): r is string => typeof r === 'string') }
      }) }
    }),
    draft: content(value.draft),
    scenes: arr(value.scenes).flatMap((x) => {
      const v = rec(x), name = scene(v.scene)
      return name ? [{ scene: name, imageUrl: strOrNull(v.imageUrl), videoUrl: strOrNull(v.videoUrl), motion: v.motion ?? null }] : []
    }),
    failureCode: strOrNull(value.failureCode),
    versions: { prompt: strOrNull(versions.prompt), model: strOrNull(versions.model) },
    themeId: strOrNull(value.themeId),
    createdAt: strOrNull(value.createdAt),
    updatedAt: strOrNull(value.updatedAt),
    regenerableTargets: regenTargets(value.regenerableTargets),
  }
}

function regenerateOf(raw: unknown): ThemeDraft['input']['regenerate'] {
  const v = rec(raw), targets = regenTargets(v.targets)
  return typeof v.baseDraftId === 'string' && v.baseDraftId && targets.length ? { baseDraftId: v.baseDraftId, targets } : null
}

/** 상태별로 보이는 동작. 최종 판단은 서버(불가 전이 409 CONFLICT) */
export const themeDraftActions = (status: ThemeDraftStatus) => ({
  adopt: status === 'READY',
  discard: status === 'READY' || status === 'CHECK_FAILED' || status === 'FAILED',
  regenerate: status !== 'GENERATING' && status !== 'ADOPTED',
})
export function themeDraftRequestErrors(req: ThemeDraftRequest): string[] {
  const errors: string[] = []
  if (req.topic && req.topic.length > 100) errors.push('주제 키워드는 100자 이내로 입력해 주세요.')
  if (!Object.hasOwn(THEME_GRADE_LABELS, req.grade)) errors.push('학년을 선택해 주세요.')
  const date = new Date(req.weekStart + 'T00:00:00Z')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(req.weekStart) || !Number.isFinite(date.valueOf()) || date.toISOString().slice(0, 10) !== req.weekStart || date.getUTCDay() !== 1)
    errors.push('적용 주의 월요일을 선택해 주세요.')
  if (new Set(req.missions?.map(m => m.thinkingType)).size !== (req.missions?.length ?? 0)) errors.push('같은 생각 유형은 한 번만 지정해 주세요.')
  for (const m of req.missions ?? []) {
    if (!THINKING_ORDER.includes(m.thinkingType)) errors.push('생각 유형을 확인해 주세요.')
    if (!Object.hasOwn(inputLabels, m.inputType)) errors.push('입력 방식을 확인해 주세요.')
    if (!m.standardCodes.length || m.standardCodes.some(code => !code.trim() || code.includes('[') || code.includes(']') || /\s/.test(code))) errors.push('직접 지정한 유형은 성취기준 표에서 코드를 골라 주세요.')
    if ((req.grade === 'G3' || req.grade === 'G4') && m.inputType === 'ESSAY') errors.push('초3~4에는 논술을 지정할 수 없습니다.')
  }
  return [...new Set(errors)]
}
