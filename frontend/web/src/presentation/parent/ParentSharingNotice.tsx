import { useQuery } from '@tanstack/react-query'
import { sharingApi } from '../../data/classroom/sharingApi.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
export function ParentSharingNotice({ studentId }: { studentId: string }) {
  const query = useQuery({ queryKey: ['parent', 'sharing-preferences', studentId],
    queryFn: ({ signal }) => sharingApi.get(studentId, 'PARENT', signal), retry: false,
    staleTime: 0, refetchOnWindowFocus: 'always' })
  return <aside className="ws-card" aria-label="학생 답변 공개 상태">
    <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    {query.isPending ? <p>학생 답변 공개 상태를 확인 중입니다.</p> : !query.error && <p>{query.data?.parentSharingEnabled
      ? '학생이 답변 원문을 공개했습니다. 학생이 설정을 바꾸면 원문 조회도 변경됩니다.'
      : '학생이 답변 원문을 비공개로 설정했습니다. 학습 수치와 활동 유형은 계속 확인할 수 있습니다. 공개 여부는 학생이 정합니다.'}</p>}
  </aside>
}
