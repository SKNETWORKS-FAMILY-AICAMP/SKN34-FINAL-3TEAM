import { useState } from 'react'
import { ThemeFrame } from './world/StudentWorld.tsx'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../data/apiClient.ts'
import { isDemo } from '../../data/classroom/useClassroom.ts'
import { useDeviceProfiles, useDeviceRegistration, usePinLogin } from '../../data/studentDevice/queries.ts'
import {
  PAIRING_CODE_LENGTH,
  loginState,
  normalizePairingCode,
  validPairingCode,
} from '../../domain/studentDevice.ts'
import type { DeviceLoginState, StudentProfile } from '../../domain/studentDevice.ts'
import { useSession } from '../auth/sessionContext.ts'
import { Brand, ErrorNotice } from '../shared/ClassroomParts.tsx'
import { PinPad } from './PinPad.tsx'
import '../classroom.css'

const code = (e: unknown) => (e instanceof ApiError ? e.problem.code : '')

/**
 * 자녀 기기 진입 (P01 개정, FN-ACC-05). 학부모가 등록한 기기에서만 프로필·PIN 화면이 열린다.
 * 미등록·해제·만료 기기(401 STUDENT_DEVICE_INVALID)에는 PIN 화면 대신 코드 등록 화면만 보인다.
 */
export function DeviceLogin() {
  const [registered, setRegistered] = useState(false)
  const profiles = useDeviceProfiles()
  const cache = useQueryClient()
  const unregistered = code(profiles.error) === 'STUDENT_DEVICE_INVALID'
  return (
    <div id="class-journal">
      <div className="cj-app-student">
      {/* 로그인 전이라 학생 설정을 모르므로 기본 테마(호수)로 그린다 */}
      <ThemeFrame>
      <main className="device-login">
        <section className="device-card" aria-busy={profiles.isPending}>
          <Brand />
          {registered && !unregistered && <p role="status">기기 등록을 마쳤어요. 이제 내 PIN으로 들어가요.</p>}
          {isDemo && <DemoDeviceScenario onApplied={() => void cache.invalidateQueries({ queryKey: ['student-device'] })} />}
          {profiles.isPending ? (
            <p role="status">이 기기를 확인하고 있어요.</p>
          ) : unregistered ? (
            <Registration onRegistered={() => setRegistered(true)} />
          ) : profiles.error instanceof ApiError && profiles.error.problem.status === 404 ? (
            // 백엔드에 기기·PIN API(명세 3.11)가 아직 없을 때. 원시 404 대신 동석 진입을 안내한다.
            <>
              <h1>자녀 기기 로그인은 준비 중이에요</h1>
              <p className="lead">지금은 보호자가 로그인한 뒤 자녀를 골라 함께 시작할 수 있어요.</p>
              <GuardianLinks />
            </>
          ) : profiles.error ? (
            <ErrorNotice error={profiles.error} retry={() => void profiles.refetch()} />
          ) : (
            <ProfileAndPin profiles={profiles.data ?? []} />
          )}
        </section>
      </main>
      </ThemeFrame>
      </div>
    </div>
  )
}

function Registration({ onRegistered }: { onRegistered: () => void }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const [value, setValue] = useState(normalizePairingCode(params.get('code') ?? ''))
  const [label, setLabel] = useState('')
  const register = useDeviceRegistration(() => {
    onRegistered()
    setParams((p) => { p.delete('code'); return p }, { replace: true, state: location.state })
  })
  const normalized = normalizePairingCode(value)
  return (
    <>
      <h1>이 기기를 학습용으로 등록해요</h1>
      <p className="lead">
        보호자 화면 ‘자녀 기기·PIN’에서 받은 {PAIRING_CODE_LENGTH}자리 코드를 입력해 주세요. 코드는 10분
        동안 한 번만 쓸 수 있어요.
      </p>
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (!validPairingCode(normalized)) return
          register.mutate({ code: normalized, label })
        }}
      >
        <label>
          등록 코드
          <input
            className="device-code"
            aria-label="등록 코드"
            autoComplete="off"
            spellCheck={false}
            maxLength={PAIRING_CODE_LENGTH + 2}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </label>
        <label>
          기기 이름 <small>보호자가 기기 목록에서 알아볼 이름</small>
          <input
            aria-label="기기 이름"
            placeholder="예: 거실 컴퓨터"
            maxLength={30}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        {value && !validPairingCode(normalized) && (
          <p role="alert">코드는 영어 대문자와 숫자 {PAIRING_CODE_LENGTH}자리예요.</p>
        )}
        <button className="cj-primary" disabled={register.isPending || !validPairingCode(normalized)}>
          {register.isPending ? '등록하는 중' : '이 기기 등록하기'}
        </button>
        <ErrorNotice error={register.error} />
      </form>
      <GuardianLinks />
    </>
  )
}

