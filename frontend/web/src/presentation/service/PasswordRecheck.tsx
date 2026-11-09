import { useState } from 'react'
import type { DeletionScope, ReauthPurpose } from '../../domain/service.ts'
import { serviceApi } from '../../data/serviceApi.ts'
import { useParentMutation } from '../../data/parent/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

export type ReauthGrant = { reauthToken: string; expiresAt: string }

/**
 * #415: ID·비밀번호 계정의 본인 재확인. 로그인 비밀번호를 다시 입력하면 Google 재확인과 같은 1회 토큰을 바로 받는다.
 * 다른 폼 안에 놓이므로 form을 만들지 않고, Enter도 바깥 폼을 제출하지 않게 막는다. 틀리면 로그인 실패 횟수에 함께 센다.
 */
export function PasswordRecheck({ purpose, childId, scope, label = '비밀번호로 본인 확인', onGrant }: {
  purpose: ReauthPurpose; childId?: string; scope?: DeletionScope; label?: string; onGrant: (grant: ReauthGrant | null) => void
}) {
  const [password, setPassword] = useState(''), [notice, setNotice] = useState('')
  const check = useParentMutation((value: string) =>
    serviceApi.passwordReauth({ purpose, ...(childId ? { childId } : {}), ...(scope ? { scope } : {}), password: value }))
  function submit() {
    if (!password || check.isPending) return
    onGrant(null); setNotice('')
    void check.mutateAsync(password)
      .then((grant) => { onGrant(grant); setNotice('재확인을 마쳤습니다. 선택한 작업만 한 번 실행할 수 있습니다.') })
      .catch(() => {})
      .finally(() => setPassword(''))
  }
  return <div className="ws-form" role="group" aria-label={label}>
    <label>로그인 비밀번호
      <input aria-label={`${label} 비밀번호`} type="password" autoComplete="current-password" maxLength={128} value={password}
        onChange={(e) => setPassword(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit() } }} />
    </label>
    <button type="button" className="cj-secondary" disabled={!password || check.isPending} onClick={submit}>{check.isPending ? '확인 중' : label}</button>
    <p role="status">{notice}</p>
    <ErrorNotice error={check.error} />
  </div>
}
