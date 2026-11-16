import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { Delete } from 'lucide-react'
import { PIN_MAX, PIN_MIN } from '../../domain/studentDevice.ts'
import './pinpad.css'

/**
 * 저학년용 PIN 숫자 키패드. 큰 버튼 + 입력 자리 점 표시.
 * 실제 키보드 숫자·Backspace·Enter도 받는다. 화면에 나타날 때 이 영역에 포커스를 두어 바로 입력되게 하고,
 * 전역 단축키는 쓰지 않는다(이 영역 밖 입력란에는 영향 없음).
 *
 * 배치(#648, 설계 캔버스 Login): 1~9, 지우기·0·다시, 그 아래 넓은 주황 '확인'. 캔버스는 '들어가기 →'지만
 * 시험·실서버 E2E·QR 시연이 키패드 묶음 안의 '확인' 이름으로 누르므로 이름은 '확인' 그대로 둔다(화살표는 읽지 않음).
 * message는 점과 키 사이에 보이는 안내(틀린 PIN 등).
 */
export function PinPad({
  label,
  busy,
  message,
  onSubmit,
}: {
  label: string
  busy?: boolean
  message?: ReactNode
  onSubmit: (pin: string) => void
}) {
  const [pin, setPin] = useState('')
  const area = useRef<HTMLDivElement>(null)
  useEffect(() => {
    area.current?.focus({ preventScroll: true })
  }, [])
  const add = (d: string) => setPin((p) => (p.length < PIN_MAX ? p + d : p))
  const back = () => setPin((p) => p.slice(0, -1))
  const submit = () => {
    if (pin.length < PIN_MIN || busy) return
    onSubmit(pin)
    setPin('')
  }
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (/^\d$/.test(e.key)) {
      e.preventDefault()
      add(e.key)
    } else if (e.key === 'Backspace') {
      e.preventDefault()
      back()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }
  return (
    <div className="pin-pad" ref={area} tabIndex={-1} onKeyDown={onKeyDown}>
      <div className="pin-dots" role="status" aria-live="polite" aria-label={`${label} ${pin.length}자리 입력됨`}>
        {Array.from({ length: PIN_MAX }, (_, i) => (
          <span key={i} className={i < pin.length ? 'on' : i < PIN_MIN ? '' : 'optional'} aria-hidden="true" />
        ))}
      </div>
      {message}
      <div className="pin-keys" role="group" aria-label={label}>
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
          <button key={d} type="button" onClick={() => add(d)} disabled={busy}>
            {d}
          </button>
        ))}
        <button type="button" className="pin-fn pin-back" onClick={back} disabled={busy || !pin} aria-label="한 칸 지우기">
          <Delete aria-hidden="true" />
          <span>지우기</span>
        </button>
        <button type="button" onClick={() => add('0')} disabled={busy}>
          0
        </button>
        <button type="button" className="pin-fn" onClick={() => setPin('')} disabled={busy || !pin} aria-label="다시 쓰기, 모두 지우기">
          다시
        </button>
        <button type="button" className="pin-ok" onClick={submit} disabled={busy || pin.length < PIN_MIN}>
          {busy ? '확인 중' : '확인'}
          <span aria-hidden="true"> →</span>
        </button>
      </div>
      <p className="pin-help">숫자 {PIN_MIN}~{PIN_MAX}자리를 누르고 ‘확인’을 눌러요.</p>
    </div>
  )
}
