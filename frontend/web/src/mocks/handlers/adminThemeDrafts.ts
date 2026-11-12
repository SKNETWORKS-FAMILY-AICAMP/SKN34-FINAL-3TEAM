import { http } from 'msw/http'
import type { AdminMission } from '../../domain/admin/operations.ts'
import type { ThinkingType } from '../../domain/classroom.ts'
import { themeDraftRequestErrors, THEME_SCENES } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraftRequest, ThemeDraftStatus, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { THEME_DAYS } from '../../domain/retention.ts'
import { achievementStandards, audit, missions, stamp } from '../fixtures/admin/operations.ts'
import { persistRetention, retentionState } from '../fixtures/retention.ts'
import { allow } from './admin.ts'
import { fail } from './parent.ts'
import { respond } from './student.ts'

/**
 * 관리자 테마 초안 목업(#441, api-spec 2.8·4.1 `ThemeDraft`). learning #438 생성 작업을 화면 확인에 필요한 만큼만 흉내 낸다.
 * - 요청 3초 뒤 조회에서 결과가 생김. 주제에 '실패'가 있으면 CHECK_FAILED(검사 실패 사유·초안 함께)
 * - 그림은 가상 SVG data URL, 영상 없음(움직임은 그림 위 카메라·문구·살펴보기 지점으로 확인)
 * - 채택: 미션 5개 DRAFT(source LLM_THEME)·테마 DRAFT. 게시는 미션·테마를 각각
 */
interface MockThemeDraft {
  draftId: string
  status: ThemeDraftStatus
  source: 'AUTO' | 'ADMIN'
  grade: ThemeDraftRequest['grade']
  weekStart: string
  attempts: number
  maxAttempts: number
  input: { topic: string | null; missions: { thinkingType: ThinkingType; inputType: string; standardCodes: string[] }[] }
  checkResults: { attempt: number; failures: { stage: string; reasons: string[] }[] }[]
  draft: Record<string, unknown> | null
  scenes: { scene: ThemeSceneName; imageUrl: string | null; videoUrl: string | null; motion: unknown }[]
  failureCode: string | null
  versions: { prompt: string | null; model: string | null }
  themeId: string | null
  requestedBy: string | null
  createdAt: string
  updatedAt: string
}
// 새로고침해도 유지되도록 sessionStorage에 가상 값만 둔다(다른 목업과 같은 방식)
const storageKey = 'sagomungchi:msw-theme-drafts:v1'
const drafts: MockThemeDraft[] = (() => {
  try {
    const raw = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(storageKey)
    return raw ? (JSON.parse(raw) as MockThemeDraft[]) : []
  } catch {
    return []
  }
})()
function persist() {
  try {
    if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(storageKey, JSON.stringify(drafts))
  } catch {
    /* 저장소를 못 쓰면 메모리 값만 유지 */
  }
}
const learningFail = (status = 400, code = 'VALIDATION_FAILED'): never => fail(code, '학습 서비스가 관리자 요청을 처리하지 못했습니다.', status)

const HUES: Record<ThemeSceneName, string> = { INTRO: '#7FC8D8', MON: '#9CCB8C', TUE: '#E9B949', WED: '#F2B8A0', THU: '#B8C2CC', FRI: '#C9A7E8', OUTRO: '#F4D88A' }
/** 가상 장면 그림(외부 호출 없음) */
const sceneSvg = (scene: ThemeSceneName, title: string) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360"><rect width="640" height="360" fill="#C6EAE1"/>` +
  `<circle cx="520" cy="80" r="40" fill="#F2C14E"/><path d="M0 360 L160 170 L280 260 L420 140 L640 360Z" fill="${HUES[scene]}" stroke="#1F2421" stroke-width="5"/>` +
  `<circle cx="250" cy="250" r="34" fill="#FFFDF7" stroke="#1F2421" stroke-width="5"/><text x="24" y="44" font-size="28" font-family="sans-serif" fill="#1F2421">${scene} · ${title}</text></svg>`)
