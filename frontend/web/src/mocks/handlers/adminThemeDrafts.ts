import { http } from 'msw/http'
import type { AdminMission } from '../../domain/admin/operations.ts'
import type { ThinkingType } from '../../domain/classroom.ts'
import { REGEN_TARGETS, regenTargetLabel, themeDraftRequestErrors, THEME_SCENES } from '../../domain/admin/themeDrafts.ts'
import type { RegenTarget, ThemeDraftRequest, ThemeDraftStatus, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import type { SceneHistory, VersionAnnotation } from '../../domain/admin/sceneVersions.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { THEME_DAYS } from '../../domain/retention.ts'
import { achievementStandards, audit, missions, stamp } from '../fixtures/admin/operations.ts'
import { persistRetention, retentionState } from '../fixtures/retention.ts'
import { assignWeek, plannedWeek, requireOpenWeek, weekLocked } from '../fixtures/themePlanning.ts'
import { allow } from './admin.ts'
import { fail } from './parent.ts'
import { respond } from './student.ts'

/**
 * 관리자 테마 초안 목업(#441, api-spec 2.8·4.1 `ThemeDraft`). learning #438 생성 작업을 화면 확인에 필요한 만큼만 흉내 낸다.
 * - 요청 3초 뒤 조회에서 결과가 생김. 주제에 '실패'가 있으면 CHECK_FAILED(검사 실패 사유·초안 함께)
 * - 그림은 가상 SVG data URL, 영상 없음(움직임은 그림 위 카메라·문구·살펴보기 지점으로 확인)
 * - 채택: 미션 5개 DRAFT(source LLM_THEME)·테마 DRAFT. 게시는 미션·테마를 각각
 * - 부분 다시 생성(#537): 본문 targets가 있으면 원래 초안 결과를 복사하고 고른 장면만 바꾼다(그림 제목·미션 제목에 '다시 만듦').
 *   다시 만들 수 있는 대상은 저장하지 않고 응답할 때 계산한다(이 기능 전에 저장된 목업 초안도 같게 보이게)
 */
interface MockThemeDraft {
  selections?: Partial<Record<ThemeSceneName, { id: string; seen: number }>>
  annotations?: Partial<Record<ThemeSceneName, VersionAnnotation>>
  draftId: string
  status: ThemeDraftStatus
  source: 'AUTO' | 'ADMIN'
  grade: ThemeDraftRequest['grade']
  weekStart: string
  attempts: number
  maxAttempts: number
  input: {
    topic: string | null
    missions: { thinkingType: ThinkingType; inputType: string; standardCodes: string[] }[]
    regenerate?: { baseDraftId: string; targets: RegenTarget[] } | null
  }
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
const sceneSvg = (scene: ThemeSceneName, title: string, take = 0) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360"><rect width="640" height="360" fill="#C6EAE1"/>` +
  `<circle cx="${520-(take%5)*60}" cy="${80+(take%3)*18}" r="40" fill="#F2C14E"/><path d="M0 360 L160 170 L280 260 L420 140 L640 360Z" fill="${HUES[scene]}" stroke="#1F2421" stroke-width="5"/>` +
  `<circle cx="${250+(take%6)*42}" cy="250" r="${34+(take%4)*5}" fill="#FFFDF7" stroke="#1F2421" stroke-width="5"/><text x="24" y="44" font-size="28" font-family="sans-serif" fill="#1F2421">${scene} · ${title}</text></svg>`)
/** ai 움직임 형식 v1 그대로(ai-service.yaml ThemeMotion: 카메라 8~20초, 방향 0~359도, 빠르기 2~20, #440에서 계약 범위로 맞춤) */
const motionOf = (scene: ThemeSceneName) => ({
  version: 1,
  transition: { kind: 'fade', seconds: 0.5 },
  camera: { from: { x: 50, y: 50, zoom: 1 }, to: { x: 40, y: 60, zoom: 1.3 }, seconds: 10 },
  speakers: scene === 'INTRO' || scene === 'OUTRO' ? {} : { 뭉치: { x: 39, y: 69, zoom: 1.2 } },
  effects: scene === 'OUTRO' ? [{ shape: 'bubble', color: '#FFF3C4', count: 12, size: 6, direction: 180, speed: 4, opacity: 0.8 }]
    : scene === 'MON' ? [{ shape: 'leaf', color: '#6FA84B', count: 8, size: 3, direction: 20, speed: 5, opacity: 0.6 }] : [],
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
  if (d.input.regenerate) return partialResult(d, d.input.regenerate)
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
const REGENERABLE: ThemeDraftStatus[] = ['READY', 'CHECK_FAILED', 'FAILED', 'DISCARDED']
/** learning regenerableTargets 흉내: 다시 생성할 수 있는 상태이고 요일 미션 5개가 있으면 14개 모두(목업은 재료가 늘 있음) */
function regenerableTargets(d: MockThemeDraft): RegenTarget[] {
  const missionCount = Array.isArray((d.draft as { missions?: unknown[] } | null)?.missions) ? (d.draft as { missions: unknown[] }).missions.length : 0
  return REGENERABLE.includes(d.status) && missionCount === 5 ? [...REGEN_TARGETS] : []
}
function rootOf(d: MockThemeDraft): MockThemeDraft {
  let node=d
  const seen=new Set([d.draftId])
  while(node.input.regenerate){
    const parent=drafts.find(record=>record.draftId===node.input.regenerate?.baseDraftId)
    if(!parent||seen.has(parent.draftId))break
    seen.add(parent.draftId);node=parent
  }
  return node
}
function historyOf(d: MockThemeDraft, name: ThemeSceneName): SceneHistory {
  const root=rootOf(d)
  const records=drafts.filter(record=>rootOf(record).draftId===root.draftId && record.scenes.some(s=>s.scene===name) &&
    (record.draftId===root.draftId || record.input.regenerate?.targets.some(t=>t.endsWith(':'+name))))
    .sort((a,b)=>a===b?0:a.draftId===root.draftId?-1:b.draftId===root.draftId?1:a.createdAt.localeCompare(b.createdAt)||a.draftId.localeCompare(b.draftId))
  const versions=records.map((record,i)=>{
    const media=record.scenes.find(s=>s.scene===name)!
    return {versionId:record.draftId,number:i+1,source:i===0?'ORIGINAL' as const:'REGENERATED' as const,
      imageUrl:media.imageUrl,videoUrl:media.videoUrl,motion:media.motion,createdAt:record.createdAt,
      starred:record.annotations?.[name]?.starred??false,note:record.annotations?.[name]?.note??'',
      status:record.status,selectable:record.status==='READY'}
  }).reverse()
  const selected=root.selections?.[name]?.id ?? (records.includes(d)?d.draftId:records[0]?.draftId)
  const assignedWeek=plannedWeek(d.draftId)
  return {scene:name,rootDraftId:root.draftId,versions,selectedVersionId:selected??null,editable:root.status==='READY'&&d.status==='READY'&&(!assignedWeek||!weekLocked(d.grade,assignedWeek))}
}
interface MockOutput { missions?: {day:string}[]; dialogues?: {day:string}[]; theme?: {days?: {day:string}[]} }
function chosenOutput(d: MockThemeDraft) {
  const output=structuredClone(d.draft)
  const data=output as MockOutput|null
  const root=rootOf(d)
  const scenes=d.scenes.map(original=>{
    const chosenId=root.selections?.[original.scene]?.id
    const selected=chosenId ? byId(chosenId) : d
    const source=selected.draft as MockOutput|null
    if(data&&source&&selected!==d){
      for(const key of ['missions','dialogues'] as const){
        const item=source[key]?.find(r=>r.day===original.scene)
        if(item&&data[key])data[key]=data[key].map(r=>r.day===original.scene?item:r)
      }
      const day=source.theme?.days?.find(r=>r.day===original.scene)
      if(day&&data.theme?.days)data.theme.days=data.theme.days.map(r=>r.day===original.scene?day:r)
    }
    return selected.scenes.find(s=>s.scene===original.scene)??original
  })
  return { draft:output, scenes }
}
function view(d: MockThemeDraft) {
  const planned=plannedWeek(d.draftId)
  const effective=planned??retentionState.themes.find(t=>t.themeId===d.themeId)?.weekStart??d.weekStart
  return { ...d, ...chosenOutput(d), plannedWeek:planned, weekLocked:!!(planned||d.themeId)&&weekLocked(d.grade,effective),
    adoptionWeekLocked:weekLocked(d.grade,effective),input:{...d.input,regenerate:d.input.regenerate??null},regenerableTargets:regenerableTargets(d) }
}
export function mockPlannerDrafts() {
  return drafts.map(advance).filter(d=>d.status==='READY'&&!d.input.regenerate).map(d=>({
    draftId:d.draftId,grade:d.grade,title:String((d.draft?.theme as {title?:string})?.title??d.input.topic??'테마 초안'),
    generationWeek:d.weekStart,plannedWeek:plannedWeek(d.draftId),
  }))
}
async function checkPlanningSnapshot(req:Request,d:MockThemeDraft) {
  const body=await req.json() as {expectedPlannedWeek?:string|null}
  if(Object.hasOwn(body,'expectedPlannedWeek') && body.expectedPlannedWeek!==plannedWeek(d.draftId))learningFail(409,'CONFLICT')
}
/** 부분 다시 생성 결과: 원래 초안 결과를 복사하고 고른 장면만 바꿈(그림·영상·움직임·미션 표시) */
function partialResult(d: MockThemeDraft, spec: { baseDraftId: string; targets: RegenTarget[] }) {
  const base = drafts.find((x) => x.draftId === spec.baseDraftId)
  d.attempts += 1
  d.updatedAt = stamp()
  if (!base?.draft) {
    d.checkResults.push({ attempt: d.attempts, failures: [{ stage: 'LEARNING', reasons: [`BASE_MISSING 원래 초안 ${spec.baseDraftId}의 생성 결과·재료(regen) 없음`] }] })
    d.status = d.attempts >= d.maxAttempts ? 'CHECK_FAILED' : 'GENERATING'
    return
  }
  const draft = structuredClone(base.draft) as { theme: { title: string }; missions: { day: string; draft: { title: string } }[] }
  const scenes = structuredClone(base.scenes)
  for (const target of spec.targets) {
    const [kind, name] = target.split(':') as ['VIDEO' | 'IMAGE' | 'MISSION', ThemeSceneName]
    const s = scenes.find((x) => x.scene === name)
    const take=historyOf(base,name).versions.length
    if (s) {
      if(kind!=='VIDEO')s.imageUrl=sceneSvg(name,`${draft.theme.title} · 다시 만듦 ${take}`,take)
      const motion=motionOf(name)
      motion.camera.to.x=40+(take%4)*12
      s.motion=motion
    }
    if (kind === 'MISSION') {
      const m = draft.missions.find((x) => x.day === name)
      if (m) m.draft.title = `${m.draft.title} (다시 만듦 ${take})`
    }
  }
  d.draft = draft
  d.scenes = scenes
  d.versions = { prompt: 'theme-draft-mock-1', model: 'mock-model' }
  d.status = 'READY'
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
  const chosen = chosenOutput(d)
  const g = chosen.draft as { theme: { title: string; intro: string; outro: string }; missions: { thinkingType: ThinkingType; draft: { title: string; question: string; guide: string } }[] }
  const grade = Number(d.grade.slice(1)), subjectOf = (code: string) => achievementStandards.find((s) => s.code === code)?.subject ?? ''
  const ids = d.input.missions.map((input, i) => {
    const m: AdminMission = {
      missionId: crypto.randomUUID(), code: `MOCK-THEME-${missions.length + 1}`, source: 'LLM_THEME', status: 'DRAFT', demoOnly: false,
      currentVersion: 1, currentRubricVersion: 1, publishedVersion: null, publishedRubricVersion: null,
      versions: [{ version: 1, title: g.missions[i].draft.title, subject: subjectOf(input.standardCodes[0]), gradeMin: grade, gradeMax: grade,
        thinkingType: input.thinkingType, inputType: input.inputType as AdminMission['versions'][number]['inputType'],
        question: g.missions[i].draft.question, guide: g.missions[i].draft.guide, answerUnit: null, inputTemplate: [],
        sceneUri: chosen.scenes.find((s) => s.scene === THEME_DAYS[i])?.imageUrl ?? null, staticSceneUri: null,
        achievementStandards: input.standardCodes, achievementLevels: null, choices: [], categories: [], createdAt: stamp() }],
      rubrics: [{ version: 1, elements: [{ code: 'e1', label: '생각 근거', description: '장면에서 찾은 근거를 말함', points: 1, commonErrors: [],
        goodThought: true, judgeVerified: false, standardCode: input.standardCodes[0] }], answerKey: null, exampleAnswer: null,
        forbiddenTerms: ['시계탑'], hints: ['무엇을 보았나요?'], keywords: [], essayType: null }],
      reviews: [],
    }
    missions.push(m)
    return m.missionId
  })
  const scene = (name: ThemeSceneName) => chosen.scenes.find((s) => s.scene === name)
  const theme = {
    themeId: `theme-${crypto.randomUUID().slice(0, 8)}`, grade: d.grade, weekStart: plannedWeek(d.draftId)??d.weekStart, title: g.theme.title, intro: g.theme.intro,
    days: THEME_DAYS.map((day, i) => ({ day, missionId: ids[i] })), status: 'DRAFT' as const, updatedAt: stamp(),
    outro: g.theme.outro, introImageUrl: scene('INTRO')?.imageUrl ?? null, outroImageUrl: scene('OUTRO')?.imageUrl ?? null,
    introVideoUrl: scene('INTRO')?.videoUrl ?? null, outroVideoUrl: scene('OUTRO')?.videoUrl ?? null, introMotion: scene('INTRO')?.motion ?? null, outroMotion: scene('OUTRO')?.motion ?? null,
  }
  retentionState.themes.unshift(theme)
  persistRetention()
  Object.assign(d, { status: 'ADOPTED', themeId: theme.themeId, updatedAt: stamp() })
  assignWeek(d.draftId,null)
  return theme
}

const historyPath='/api/v1/admin/theme-drafts/:draftId/scenes/:scene/versions'
function readContext(id:string,name:string) {
  if(!(THEME_SCENES as string[]).includes(name))return learningFail()
  const d=byId(id),scene=name as ThemeSceneName
  return {d,scene,history:historyOf(d,scene)}
}
export const adminThemeDraftHandlers = [
  http.get(historyPath,({request,params})=>respond(async()=>{
    allow(request,'CONTENT')
    return readContext(String(params.draftId),String(params.scene)).history
  })),
  http.put(historyPath+'/selection',({request,params})=>respond(async()=>{
    allow(request,'CONTENT')
    const {d,scene,history}=readContext(String(params.draftId),String(params.scene))
    const body=await request.json() as {versionId:string;expectedVersionId:string;expectedVersionCount?:number}
    if(!history.editable || body.expectedVersionId!==history.selectedVersionId ||
      (body.expectedVersionCount!==undefined && body.expectedVersionCount!==history.versions.length) ||
      !history.versions.some(v=>v.versionId===body.versionId&&v.selectable))return learningFail(409,'CONFLICT')
    const root=rootOf(d)
    root.selections={...root.selections,[scene]:{id:body.versionId,seen:history.versions.length}}
    persist();return historyOf(d,scene)
  })),
  http.patch(historyPath+'/:versionId',({request,params})=>respond(async()=>{
    allow(request,'CONTENT')
    const {d,scene,history}=readContext(String(params.draftId),String(params.scene))
    const row=history.versions.find(v=>v.versionId===params.versionId)
    if(!history.editable || !row?.selectable)return learningFail(409,'CONFLICT')
    const change=await request.json() as VersionAnnotation
    if(!Object.keys(change).length || ('starred' in change && typeof change.starred!=='boolean') ||
      ('note' in change && (typeof change.note!=='string'||[...change.note].length>160)))return learningFail()
    const source=byId(row.versionId)
    source.annotations={...source.annotations,[scene]:{...source.annotations?.[scene],...change}}
    persist();return historyOf(d,scene)
  })),
  http.post('/api/v1/admin/theme-drafts', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const body = (await request.json()) as ThemeDraftRequest
      if (themeDraftRequestErrors(body).length || (body.topic && body.topic.length > 100)) learningFail()
      requireOpenWeek(body.grade,body.weekStart)
      const d = create(body, 'ADMIN')
      audit('THEME_DRAFT_REQUEST', 'THEME_DRAFT', d.draftId, 'SUCCESS', '테마 초안 생성 요청')
      persist()
      return view(d)
    }, 202),
  ),
  http.get('/api/v1/admin/theme-drafts', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const q = new URL(request.url).searchParams
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20), status = q.get('status'), source = q.get('source')
      if (!Number.isInteger(index) || index < 0 || !Number.isInteger(size) || size < 1 || size > 100) learningFail()
      const rows = drafts.map(advance).filter(d => (!status || d.status===status) && (!source || d.source===source) &&
        (!q.get('grade')||d.grade===q.get('grade')) && (!q.get('weekStart')||d.weekStart===q.get('weekStart')) &&
        (q.get('hideDiscarded')!=='true'||d.status!=='DISCARDED') &&
        (q.get('comparisonPending')!=='true' || (d.status==='READY' && rootOf(d)===d && THEME_SCENES.some(s=>{
          const h=historyOf(d,s)
          return h.versions.length>(d.selections?.[s]?.seen??1)&&h.versions.some(v=>v.source==='REGENERATED'&&v.selectable)
        }))))
      persist()
      return { items: rows.slice(index * size, (index + 1) * size).map(view), page: index, size, totalElements: rows.length }
    }),
  ),
  http.get('/api/v1/admin/theme-drafts/:draftId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = advance(byId(String(params.draftId)))
      persist()
      return view(d)
    }),
  ),
  http.post('/api/v1/admin/theme-drafts/:draftId/adopt', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = byId(String(params.draftId))
      if (d.status !== 'READY' || !d.draft) learningFail(409, 'CONFLICT')
      await checkPlanningSnapshot(request,d)
      requireOpenWeek(d.grade,plannedWeek(d.draftId)??d.weekStart)
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
      await checkPlanningSnapshot(request,d)
      const assigned=plannedWeek(d.draftId)
      if(assigned)requireOpenWeek(d.grade,assigned)
      assignWeek(d.draftId,null)
      Object.assign(d, { status: 'DISCARDED', updatedAt: stamp() })
      audit('THEME_DRAFT_DISCARD', 'THEME_DRAFT', d.draftId, 'SUCCESS', '초안 버림')
      persist()
      return view(d)
    }),
  ),
  http.post('/api/v1/admin/theme-drafts/:draftId/regenerate', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = byId(String(params.draftId))
      // learning #537과 같은 검사: targets 없음·null은 전체, 목록이면 1개 이상·알려진 값만(400), 다시 만들 수 없는 대상은 409
      const raw = ((await request.json().catch(() => ({}))) as { targets?: unknown }).targets
      if (raw != null && (!Array.isArray(raw) || !raw.length || raw.some((t) => !(REGEN_TARGETS as unknown[]).includes(t)))) learningFail()
      const targets = raw == null ? null : [...new Set(raw as RegenTarget[])]
      if (d.status === 'GENERATING' || d.status === 'ADOPTED') learningFail(409, 'CONFLICT')
      if(d.status==='DISCARDED' && targets)learningFail(409,'CONFLICT')
      if (targets && targets.some((t) => !regenerableTargets(d).includes(t))) learningFail(409, 'CONFLICT')
      const next = create({ grade: d.grade, weekStart: d.weekStart, topic: d.input.topic ?? undefined,
        missions: d.input.missions as ThemeDraftRequest['missions'] }, 'ADMIN')
      next.input = { ...structuredClone(d.input), regenerate: targets ? { baseDraftId: d.draftId, targets } : null }
      audit('THEME_DRAFT_REGENERATE', 'THEME_DRAFT', next.draftId, 'SUCCESS',
        targets ? `초안 ${d.draftId} 부분 다시 생성(${targets.map(regenTargetLabel).join(', ')})` : `초안 ${d.draftId} 다시 생성`)
      persist()
      return view(next)
    }, 202),
  ),
]
