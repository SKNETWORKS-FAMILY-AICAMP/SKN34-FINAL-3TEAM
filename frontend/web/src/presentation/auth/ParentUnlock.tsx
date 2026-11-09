import { useState } from 'react'
import { ApiError, parentSessionLocked } from '../../data/apiClient.ts'
import { useAuthentication } from '../../data/classroom/useClassroom.ts'
import type { Session } from '../../domain/classroom.ts'
import { PIN_MAX, unlockProblem } from '../../domain/studentDevice.ts'

/**
 * 자녀 학습(동석 진입) 뒤 학부모 화면 복귀 (FN-ACC-05).
 * 학부모 세션은 잠긴 채 남아 있으므로 Google 로그인 없이 보호자 비밀번호만 확인한다.
 */
export function ParentUnlock({ onUnlocked }: { onUnlocked: (session: Session) => void }) {
  const { unlock } = useAuthentication()
  const [password, setPassword] = useState('')
  const problem = unlock.error instanceof ApiError ? unlock.error.problem : null
  const locked = parentSessionLocked()
  if (!locked && !unlock.error) return null
  return (
    <form
      className="ux-login-form"
      aria-labelledby="parent-unlock-h"
      onSubmit={(e) => {
        e.preventDefault()
        unlock.mutate(password, {
          onSuccess: (session) => { setPassword(''); onUnlocked(session) },
          onError: () => setPassword(''),
        })
      }}
    >
      <h2 id="parent-unlock-h">학부모 화면으로 돌아가기</h2>
      {locked && <>
        <p>자녀가 학습하는 동안 학부모 화면을 잠가 두었습니다. 보호자 비밀번호를 입력하면 바로 돌아갑니다.</p>
        <label className="cj-field">
          보호자 비밀번호
          <input
            aria-label="보호자 비밀번호"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={PIN_MAX}
            value={password}
            onChange={(e) => setPassword(e.target.value.replace(/\D/g, ''))}
            required
          />
        </label>
        <button className="cj-primary" type="submit" disabled={unlock.isPending || password.length < 4}>
          {unlock.isPending ? '확인 중' : '학부모 화면으로'}
        </button>
      </>}
      {problem
        ? <p role="alert">{unlockProblem(problem.code, problem.remainingAttempts)}</p>
        : unlock.error && <p role="alert">{unlockProblem('')}</p>}
      <small>보호자 비밀번호가 없거나 잊었다면 아래에서 다시 로그인해 주세요.</small>
    </form>
  )
}
