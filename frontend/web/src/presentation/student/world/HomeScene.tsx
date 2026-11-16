import { useState } from 'react'
import type { CompanionId, Theme } from '../../../domain/studentLook.ts'
import { Companion } from './Companion.tsx'
import { SCENE } from './homeScene.ts'
import { SpeechBubble } from './SpeechBubble.tsx'

/**
 * 홈 "우리 집" 장면(#589·#648). 화면 테마마다 생성한 배경 그림(캐릭터·글자 없음) 위에 동행 캐릭터와 말풍선을 얹고,
 * 그림 속 집을 누르면 내 방으로 간다. 그림 출처·프롬프트는 docs/report/frontend.md #648 절.
 * 위치 값(그림마다 잰 발판 가운데·집 영역)은 homeScene.ts(꾸미기 미리 보기와 같이 씀).
 */

export function HomeScene({
  t,
  companion,
  worn,
  lines,
  onRoom,
}: {
  t: Theme
  companion: CompanionId
  worn: Partial<Record<'HAT' | 'OUTFIT' | 'ACCESSORY', string>>
  /** 말풍선 대사. 캐릭터를 누를 때마다 다음 줄 */
  lines: string[]
  onRoom: () => void
}) {
  const [talk, setTalk] = useState(0)
  const s = SCENE[t.id]
  const line = lines.length ? lines[talk % lines.length] : ''
  return (
    <section className="sh-scene" aria-label={`우리 집 · ${t.name} ${t.place}`}>
      {/* 장면 틀은 3:2, 그림은 원래 비율(10:8)로 가운데에 두고 위아래를 잘라 보인다. 위치 값은 그림 기준이라 sh-scene-art 안에 둔다 */}
      <div className="sh-scene-art">
      <img className="sh-scene-bg" src={`/student-assets/home/${t.id}.jpg`} alt="" />
      <button
        type="button"
        className="sh-house"
        aria-label="우리 집 · 내 방으로 가기"
        style={{ left: `${s.house[0]}%`, top: `${s.house[1]}%`, width: `${s.house[2]}%`, height: `${s.house[3]}%` }}
        onClick={onRoom}
      >
        <span className="sh-house-tag" aria-hidden="true">
          내 방 →
        </span>
      </button>
      <div className="sh-buddy" style={{ left: `${s.cx - 9}%`, bottom: `${s.cb}%` }}>
        <div className="sh-bob">
          <span className="sh-shadow" aria-hidden="true" />
          {line && (
            <div className="sh-bubble-pos">
              <SpeechBubble className="sh-bubble" role="status">
                {line}
              </SpeechBubble>
            </div>
          )}
          <button
            type="button"
            className="sh-pet"
            aria-label="내 캐릭터에게 말 걸기"
            onClick={() => setTalk((n) => n + 1)}
          >
            <Companion kind={companion} size={150} worn={worn} />
          </button>
        </div>
      </div>
      </div>
      <span className="sh-scene-tag">
        우리 집 · {t.name} {t.place}
      </span>
    </section>
  )
}