const motionOf = (scene: ThemeSceneName) => ({
  version: 1,
  transition: { kind: 'fade', seconds: 0.5 },
  camera: { from: { x: 50, y: 50, zoom: 1 }, to: { x: 40, y: 60, zoom: 1.3 }, seconds: 6 },
  speakers: { 뭉치: { x: 39, y: 69, zoom: 1.2 } },
  effects: scene === 'OUTRO' ? [{ shape: 'circle', color: '#FFF3C4', count: 12, size: 6, direction: 'up', speed: 1, opacity: 0.8 }] : [],
  captions: scene === 'INTRO' || scene === 'OUTRO'
    ? [{ start: 0, end: 3, text: scene === 'INTRO' ? '뭉치가 마을 광장에 도착했어요.' : '마지막 단서가 맞춰졌어요!' }, { start: 3, end: 6, text: '함께 살펴볼까요?' }]
    : [],
  spots: scene === 'INTRO' || scene === 'OUTRO' ? [] : [
    { x: 25, y: 70, label: '발자국', line: '어디로 이어질까?', evidence: true },
    { x: 70, y: 40, label: '깃발', line: '바람이 부는 쪽', evidence: false },
  ],
})
const STANDARD_BY_BAND: Record<'G3_4' | 'G5_6', string> = { G3_4: '4과03-01', G5_6: '6국01-02' }
const DEFAULT_INPUT: Record<ThinkingType, string> = { ANALYZE: 'NARRATIVE', EVALUATE: 'CHOICE', CREATE: 'NARRATIVE', SOLVE: 'ORDERING', REFLECT: 'NARRATIVE' }

