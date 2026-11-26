import { useState } from 'react'
import { useCommunitySettings, useSaveCommunitySettings } from '../../data/retention/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import type { Child } from '../../domain/classroom.ts'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import './learning-settings.css'

/**
 * embedded면 학생 설정(#583) 안의 카드 하나로 그린다(제목 h2 "공개 설정", 바깥 main 없음, #648 시안 Settings).
 * 학부모 공개는 학생이 고르지 않는다(#1064): 자녀 등록 때 학부모가 법정대리인 동의서(GUARDIAN 1.2)로 동의하고,
 * 학생에게는 여기와 첫 둘러보기(#1038)에서 알리기만 한다. 고를 수 있는 것은 친구 공개(P20)뿐이다.
 */
export function StudentSharingPage({ child, embedded = false }: { child: Child; embedded?: boolean }) {
  const Wrapper = embedded ? 'section' : 'main', Title = embedded ? 'h2' : 'h1'
  return <Wrapper className={embedded ? 'st-sharing st-settings-part' : 'st-paper st-sheet st-sharing'} aria-labelledby="sharing-h">
    <Title id="sharing-h" tabIndex={embedded ? -1 : undefined}>{embedded ? '공개 설정' : '내 답 공개 설정'}</Title>
    {/* 학부모 안내 묶음. 설정 카드(embedded)에서는 친구 공개와 왼쪽·오른쪽 두 칸으로 놓는다(#648, 한 화면) */}
    <div className="st-sharing-parent" role="note" aria-label="학부모님께 보이는 답">
      <p><strong>내가 쓴 답은 학부모님이 보실 수 있어요.</strong></p>
      <p className={embedded ? 'st-meta' : undefined}>학부모님이 가입할 때 동의해 주셨어요. 학부모님은 내 답과 리포트로 내가 어떻게 생각했는지 살펴봐요.</p>
    </div>
    <CommunitySharing child={child} level={embedded ? 'h3' : 'h2'} />
  </Wrapper>
}

/**
 * 친구들에게 내 답 보여 주기 (P20, API 명세 2.9). 학부모에게 보이는 것과는 따로인 설정이다.
 * 켠 뒤 마무리한 미션의 마지막 답만 자동으로 공유되고, 끄면 바로 비공개가 된다.
 */
function CommunitySharing({ child, level: Heading }: { child: Child; level: 'h2' | 'h3' }) {
  const [guide, setGuide] = useState(false)
  const query = useCommunitySettings(child.id)
  const save = useSaveCommunitySettings(child.id)
  const value = query.error ? undefined : query.data
  const enabled = save.isPending ? save.variables : value?.enabled
  const needsConsent = save.error instanceof ApiError && save.error.problem.code === 'COMMUNITY_CONSENT_REQUIRED'
  return <section aria-labelledby="community-h">
    <Heading id="community-h">친구들에게 내 답 보여 주기</Heading>
    <p>켜면 같은 미션을 끝낸 친구들에게 내 답이 별명으로 보여요.</p>
    {query.isPending && <p role="status">친구 공개 설정을 읽고 있어요.</p>}
    <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    {value && <fieldset disabled={save.isPending}>
      <legend>친구 공개</legend>
      <label><input type="radio" name="community" checked={!enabled} onChange={() => save.mutate(false)} />나만 볼게요</label>
      <label>
        <input type="radio" name="community" aria-label="친구들에게 보여 줄게요" checked={!!enabled} disabled={!value.consentGranted}
          aria-describedby={value.consentGranted ? undefined : 'community-consent-note'} onChange={() => save.mutate(true)} />
        친구들에게 보여 줄게요
        {!value.consentGranted && <strong className="st-badge"> · 보호자 동의가 필요해요</strong>}
      </label>
    </fieldset>}
    {value && !value.consentGranted && <div className="st-consent-note" id="community-consent-note" role="note">
      <p>학부모님이 계정·자녀 설정 › 공개·동의 › 풀이 공유 커뮤니티에서 동의해 주시면 켤 수 있어요.</p>
    </div>}
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
