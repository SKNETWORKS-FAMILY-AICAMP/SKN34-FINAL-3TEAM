import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { CompanionId } from '../../../domain/studentLook.ts'
import type { wornAssets } from '../../../domain/retention.ts'
import { Companion } from './Companion.tsx'
import { faceStyle, roomFaces, RUG, slotTransform } from './roomArt.ts'
import type { RoomLook } from './roomArt.ts'
import { skinOf, wallpaperOf } from './roomAssets.ts'
import type { RoomSlot } from './roomAssets.ts'
import { glowClass } from './roomGlow.ts'
import './room.css'

/** 내 방과 같은 시점(StudentRoom START) */
const VIEW = { rx: -24, ry: -30 }
/**
 * 꾸미기 "내 방 가구" 탭 미리 보기(사용자 의견 2026-11-16 "뭐가 어떻게 변하는지 보여야지"): 내 방과 같은 그림·시점의
 * 작은 방. 걷기·이름표·액자 고르기 없이 그림만 그리고, 칸 폭에 맞춰 줄인다. 고른 칸의 가구는 잠깐 반짝인다.
 */
export function RoomScene({ look, glow, companion, worn, label }: {
  look: RoomLook
  glow: { slot: RoomSlot; n: number } | null
  companion: CompanionId
  worn: ReturnType<typeof wornAssets>
  label: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(420)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setW(el.clientWidth || 420)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  // 무대 1400×780 중 방이 보이는 위쪽 약 86%만 담는다(아래는 바닥만 이어짐)
  const scale = w / 1400
  const faceCamera = (x: number, y: number, z: number) => `translate3d(${x}px,${y}px,${z}px) rotateY(${-VIEW.ry}deg) rotateX(${-VIEW.rx}deg)`
  const frameWood = skinOf('WALL', look.wall).set[0]
  const boardGlow = glowClass('WALL', glow)
  return (
    <div ref={ref} className="st-room-scene-mini" role="img" aria-label={label}
      style={{ height: Math.round(780 * 0.86 * scale), background: wallpaperOf(look.wallpaper).swatch, '--st-frame-wood': frameWood } as CSSProperties}>
      <div className="st-room-stage is-fixed" style={{ transform: `scale(${scale.toFixed(4)})` }} aria-hidden="true">
        <div className="st-room-world" style={{ transform: `rotateX(${VIEW.rx}deg) rotateY(${VIEW.ry}deg)` }}>
          {roomFaces(look).map((f) => {
            const g = glowClass(f.part, glow)
            return <div key={f.key + g.suffix} className={`st-f${g.cls}`} style={faceStyle(f)} />
          })}
          {/* 추억의 벽 액자 두 장(빈 액자): 추억의 벽 스킨이 바꾸는 액자 테두리 색이 보이게 */}
          {[0, 4].map((i) => (
            <div key={`frame${i}${boardGlow.suffix}`} className={`st-f st-room-slot is-filled st-mini-frame${boardGlow.cls}`}
              style={{ transform: slotTransform(i, true) }} />
          ))}
          <div className="st-f st-room-char" style={{ transform: faceCamera(RUG.x, 0, RUG.z) }}>
            <Companion kind={companion} size={140} decorative worn={worn} />
          </div>
        </div>
      </div>
    </div>
  )
}
