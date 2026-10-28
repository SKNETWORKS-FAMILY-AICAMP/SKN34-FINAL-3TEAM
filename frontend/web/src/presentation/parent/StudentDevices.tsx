import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { parentApi } from '../../data/parent/api.ts'
import { useParentMutation } from '../../data/parent/queries.ts'
import { qrDemoEnabled, useDeviceAdmin, usePairingOrigins, useStudentDevices } from '../../data/studentDevice/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import {
  PIN_MAX,
  PIN_MIN,
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
    <div className="ws-grid">
      <PinSettings items={items} />
      <PairingIssue items={items} />
      <DeviceList />
    </div>
  )
}

function PinSettings({ items }: { items: Child[] }) {
  const [password, setPassword] = useState(''),
    [token, setToken] = useState(''),
    [notice, setNotice] = useState('')
  // 기존 정보 관리(AccountForms)와 같은 비밀번호 재확인 목업. 명세의 /me/reauth는 Google 재인증 기반(#45)이라
  // Google 로그인 사용자는 비밀번호가 없다. 실제 연동 때 #45 재인증 흐름으로 바꿔야 PIN을 설정할 수 있다.
  const reauth = useParentMutation(parentApi.reauth)
  return (
    <section className="ws-card" aria-labelledby="pin-h">
      <h2 id="pin-h">자녀 PIN</h2>
      <p>
        자녀가 등록된 기기에서 혼자 들어올 때 쓰는 숫자 {PIN_MIN}~{PIN_MAX}자리입니다. 같은 숫자 반복(1111)과
        이어지는 숫자(1234)는 쓸 수 없습니다. 5번 틀리면 잠기고, 여기서 다시 정해야 풀립니다.
      </p>
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          void reauth
            .mutateAsync(password)
            .then((r) => {
              setToken(r.reauthToken)
              setPassword('')
              setNotice('재확인을 완료했습니다. 5분 안에 PIN을 정해 주세요.')
            })
            .catch(() => {})
        }}
      >
        <label>
          PIN 변경 전 본인 재확인
          <input
            aria-label="PIN 재확인 비밀번호"
            type="password"
            autoComplete="current-password"
            value={password}
            required
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button className="cj-secondary" disabled={reauth.isPending}>
          본인 재확인
        </button>
        <ErrorNotice error={reauth.error} />
      </form>
      {items.map((c) => (
        <ChildPin key={c.id} child={c} token={token} onDone={setNotice} />
      ))}
      <p role="status">{notice}</p>
    </section>
  )
}

function ChildPin({ child, token, onDone }: { child: Child; token: string; onDone: (m: string) => void }) {
  const [pin, setPin] = useState(''),
    [again, setAgain] = useState(''),
    [problem, setProblem] = useState<string | null>(null)
  const { setPin: save } = useDeviceAdmin()
  const status = child.pinLocked ? '잠김 · 다시 정해야 풀려요' : child.pinSet ? '설정됨' : '아직 없음'
  return (
    <form
      className="ws-form"
      aria-label={`${child.nickname} PIN`}
      onSubmit={(e) => {
        e.preventDefault()
        const p = pinProblem(pin) ?? (pin !== again ? '두 번 입력한 PIN이 다릅니다.' : null)
        setProblem(p)
        if (p) return
        save.mutate(
          { childId: child.id, pin, reauthToken: token },
          {
            onSuccess: () => {
              setPin('')
              setAgain('')
              onDone(`${child.nickname}의 PIN을 저장했습니다.${child.pinLocked ? ' 잠금도 풀렸습니다.' : ''}`)
            },
          },
        )
      }}
    >
      <h3>
        {child.nickname} <small>· 초{child.grade}</small>
      </h3>
      <p>
        현재 상태: <strong data-pin-state={child.pinLocked ? 'locked' : child.pinSet ? 'set' : 'none'}>{status}</strong>
      </p>
      <label>
        새 PIN
        <input
          aria-label={`${child.nickname} 새 PIN`}
          type="password"
          inputMode="numeric"
          autoComplete="new-password"
          maxLength={PIN_MAX}
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
        />
      </label>
      <label>
        새 PIN 다시 입력
        <input
          aria-label={`${child.nickname} 새 PIN 확인`}
          type="password"
          inputMode="numeric"
          autoComplete="new-password"
          maxLength={PIN_MAX}
          value={again}
          onChange={(e) => setAgain(e.target.value.replace(/\D/g, ''))}
        />
      </label>
      {problem && <p role="alert">{problem}</p>}
      <button className="cj-primary" disabled={!token || save.isPending}>
        {child.pinSet ? 'PIN 바꾸기' : 'PIN 정하기'}
      </button>
      {!token && <small>본인 재확인 후 저장할 수 있습니다.</small>}
      <ErrorNotice error={save.error} />
    </form>
  )
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
              {c.nickname} · 초{c.grade}
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
