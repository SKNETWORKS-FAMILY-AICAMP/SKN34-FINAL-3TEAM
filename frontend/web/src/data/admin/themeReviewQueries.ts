import { useQueries } from '@tanstack/react-query'
import { adminApi } from './api.ts'
import { adminRetentionApi } from './retentionApi.ts'
import { useAdminQuery } from './queries.ts'
import { THEME_DAYS } from '../../domain/retention.ts'
import { sceneVideoLabel, versionName } from '../../domain/admin/sceneVersions.ts'
import { THEME_SCENES, sceneLabels, type ThemeDraft } from '../../domain/admin/themeDrafts.ts'

export function useStoryboardScenes(draft: ThemeDraft | undefined, enabled: boolean) {
  return useQueries({ queries: THEME_SCENES.map(scene => ({
    queryKey: ['admin', 'theme-scene-history', draft?.draftId, scene],
    queryFn: ({ signal }: { signal: AbortSignal }) => adminRetentionApi.sceneVersions(draft!.draftId, scene, signal),
    enabled: !!draft?.draft && enabled,
    retry: false,
  })) }).map((query, i) => {
    const scene = THEME_SCENES[i]
    const history = query.isError ? undefined : query.data
    const selected = history?.versions.find(v => v.versionId === history.selectedVersionId)
    const mission = draft?.draft?.missions.find(m => m.day === scene)
    const title = scene === 'INTRO' ? draft?.draft?.theme?.title : scene === 'OUTRO' ? draft?.draft?.theme?.outro : mission?.title
    return {
      scene, title: title || sceneLabels[scene], question: mission?.question,
      label: sceneVideoLabel(scene), versionCount: history?.versions.length ?? 0, comparisonPending: history?.comparisonPending === true, editable: history?.editable,
      selected, image: selected?.imageUrl ?? draft?.scenes.find(s => s.scene === scene)?.imageUrl,
      status: query.isError ? '이력 조회 실패' : !history ? '이력 조회 중' : history.comparisonPending ? '비교 대기' : selected ? versionName(selected) : '선택 전',
      loading: query.isPending, error: query.error, refetch: query.refetch,
    }
  })
}
export type StoryboardScenes = ReturnType<typeof useStoryboardScenes>

// The draft and the missions created at adoption have separate publishing lifecycles.
export function useAdoptedTheme(themeId: string | null) {
  return useAdminQuery(['theme-mission-progress', themeId], async signal => {
    const theme = await adminRetentionApi.theme(themeId!, signal)
    const missions = await Promise.all(theme.days.map(async ({ day, missionId }) => ({
      day, mission: await adminApi.mission(missionId, signal),
    })))
    const published = THEME_DAYS.filter(day => missions.find(row => row.day === day)?.mission.status === 'PUBLISHED').length
    return { theme, missions, published }
  }, !!themeId)
}
