import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { studentDeviceApi } from '../../data/studentDevice/api.ts'
import { useParentMutation } from '../../data/parent/queries.ts'
import { useReauthReturn } from '../../data/reauthReturn.ts'
import { useSession } from '../auth/sessionContext.ts'
import { PasswordRecheck } from '../service/PasswordRecheck.tsx'
import { qrDemoEnabled, useDeviceAdmin, useGuardianPassword, usePairingOrigins, useStudentDevices } from '../../data/studentDevice/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import { gradeLabel } from '../../domain/grade.ts'
import {
  PIN_MAX,
  deviceExpired,
  formatPairingCode,
  pinProblem,
  remaining,
} from '../../domain/studentDevice.ts'
import type { Pairing } from '../../domain/studentDevice.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'
import '../student/pinpad.css'

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }) : '아직 사용 전'

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

/**
 * 학부모: 자녀 기기 등록·PIN·기기 목록 (FN-ACC-14, API 명세 3.11).
 * 자녀 기기에 학부모 Google 세션이 남지 않도록, 코드는 이 화면(학부모 기기)에서 발급해 자녀 기기에 입력한다.
 */
export function StudentDevices({ items }: { items: Child[] }) {
  return (
    <section className="parent-devices"><header className="parent-page-head"><h1>기기·PIN</h1><p>자녀의 PIN을 정하고 학습할 기기를 연결하세요.</p></header><div className="ws-grid">
      <PinSettings items={items} />
      <GuardianPasswordSettings />
      <PairingIssue items={items} />
      <DeviceList />
    </div></section>
  )
}