function filledInput(body: ThemeDraftRequest): MockThemeDraft['input'] {
  const grade = Number(body.grade.slice(1)), code = STANDARD_BY_BAND[grade <= 4 ? 'G3_4' : 'G5_6']
  return {
    topic: body.topic?.trim() || '뭉치 역할: 탐정 / 장소: 마을 광장 / 찾는 대상: 사라진 종',
    missions: THINKING_ORDER.map((thinkingType) => body.missions?.find((m) => m.thinkingType === thinkingType)
      ?? { thinkingType, inputType: DEFAULT_INPUT[thinkingType], standardCodes: [code] }),
  }
}
function result(d: MockThemeDraft) {
  const title = '사라진 종을 찾아라', failing = d.input.topic?.includes('실패')
  const candidates = ['시계탑', '분수대', '빵집', '도서관']
  d.draft = {
    theme: {
      title, world: '목업 마을', characters: [{ name: '뭉치', look: '솜뭉치' }], styleNote: '2D 만화풍', outfit: '탐정 모자',
      intro: '마을 광장의 종이 사라졌어요. 뭉치는 한 주 동안 단서를 모아 종이 어디 있는지 찾기로 했어요.',
      outro: '종은 시계탑 꼭대기에 숨어 있었어요. 모두가 모은 단서 덕분이에요.',
      bigQuestion: '사라진 종은 어디에 있을까?', candidates, answer: '시계탑',
      days: THEME_DAYS.map((day, i) => ({ day, thinkingType: THINKING_ORDER[i], place: `${i + 1}번째 장소`, sceneNote: '목업',
        clue: i < 3 ? `${candidates[i + 1]}에는 종소리가 나지 않았어요.` : '높은 곳에서 소리가 들렸어요.', rulesOut: i < 3 ? [candidates[i + 1]] : [] })),
    },
    missions: d.input.missions.map((m, i) => ({ day: THEME_DAYS[i], thinkingType: m.thinkingType, draft: {
      title: `${title} ${i + 1}일째`, question: `${['단서를 나누어', '두 주장을 따져', '새 방법을 만들어', '순서를 정해', '이번 주를 돌아보며'][i]} 생각을 말해 보세요.`,
      guide: '장면을 먼저 살펴보세요.', sceneNote: null, choices: null, categories: null, answerKey: null, exampleAnswer: null,
      forbiddenTerms: ['시계탑'], hints: ['무엇을 보았나요?'], elements: [] } })),
    dialogues: THEME_DAYS.map((day) => ({ day, lines: [{ speaker: '뭉치', text: '여기 뭔가 있어!' }, { speaker: '토리', text: '같이 살펴보자.' }] })),
    warnings: [{ stage: 'VIDEO', item: 'ALL', reason: '목업이라 영상을 만들지 않았어요.' }],
  }
  d.scenes = THEME_SCENES.map((scene) => ({ scene, imageUrl: sceneSvg(scene, title), videoUrl: null, motion: motionOf(scene) }))
  d.attempts += 1
  d.versions = { prompt: 'theme-draft-mock-1', model: 'mock-model' }
  if (failing) {
    d.status = 'CHECK_FAILED'
    d.checkResults.push({ attempt: d.attempts, failures: [{ stage: 'LEARNING', reasons: ['WED QUESTION_LENGTH 질문이 너무 깁니다.'] }] })
  } else d.status = 'READY'
  d.updatedAt = stamp()
}
/** 요청 3초 뒤 처음 조회할 때 결과가 생김(화면의 5초 주기 조회로 바뀌는 것까지 확인) */
const GENERATE_MS = 3_000
function advance(d: MockThemeDraft) {
  if (d.status !== 'GENERATING') return d
  if (Date.now() - Date.parse(d.createdAt) >= GENERATE_MS) result(d)
  return d
}
function byId(id: string) {
  const d = drafts.find((x) => x.draftId === id)
  if (!d) learningFail(404, 'NOT_FOUND')
  return d!
}
function create(body: ThemeDraftRequest, source: 'AUTO' | 'ADMIN'): MockThemeDraft {
  const d: MockThemeDraft = {
    draftId: crypto.randomUUID(), status: 'GENERATING', source, grade: body.grade, weekStart: body.weekStart, attempts: 0, maxAttempts: 3,
    input: filledInput(body), checkResults: [], draft: null, scenes: [], failureCode: null, versions: { prompt: null, model: null },
    themeId: null, requestedBy: source === 'ADMIN' ? 'mock-admin' : null, createdAt: stamp(), updatedAt: stamp(),
  }
  drafts.unshift(d)
  return d
}
// 처음부터 하나는 주간 자동 결과가 있게 둔다
if (!drafts.length) {
  const seed = create({ grade: 'G4', weekStart: (() => { const t = new Date(); t.setUTCDate(t.getUTCDate() + ((8 - t.getUTCDay()) % 7 || 7)); return t.toISOString().slice(0, 10) })() }, 'AUTO')
  result(seed)
  persist()
}

function adopt(d: MockThemeDraft) {
  const g = d.draft as { theme: { title: string; intro: string; outro: string }; missions: { thinkingType: ThinkingType; draft: { title: string; question: string; guide: string } }[] }
  const grade = Number(d.grade.slice(1)), subjectOf = (code: string) => achievementStandards.find((s) => s.code === code)?.subject ?? ''
  const ids = d.input.missions.map((input, i) => {
    const m: AdminMission = {
      missionId: crypto.randomUUID(), code: `MOCK-THEME-${missions.length + 1}`, source: 'LLM_THEME', status: 'DRAFT', demoOnly: false,
      currentVersion: 1, currentRubricVersion: 1, publishedVersion: null, publishedRubricVersion: null,
      versions: [{ version: 1, title: g.missions[i].draft.title, subject: subjectOf(input.standardCodes[0]), gradeMin: grade, gradeMax: grade,
        thinkingType: input.thinkingType, inputType: input.inputType as AdminMission['versions'][number]['inputType'],
        question: g.missions[i].draft.question, guide: g.missions[i].draft.guide, answerUnit: null, inputTemplate: [],
        sceneUri: d.scenes.find((s) => s.scene === THEME_DAYS[i])?.imageUrl ?? null, staticSceneUri: null,
        achievementStandards: input.standardCodes, achievementLevels: null, choices: [], categories: [], createdAt: stamp() }],
      rubrics: [{ version: 1, elements: [{ code: 'e1', label: '생각 근거', description: '장면에서 찾은 근거를 말함', points: 1, commonErrors: [],
        goodThought: true, judgeVerified: false, standardCode: input.standardCodes[0] }], answerKey: null, exampleAnswer: null,
        forbiddenTerms: ['시계탑'], hints: ['무엇을 보았나요?'], keywords: [], essayType: null }],
      reviews: [],
    }
    missions.push(m)
    return m.missionId
  })
  const scene = (name: ThemeSceneName) => d.scenes.find((s) => s.scene === name)
  const theme = {
    themeId: `theme-${crypto.randomUUID().slice(0, 8)}`, grade: d.grade, weekStart: d.weekStart, title: g.theme.title, intro: g.theme.intro,
    days: THEME_DAYS.map((day, i) => ({ day, missionId: ids[i] })), status: 'DRAFT' as const, updatedAt: stamp(),
    outro: g.theme.outro, introImageUrl: scene('INTRO')?.imageUrl ?? null, outroImageUrl: scene('OUTRO')?.imageUrl ?? null,
    introVideoUrl: null, outroVideoUrl: null, introMotion: scene('INTRO')?.motion ?? null, outroMotion: scene('OUTRO')?.motion ?? null,
  }
  retentionState.themes.unshift(theme)
  persistRetention()
  Object.assign(d, { status: 'ADOPTED', themeId: theme.themeId, updatedAt: stamp() })
  return theme
}

