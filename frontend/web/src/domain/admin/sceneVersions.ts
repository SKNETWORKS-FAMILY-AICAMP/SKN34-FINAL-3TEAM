import type { ThemeDraftScene, ThemeSceneName } from './themeDrafts.ts'
import { sceneLabels } from './themeDrafts.ts'

export interface SceneVersion extends Omit<ThemeDraftScene, 'scene'> {
  versionId: string
  number: number
  source: 'ORIGINAL' | 'REGENERATED'
  status: string
  createdAt: string
  starred: boolean
  note: string
  selectable: boolean
}
export interface SceneHistory {
  scene: ThemeSceneName
  rootDraftId: string
  editable: boolean
  comparisonPending?: boolean
  selectedVersionId: string | null
  versions: SceneVersion[]
}
export type VersionAnnotation = Partial<Pick<SceneVersion, 'starred' | 'note'>>

function isRecord(raw: unknown): raw is Record<string, unknown> {
  return typeof raw === 'object' && raw !== null && !Array.isArray(raw)
}
const invalid = () => new Error('장면 이력 응답을 확인하지 못했습니다.')

export function readSceneHistory(raw: unknown, scene: ThemeSceneName): SceneHistory {
  if (!isRecord(raw) || raw.scene !== scene || !Array.isArray(raw.versions)) throw invalid()
  const versions = raw.versions.map((row): SceneVersion => {
    if (!isRecord(row) || typeof row.versionId !== 'string' || !row.versionId || !Number.isInteger(row.number) ||
      Number(row.number) < 1 || !['ORIGINAL', 'REGENERATED'].includes(String(row.source)) ||
      typeof row.status !== 'string' || typeof row.selectable !== 'boolean' ||
      typeof row.starred !== 'boolean' || typeof row.note !== 'string' || (row.motion !== null && !isRecord(row.motion)) ||
      typeof row.createdAt !== 'string' || (row.imageUrl !== null && typeof row.imageUrl !== 'string') ||
      (row.videoUrl !== null && typeof row.videoUrl !== 'string')) throw invalid()
    return { versionId: row.versionId, number: Number(row.number), source: row.source as SceneVersion['source'],
      status: row.status, createdAt: row.createdAt, imageUrl: row.imageUrl, videoUrl: row.videoUrl, motion: row.motion,
      starred: row.starred, note: row.note, selectable: row.selectable }
  }).sort((a, b) => b.number - a.number)
  const selected = raw.selectedVersionId
  if (new Set(versions.map(v => v.versionId)).size !== versions.length ||
    !(selected === null || typeof selected === 'string' && versions.some(v => v.versionId === selected))) throw invalid()
  if (typeof raw.rootDraftId !== 'string' || !raw.rootDraftId || typeof raw.editable !== 'boolean') throw invalid()
  if (raw.comparisonPending !== undefined && typeof raw.comparisonPending !== 'boolean') throw invalid()
  return { scene, rootDraftId: raw.rootDraftId, editable: raw.editable, comparisonPending: raw.comparisonPending,
    selectedVersionId: typeof selected === 'string' ? selected : null, versions }
}

export const versionName = (v: SceneVersion) => v.source === 'ORIGINAL' ? '최초 생성본' : `재생성 ${v.number - 1}차`
export const sceneVideoLabel = (scene: ThemeSceneName) =>
  scene === 'INTRO' ? '시작 영상' : scene === 'OUTRO' ? '종료 영상' : sceneLabels[scene] + ' 장면'