/** 학생 화면에서 잠긴 학부모 화면으로 돌아올 때 쓰는 보호자 비밀번호 (FN-ACC-05). */
function GuardianPasswordSettings() {
  const state = useGuardianPassword()
  const byPassword = useSession().session?.authMethod === 'PASSWORD'
  const [challenge, setChallenge] = useState('')
  const [grant, setGrant] = useState<{ reauthToken: string; expiresAt: string } | null>(null)
  const [notice, setNotice] = useState('')
  const [password, setPassword] = useState(''),
    [again, setAgain] = useState(''),
    [problem, setProblem] = useState<string | null>(null)
  const start = useParentMutation(studentDeviceApi.startGuardianReauth)
  const finish = useParentMutation(studentDeviceApi.finishPinReauth)
  const save = useParentMutation(studentDeviceApi.setGuardianPassword)
  useEffect(() => {
    if (!grant) return
    const timeout = window.setTimeout(() => setGrant(null), Math.max(0, Date.parse(grant.expiresAt) - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [grant])
  const token = grant?.reauthToken ?? ''
  const current = state.data
  const status = !current ? '확인 중' : current.locked ? '잠김 · 다시 정해야 풀려요' : current.set ? '설정됨' : '아직 없음'
  function begin() {
    const popup = window.open('about:blank', '_blank')
    if (!popup) { setNotice('팝업을 허용한 뒤 다시 시도해 주세요.'); return }
    popup.opener = null
    setGrant(null); setChallenge(''); setNotice('')
    void start.mutateAsync(undefined).then((result) => {
      const url = new URL(result.authorizationUrl, window.location.origin)
      if (url.protocol !== 'https:' && url.origin !== window.location.origin) throw new Error('잘못된 재인증 주소입니다.')
      popup.location.href = url.href
      setChallenge(result.challengeId)
      setNotice('Google 확인을 마치면 이 화면에서 자동으로 완료됩니다. 넘어오지 않으면 완료 확인을 눌러 주세요.')
    }).catch(() => { popup.close(); setNotice('Google 재확인을 시작하지 못했습니다.') })
  }
  function complete() {
    void finish.mutateAsync(challenge).then((value) => { setGrant(value); setNotice('재확인을 완료했습니다. 5분 안에 비밀번호를 정해 주세요.') }).catch(() => {})
  }
  useReauthReturn(challenge, !!challenge && !token && !finish.isPending, complete)
  return (
    <section className="ws-card" aria-labelledby="guardian-password-h">
      <h2 id="guardian-password-h">보호자 비밀번호</h2>
      <p>자녀가 학습을 마친 뒤 다시 로그인하지 않고 학부모 화면으로 돌아올 때 입력합니다. 자녀가 모르는 숫자 4~6자리로 정해 주세요. 5번 틀리면 잠기고, 여기서 다시 정하면 풀립니다.</p>
      <QueryFeedback query={state} />
      <form
        className="ws-form"
        aria-label="보호자 비밀번호 설정"
        onSubmit={(e) => {
          e.preventDefault()
          const p = pinProblem(password)?.replace('PIN', '비밀번호') ?? (password !== again ? '두 번 입력한 비밀번호가 다릅니다.' : null)
          setProblem(p)
          if (p) return
          save.mutate({ password, reauthToken: token }, {
            onSuccess: () => {
              setPassword(''); setAgain(''); setGrant(null); setChallenge('')
              setNotice(`보호자 비밀번호를 저장했습니다.${current?.locked ? ' 잠금도 풀렸습니다.' : ''}`)
            },
          })
        }}
      >
        <p>현재 상태: <strong data-guardian-password-state={current ? (current.locked ? 'locked' : current.set ? 'set' : 'none') : 'unknown'}>{status}</strong></p>
        {byPassword
          ? <PasswordRecheck purpose="GUARDIAN_PASSWORD" label="보호자 비밀번호 본인 확인" onGrant={(value) => { setGrant(value); if (value) setNotice('재확인을 완료했습니다. 5분 안에 비밀번호를 정해 주세요.') }} />
          : <button type="button" className="cj-secondary" disabled={start.isPending || finish.isPending} onClick={begin}>
            보호자 비밀번호 Google 본인 확인
          </button>}
        {!byPassword && challenge && !token && <button type="button" className="cj-secondary" disabled={finish.isPending} onClick={complete}>
          보호자 비밀번호 완료 확인
        </button>}
        <ErrorNotice error={start.error ?? finish.error} />
        {notice && <p role="status">{notice}</p>}
        <label>
          새 보호자 비밀번호
          <input aria-label="새 보호자 비밀번호" type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX}
            value={password} onChange={(e) => setPassword(e.target.value.replace(/\D/g, ''))} />
        </label>
        <label>
          새 보호자 비밀번호 다시 입력
          <input aria-label="새 보호자 비밀번호 확인" type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX}
            value={again} onChange={(e) => setAgain(e.target.value.replace(/\D/g, ''))} />
        </label>
        {problem && <p role="alert">{problem}</p>}
        <button className="cj-primary" disabled={!token || save.isPending || start.isPending || finish.isPending}>
          {current?.set ? '보호자 비밀번호 바꾸기' : '보호자 비밀번호 정하기'}
        </button>
        {!token && <small>본인 재확인 후 저장할 수 있습니다.</small>}
        <ErrorNotice error={save.error} />
      </form>
    </section>
  )
}

function PinSettings({ items }: { items: Child[] }) {
  const [selected, setSelected] = useState(items[0]?.id ?? '')
  const child = items.find(item => item.id === selected) ?? items[0]
  return <section className="ws-card parent-pin-settings" aria-labelledby="pin-h">
    <h2 id="pin-h">자녀 PIN</h2>
    <p>PIN을 정할 자녀를 골라 주세요. 잠긴 PIN도 다시 정하면 풀립니다.</p>
    <div className="parent-child-pills" role="tablist" aria-label="PIN 설정할 자녀">
      {items.map((item, index) => <button key={item.id} type="button" role="tab" id={`pin-tab-${item.id}`}
        aria-selected={child?.id === item.id} aria-controls={`pin-panel-${item.id}`} tabIndex={child?.id === item.id ? 0 : -1}
        onClick={() => setSelected(item.id)} onKeyDown={event => {
          const next = event.key === 'ArrowRight' ? (index + 1) % items.length : event.key === 'ArrowLeft' ? (index + items.length - 1) % items.length : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : null
          if (next === null) return
          event.preventDefault(); setSelected(items[next].id); document.getElementById(`pin-tab-${items[next].id}`)?.focus()
        }}>{item.nickname}</button>)}
    </div>
    {child ? <div role="tabpanel" id={`pin-panel-${child.id}`} aria-labelledby={`pin-tab-${child.id}`}><ChildPin key={child.id} child={child} /></div>
      : <p>계정·자녀 설정에서 자녀를 먼저 등록해 주세요.</p>}
  </section>
}

function ChildPin({ child }: { child: Child }) {
  const [pin, setPin] = useState(''), [again, setAgain] = useState(''), [notice, setNotice] = useState(''), [problem, setProblem] = useState<string | null>(null)
  const { setPin: save } = useDeviceAdmin()
  const state = child.pinLocked === true ? 'locked' : child.pinSet === true ? 'set' : child.pinSet === false ? 'none' : 'unknown'
  const status = state === 'locked' ? '잠김 · 다시 정해야 풀려요' : state === 'set' ? '설정됨' : state === 'none' ? '아직 없음' : '확인 필요'
  return <form className="ws-form" aria-label={`${child.nickname} PIN`} onSubmit={event => {
    event.preventDefault(); setNotice('')
    const error = pinProblem(pin) ?? (pin !== again ? '두 번 입력한 PIN이 다릅니다.' : null)
    setProblem(error)
    if (error) return
    save.mutate({ childId: child.id, pin }, { onSuccess: () => {
      setPin(''); setAgain(''); setNotice(`${child.nickname}의 PIN을 저장했습니다.${child.pinLocked ? ' 잠금도 풀렸습니다.' : ''}`)
    } })
  }}>
    <h3>{child.nickname} <small>· {gradeLabel(child.grade)}</small></h3>
    <p>현재 상태: <strong data-pin-state={state}>{status}</strong></p>
    <label>새 PIN<input aria-label={`${child.nickname} 새 PIN`} type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX}
      value={pin} onChange={event => setPin(event.target.value.replace(/\D/g, ''))} /></label>
    <label>새 PIN 다시 입력<input aria-label={`${child.nickname} 새 PIN 확인`} type="password" inputMode="numeric" autoComplete="new-password" maxLength={PIN_MAX}
      value={again} onChange={event => setAgain(event.target.value.replace(/\D/g, ''))} /></label>
    {problem && <p role="alert">{problem}</p>}
    <button className="cj-primary" disabled={save.isPending}>{save.isPending ? 'PIN 저장 중…' : child.pinSet ? 'PIN 바꾸기' : 'PIN 정하기'}</button>
    <ErrorNotice error={save.error} />{notice && <p role="status">{notice}</p>}
  </form>
}