export const adminThemeDraftHandlers = [
  http.post('/api/v1/admin/theme-drafts', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const body = (await request.json()) as ThemeDraftRequest
      if (themeDraftRequestErrors(body).length || (body.topic && body.topic.length > 100)) learningFail()
      const d = create(body, 'ADMIN')
      audit('THEME_DRAFT_REQUEST', 'THEME_DRAFT', d.draftId, 'SUCCESS', '테마 초안 생성 요청')
      persist()
      return d
    }, 202),
  ),
  http.get('/api/v1/admin/theme-drafts', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const q = new URL(request.url).searchParams
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20), status = q.get('status'), source = q.get('source')
      if (!Number.isInteger(index) || index < 0 || !Number.isInteger(size) || size < 1 || size > 100) learningFail()
      const rows = drafts.map(advance).filter((d) => (!status || d.status === status) && (!source || d.source === source))
      persist()
      return { items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length }
    }),
  ),
  http.get('/api/v1/admin/theme-drafts/:draftId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = advance(byId(String(params.draftId)))
      persist()
      return d
    }),
  ),
  http.post('/api/v1/admin/theme-drafts/:draftId/adopt', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = byId(String(params.draftId))
      if (d.status !== 'READY' || !d.draft) learningFail(409, 'CONFLICT')
      const theme = adopt(d)
      audit('THEME_DRAFT_ADOPT', 'WEEKLY_THEME', theme.themeId, 'SUCCESS', `초안 ${d.draftId} 채택`)
      persist()
      return theme
    }, 201),
  ),
  http.post('/api/v1/admin/theme-drafts/:draftId/discard', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = byId(String(params.draftId))
      if (!['READY', 'CHECK_FAILED', 'FAILED'].includes(d.status)) learningFail(409, 'CONFLICT')
      Object.assign(d, { status: 'DISCARDED', updatedAt: stamp() })
      audit('THEME_DRAFT_DISCARD', 'THEME_DRAFT', d.draftId, 'SUCCESS', '초안 버림')
      persist()
      return d
    }),
  ),
  http.post('/api/v1/admin/theme-drafts/:draftId/regenerate', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = byId(String(params.draftId))
      if (d.status === 'GENERATING' || d.status === 'ADOPTED') learningFail(409, 'CONFLICT')
      const next = create({ grade: d.grade, weekStart: d.weekStart, topic: d.input.topic ?? undefined,
        missions: d.input.missions as ThemeDraftRequest['missions'] }, 'ADMIN')
      audit('THEME_DRAFT_REGENERATE', 'THEME_DRAFT', next.draftId, 'SUCCESS', `초안 ${d.draftId} 다시 생성`)
      persist()
      return next
    }, 202),
  ),
]
