import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sharingApi } from '../../data/classroom/sharingApi.ts'
import { useCommunitySettings, useSaveCommunitySettings } from '../../data/retention/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import type { Child } from '../../domain/classroom.ts'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
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
    <CommunitySharing child={child} />
  </main>
}

/**
 * 친구들에게 내 답 보여 주기 (P20, API 명세 2.9). 학부모 공개(#206)와 따로인 설정이다.
 * 켠 뒤 마무리한 미션의 마지막 답만 자동으로 공유되고, 끄면 바로 비공개가 된다.
 */
function CommunitySharing({ child }: { child: Child }) {
  const [guide, setGuide] = useState(false)
  const query = useCommunitySettings(child.id)
  const save = useSaveCommunitySettings(child.id)
  const value = query.error ? undefined : query.data
  const enabled = save.isPending ? save.variables : value?.enabled
  const needsConsent = save.error instanceof ApiError && save.error.problem.code === 'COMMUNITY_CONSENT_REQUIRED'
  return <section aria-labelledby="community-h">
    <h2 id="community-h">친구들에게 내 답 보여 주기</h2>
    <p>켜 두면 내가 마무리한 미션의 답이 같은 미션을 마무리한 친구들에게 별명으로 보여요. 처음에는 꺼져 있어요.</p>
    {query.isPending && <p role="status">친구 공개 설정을 읽고 있어요.</p>}
    <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    {value && !value.consentGranted && <p className="st-meta" role="note">학부모님이 커뮤니티 이용에 동의해 주셔야 켤 수 있어요. 학부모님께 부탁해 보세요.</p>}
    {value && <fieldset disabled={save.isPending}>
      <legend>친구 공개</legend>
      <label><input type="radio" name="community" checked={!enabled} onChange={() => save.mutate(false)} />나만 볼게요</label>
      <label><input type="radio" name="community" checked={!!enabled} disabled={!value.consentGranted} onChange={() => save.mutate(true)} />친구들에게 보여 줄게요</label>
    </fieldset>}
    {needsConsent ? <p role="alert">학부모님 동의가 아직 없어서 켜지 못했어요.</p> : <ErrorNotice error={save.error} />}
    {value && <p role="status">{save.isPending ? '친구 공개 설정을 저장하고 있어요.' : `친구 공개 ${value.enabled && value.consentGranted ? '켜짐' : '꺼짐'}`}</p>}
    <div className="st-sharing-actions">
      {value && !value.consentGranted && <button type="button" className="st-button" onClick={() => setGuide(true)}>보호자 동의 방법 보기</button>}
      <button type="button" className="st-button" disabled={query.isFetching || save.isPending} onClick={() => void query.refetch()}>동의 상태 다시 확인</button>
    </div>
    <p>끄면 이미 나눈 답도 바로 안 보이게 돼요. 다시 켜면 다시 보여요.</p>
    {guide && <Modal title="친구 공개를 켜려면" onClose={() => setGuide(false)}><ol><li>학부모님이 학부모 화면에 로그인해요.</li><li>계정·자녀 설정 → 공개·동의에서 커뮤니티 이용에 동의해요.</li><li>이 화면으로 돌아와 동의 상태 다시 확인을 눌러 주세요.</li><li>친구들에게 보여 줄게요를 직접 골라 주세요.</li></ol><p>보호자가 동의해도 내 답이 바로 공개되지는 않아요. 마지막 선택은 내가 해요.</p><button type="button" className="st-button" onClick={() => setGuide(false)}>알겠어요</button></Modal>}
  </section>
}