function PairingIssue({ items }: { items: Child[] }) {
  const [picked, setPicked] = useState<string[]>(() => items.map((c) => c.id))
  const [pairing, setPairing] = useState<Pairing | null>(null)
  const [qr, setQr] = useState<{ url: string; src: string; error: boolean } | null>(null)
  const [selectedOrigin, setSelectedOrigin] = useState('')
  const addresses = usePairingOrigins()
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
  const suggested = addresses.data?.origins.find((a) => !/docker|vethernet|wsl|virtual|loopback/i.test(a.label))
    ?? addresses.data?.origins[0]
  const origin = selectedOrigin || (local && qrDemoEnabled ? suggested?.origin : undefined) || window.location.origin
  const registrationUrl = pairing ? `${origin}/student/login?code=${encodeURIComponent(pairing.pairingCode)}` : ''
  const { pairing: issue } = useDeviceAdmin()
  const now = useNow(!!pairing)
  const left = pairing ? remaining(pairing.expiresAt, now) : null
  useEffect(() => {
    if (!pairing) return
    let active = true
    void QRCode.toString(registrationUrl, { type: 'svg', margin: 4, width: 224 }).then((svg) => {
      if (active) setQr({ url: registrationUrl, src: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`, error: false })
    }).catch(() => { if (active) setQr({ url: registrationUrl, src: '', error: true }) })
    return () => {
      active = false
    }
  }, [pairing, registrationUrl])
  return (
    <section className="ws-card" aria-labelledby="pairing-h">
      <h2 id="pairing-h">자녀 기기 등록</h2>
      <p>
        자녀 태블릿의 기본 카메라로 QR을 찍어 주세요. 열린 화면에서 기기 이름을 적고 등록하면,
        다음부터는 자녀 PIN으로 들어갈 수 있습니다. 코드를 직접 입력해도 됩니다.
      </p>
      {qrDemoEnabled && (
        <div className="ws-form">
          <p>두 기기 QR 시연 · 노트북과 태블릿을 같은 Wi-Fi에 연결해 주세요. 가상 정보만 사용합니다.</p>
          <label>
            QR에서 열 주소
            <select aria-label="QR에서 열 주소" value={origin} onChange={(e) => setSelectedOrigin(e.target.value)}>
              <option value={window.location.origin}>{window.location.origin}{local ? ' (이 컴퓨터에서만)' : ' (현재 주소)'}</option>
              {addresses.data?.origins.filter((a) => a.origin !== window.location.origin).map((a) => (
                <option key={a.origin} value={a.origin}>{a.origin} · {a.label}</option>
              ))}
            </select>
          </label>
          {local && origin === window.location.origin && <p role="status">다른 기기에서 찍으려면 Wi-Fi 주소를 골라 주세요.</p>}
          <ErrorNotice error={addresses.error} retry={() => void addresses.refetch()} />
        </div>
      )}
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          setQr(null)
          issue.mutate(picked, { onSuccess: setPairing })
        }}
      >
        <fieldset>
          <legend>이 기기에서 공부할 자녀</legend>
          {items.map((c) => (
            <label key={c.id}>
              <input
                type="checkbox"
                checked={picked.includes(c.id)}
                onChange={(e) =>
                  setPicked((p) => (e.target.checked ? [...p, c.id] : p.filter((id) => id !== c.id)))
                }
              />
              {c.nickname} · {gradeLabel(c.grade)}
            </label>
          ))}
        </fieldset>
        <button className="cj-primary" disabled={!picked.length || issue.isPending}>
          {pairing ? '새 코드 만들기' : '등록 코드 만들기'}
        </button>
        <ErrorNotice error={issue.error} />
      </form>
      {pairing && (
        <div className="pairing-code" aria-live="polite">
          <div>
            <p>등록 코드 (한 번만 사용)</p>
            <strong aria-label={`등록 코드 ${pairing.pairingCode.split('').join(' ')}`}>
              {formatPairingCode(pairing.pairingCode)}
            </strong>
            <p role="status">
              {left ? `남은 시간 ${left}` : '코드 시간이 지났습니다. 새 코드를 만들어 주세요.'}
            </p>
          </div>
          {qr?.url === registrationUrl && qr.src && left && <img src={qr.src} alt="자녀 기기 등록 QR 코드 (위 코드와 같은 내용)" width="224" height="224" />}
          {left && <a href={registrationUrl} target="_blank" rel="noreferrer">등록 화면 열기</a>}
          {qr?.url === registrationUrl && qr.error && <p role="status">QR을 만들지 못했습니다. 위 등록 코드를 직접 입력해 주세요.</p>}
        </div>
      )}
    </section>
  )
}

function DeviceList() {
  const devices = useStudentDevices()
  const { revoke } = useDeviceAdmin()
  const [confirming, setConfirming] = useState<string | null>(null)
  const now = useNow(false) // 만료 표시는 목록을 받은 시점 기준. 1분 단위 갱신은 필요하지 않다.
  return (
    <section className="ws-card" aria-labelledby="devices-h">
      <h2 id="devices-h">등록된 기기</h2>
      <QueryFeedback query={devices} />
      {devices.data && !devices.data.length && <p>아직 등록된 기기가 없습니다.</p>}
      {!!devices.data?.length && (
        <div className="ws-table-wrap">
          <table className="ws-table">
            <thead>
              <tr>
                <th scope="col">기기 이름</th>
                <th scope="col">자녀</th>
                <th scope="col">마지막 사용</th>
                <th scope="col">만료</th>
                <th scope="col">관리</th>
              </tr>
            </thead>
            <tbody>
              {devices.data.map((d) => (
                <tr key={d.deviceId}>
                  <td>{d.label}</td>
                  <td>{d.children.map((c) => c.nickname).join(', ')}</td>
                  <td>{when(d.lastUsedAt)}</td>
                  <td>
                    {when(d.expiresAt)}
                    {deviceExpired(d, now) && <strong> · 만료됨</strong>}
                  </td>
                  <td>
                    {confirming === d.deviceId ? (
                      <span role="group" aria-label={`${d.label} 해제 확인`}>
                        <button
                          className="cj-primary"
                          disabled={revoke.isPending}
                          onClick={() => revoke.mutate(d.deviceId, { onSettled: () => setConfirming(null) })}
                        >
                          해제
                        </button>{' '}
                        <button className="cj-secondary" onClick={() => setConfirming(null)}>
                          취소
                        </button>
                      </span>
                    ) : (
                      <button
                        className="cj-secondary"
                        aria-label={`${d.label} 등록 해제`}
                        onClick={() => setConfirming(d.deviceId)}
                      >
                        등록 해제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>해제한 기기에서는 PIN이 맞아도 들어올 수 없습니다. 이미 열려 있던 학습 화면은 로그인 시간이 끝날 때까지 유지됩니다.</p>
      <ErrorNotice error={revoke.error} />
    </section>
  )
}
