import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../data/apiClient.ts'
import { usePinLogin } from '../../data/studentDevice/queries.ts'
import { loginState } from '../../domain/studentDevice.ts'
import type { DeviceLoginState } from '../../domain/studentDevice.ts'
import type { Child } from '../../domain/classroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { PinPad } from './PinPad.tsx'

/**
 * 기기 PIN 학생의 access 만료(#59): refresh가 없으므로 같은 자녀 PIN만 다시 받는다.
 * 화면을 떠나지 않아 작성 중 화면과 자동 저장된 초안이 그대로 남는다.
 */
export function PinReentry({ child, onLeave }: { child: Child; onLeave: () => void }) {
  const login = usePinLogin()
  const { setSession, setExpired } = useSession()
  const cache = useQueryClient()
  const [state, setState] = useState<DeviceLoginState | null>(null)
  const blocked = state && ['locked', 'invalid-device', 'pin-not-set', 'not-linked'].includes(state.kind)
  return (
    <div className="pin-reentry">
      <p>
        {child.nickname}, 오래 쉬어서 다시 확인할게요. 쓰던 글은 저장되어 있어요. PIN을 다시 눌러 주세요.
      </p>
      {blocked ? (
        <>
          <p className="device-notice warn" role="alert">
            {state.kind === 'locked'
              ? 'PIN이 잠겼어요. 보호자에게 PIN을 다시 정해 달라고 해 주세요.'
              : state.kind === 'invalid-device'
                ? '이 기기는 더 이상 학습용으로 쓸 수 없어요. 보호자에게 알려 주세요.'
                : '보호자와 함께 다시 시작해 주세요.'}
          </p>
          <button type="button" className="cj-primary" onClick={onLeave}>
            처음 화면으로
          </button>
        </>
      ) : (
        <>
          <PinPad
            label="다시 확인 PIN 숫자 키패드"
            busy={login.isPending}
            onSubmit={(pin) => {
              setState(null)
              login.mutate(
                { childId: child.id, pin },
                {
                  onSuccess: (session) => {
                    setSession(session)
                    setExpired(false)
                    // 같은 자녀·같은 화면을 이어 간다. 저장된 초안은 서버 응답으로 다시 받는다.
                    void cache.invalidateQueries()
                  },
                  onError: (e) => {
                    const p = e instanceof ApiError ? e.problem : null
                    setState(loginState(p?.code ?? '', p?.remainingAttempts, p?.title))
                  },
                },
              )
            }}
          />
          {state?.kind === 'wrong-pin' && (
            <p className="device-notice warn" role="alert">
              PIN이 맞지 않아요.
              {state.remainingAttempts !== null ? ` 남은 기회는 ${state.remainingAttempts}번이에요.` : ''}
            </p>
          )}
          {state?.kind === 'other' && (
            <p className="device-notice warn" role="alert">
              {state.message}
            </p>
          )}
        </>
      )}
    </div>
  )
}
