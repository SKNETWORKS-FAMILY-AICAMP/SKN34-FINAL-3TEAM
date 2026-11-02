import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sharingApi } from '../../data/classroom/sharingApi.ts'
import type { Child } from '../../domain/classroom.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './learning-settings.css'

export function StudentSharingPage({ child }: { child: Child }) {
  const cache = useQueryClient()
  const key = ['sharing-preferences', 'STUDENT', child.id]
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => sharingApi.get(child.id, 'STUDENT', signal), retry: false })
  const save = useMutation({ mutationFn: (enabled: boolean) => sharingApi.save(child.id, enabled),
    onSuccess: value => {
      cache.setQueryData(key, value)
      // Shared-browser caches must not retain parent originals after a change.
      cache.removeQueries({ predicate: q => ['parent', 'records', 'report', 'public-record'].includes(String(q.queryKey[0])) })
    } })
  const value = query.error ? undefined : query.data
  return <main className="st-paper st-sheet st-sharing">
    <h1>내 답 공개 설정</h1>
    <p>내가 쓴 답과 돌아보기를 학부모님께 보여 드릴지 정해 주세요.</p>
    <p>처음에는 비공개입니다. 공개해도 나중에 다시 바꿀 수 있어요.</p>
    {query.isPending && <p role="status">공개 설정을 읽고 있어요.</p>}
    <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    {value && <fieldset disabled={save.isPending}>
      <legend>학부모님께 답변 원문 보여 드리기</legend>
      <label><input type="radio" name="sharing" checked={!(save.isPending ? save.variables : value.parentSharingEnabled)} onChange={() => save.mutate(false)} />비공개로 둘게요</label>
      <label><input type="radio" name="sharing" checked={save.isPending ? save.variables : value.parentSharingEnabled} onChange={() => save.mutate(true)} />학부모님께 공개할게요</label>
    </fieldset>}
    <ErrorNotice error={save.error} />
    <p role="status">{save.isPending ? '설정을 저장하고 있어요.' : value ? `현재 ${value.parentSharingEnabled ? '공개' : '비공개'} 상태입니다.` : ''}</p>
    <p>비공개여도 학습 횟수와 활동 유형은 학부모님께 보입니다. 이미 받으신 파일은 회수되지 않아요.</p>
  </main>
}