function ProfileAndPin({ profiles }: { profiles: StudentProfile[] }) {
  const [chosen, setChosen] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [state, setState] = useState<DeviceLoginState | null>(null)
  const login = usePinLogin()
  const { setSession, setExpired } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const cache = useQueryClient()
  // 기기에 자녀가 한 명이면 프로필 선택을 건너뛴다 (#59 확인 결과)
  const single = profiles.length === 1 && !showAll
  const selected = profiles.find((p) => p.childId === (single ? profiles[0].childId : chosen))

  if (!profiles.length)
    return (
      <>
        <h1>이 기기에 등록된 친구가 없어요</h1>
        <p className="lead">보호자에게 기기를 다시 등록해 달라고 해 주세요.</p>
        <GuardianLinks />
      </>
    )

  if (!selected)
    return (
      <>
        <h1>누가 공부할까요?</h1>
        <div className="device-profiles">
          {profiles.map((p) => (
            <button
              key={p.childId}
              type="button"
              onClick={() => {
                setChosen(p.childId)
                setState(null)
              }}
            >
              {p.nickname}
              <small>{p.pinLocked ? '잠겨 있어요' : p.pinSet ? 'PIN으로 들어가요' : 'PIN이 아직 없어요'}</small>
            </button>
          ))}
        </div>
        <GuardianLinks />
      </>
    )

  const back = () => {
    setChosen(null)
    setShowAll(true)
    setState(null)
  }
  const locked = selected.pinLocked || state?.kind === 'locked'
  return (
    <>
      <h1>{selected.nickname}, 안녕하세요!</h1>
      {locked ? (
        <p className="device-notice warn" role="alert">
          PIN이 잠겼어요. 보호자에게 PIN을 다시 정해 달라고 해 주세요.
        </p>
      ) : !selected.pinSet || state?.kind === 'pin-not-set' ? (
        <p className="device-notice warn" role="alert">
          아직 PIN이 없어요. 보호자와 함께 로그인해서 시작해 주세요.
        </p>
      ) : (
        <>
          <p className="lead">내 PIN을 눌러 주세요.</p>
          <PinPad
            label="PIN 숫자 키패드"
            busy={login.isPending}
            onSubmit={(pin) => {
              setState(null)
              login.mutate(
                { childId: selected.childId, pin },
                {
                  onSuccess: (session) => {
                    cache.clear()
                    setExpired(false)
                    // LoginGate가 세션의 startPath로 보내므로 돌아갈 화면을 함께 둔다
                    const target = returnTo(location.state)
                    setSession({ ...session, startPath: target })
                    navigate(target, { replace: true })
                  },
                  onError: (e) => {
                    const p = e instanceof ApiError ? e.problem : null
                    setState(loginState(p?.code ?? '', p?.remainingAttempts, p?.title))
                  },
                },
              )
            }}
          />
          <LoginMessage state={state} />
        </>
      )}
      <div className="device-links">
        {(profiles.length > 1 || single) && (
          <button type="button" className="cj-secondary" onClick={back}>
            {single ? '내가 아니에요' : '다른 친구 고르기'}
          </button>
        )}
        <GuardianLinks inline />
      </div>
    </>
  )
}

function LoginMessage({ state }: { state: DeviceLoginState | null }) {
  if (!state) return null
  const text =
    state.kind === 'wrong-pin'
      ? `PIN이 맞지 않아요.${state.remainingAttempts !== null ? ` 남은 기회는 ${state.remainingAttempts}번이에요.` : ''}`
      : state.kind === 'invalid-device'
        ? '이 기기는 더 이상 학습용으로 쓸 수 없어요. 보호자에게 다시 등록해 달라고 해 주세요.'
        : state.kind === 'not-linked'
          ? '보호자와 연결이 확인되지 않았어요. 보호자에게 알려 주세요.'
          : state.kind === 'other'
            ? state.message
            : ''
  return text ? (
    <p className="device-notice warn" role="alert">
      {text}
    </p>
  ) : null
}

/** 학생 → 학부모 화면 전환은 항상 학부모 로그인을 거친다 (FN-ACC-05). */
function GuardianLinks({ inline = false }: { inline?: boolean }) {
  const navigate = useNavigate()
  const button = (
    <button type="button" className="cj-secondary" onClick={() => navigate('/login')}>
      보호자 로그인
    </button>
  )
  return inline ? button : <div className="device-links">{button}</div>
}

/** 개발(MSW) 전용 상태 선택기: 해제·만료 기기, PIN 잠금·미설정 시나리오 */
function DemoDeviceScenario({ onApplied }: { onApplied: () => void }) {
  return (
    <label className="ux-help">
      기기 상태 시연
      <select
        aria-label="기기 상태 시연"
        defaultValue=""
        onChange={(e) => {
          const value = e.target.value
          if (!value) return
          const done = () => {
            window.removeEventListener('sagomungchi:device-scenario-applied', done)
            onApplied()
          }
          window.addEventListener('sagomungchi:device-scenario-applied', done)
          window.dispatchEvent(new CustomEvent('sagomungchi:device-scenario', { detail: value }))
          e.target.value = ''
        }}
      >
        <option value="">선택</option>
        <option value="device-revoked">보호자가 기기 해제</option>
        <option value="device-expired">기기 등록 만료</option>
        <option value="pin-locked">PIN 잠금</option>
        <option value="pin-not-set">PIN 미설정</option>
        <option value="device-reset">미등록 기기로 되돌리기</option>
      </select>
    </label>
  )
}

/** 학생 로그인이 끊겨 PIN을 다시 넣은 경우 보던 학생 화면으로 돌아간다. 다른 경로는 학생 홈으로. */
function returnTo(state: unknown) {
  const from = (state as { from?: unknown } | null)?.from
  if (typeof from !== 'string' || !from.startsWith('/student/')) return '/student/home'
  return new URL(from, window.location.origin).pathname === '/student/login' ? '/student/home' : from
}
