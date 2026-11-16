import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { effectParticles } from '../../domain/themeMotion.ts'
import type { MotionEffect } from '../../domain/themeMotion.ts'
import './theme-motion.css'

/**
 * 장면 효과 층(움직임 형식 v1 effects). 그림 위에 겹쳐 입자를 계약 단위대로 움직인다:
 * 크기 = 그림 너비 %, 빠르기 = 초당 그림 높이 %, 방향 = 도(0 아래, domain/themeMotion.ts effectVector).
 * 그림 크기를 재야 해서 부모(그림을 감싼 상자)는 position이 있어야 한다. 움직임 줄이기면 부르는 쪽이 그리지 않는다.
 */
export function MotionEffects({ effects }: { effects: MotionEffect[] }) {
  const layer = useRef<HTMLSpanElement>(null)
  const [box, setBox] = useState<{ w: number; h: number } | null>(null)
  useEffect(() => {
    const el = layer.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      const next = r.width > 0 && r.height > 0 ? { w: Math.round(r.width), h: Math.round(r.height) } : null
      setBox((prev) => (prev?.w === next?.w && prev?.h === next?.h ? prev : next))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return (
    <span ref={layer} className="tm-effects" aria-hidden="true">
      {box && effects.map((fx, i) => effectParticles(fx, box.w, box.h).map((p, n) => (
        <i key={`${i}-${n}`} className="tm-fx" data-shape={fx.shape}
          style={{
            width: p.size, height: p.size, color: fx.color, opacity: fx.opacity,
            animationDuration: `${p.seconds.toFixed(2)}s`, animationDelay: `${p.delay.toFixed(2)}s`,
            '--x0': `${(p.x0 - p.size / 2).toFixed(1)}px`, '--y0': `${(p.y0 - p.size / 2).toFixed(1)}px`,
            '--x1': `${(p.x1 - p.size / 2).toFixed(1)}px`, '--y1': `${(p.y1 - p.size / 2).toFixed(1)}px`,
          } as CSSProperties} />
      )))}
    </span>
  )
}
