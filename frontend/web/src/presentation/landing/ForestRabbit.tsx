import { useEffect, useId, useRef, useState } from 'react'

const clamp = (value: number) => Math.max(0, Math.min(1, value))
const ease = (value: number) => { const t = clamp(value); return t * t * (3 - 2 * t) }
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const CELL = 1254 / 4
let assetPreparation: Promise<void> | undefined

function prepareRabbitAssets() {
  assetPreparation ??= Promise.all([
    '/landing/rabbit-walk.png',
    '/landing/rabbit-turn.png',
    '/student-assets/theme-card/forest.jpg',
  ].map(async (src) => {
    const image = new Image()
    image.src = src
    await image.decode()
  })).then(() => undefined).catch((error) => {
    assetPreparation = undefined
    throw error
  })
  return assetPreparation
}

/** Illustrated motion frames, including an actual turn rather than a mirrored cutout. */
export function ForestRabbit({ active }: { active: boolean }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let cancelled = false
    void prepareRabbitAssets().then(() => {
      if (!cancelled) setReady(true)
    }, () => { /* Keep the original landscape when a decorative asset cannot load. */ })
    return () => { cancelled = true }
  }, [])
  // Unmounting discards the clock immediately; a new hover always starts at frame zero.
  return active && ready ? <RabbitVisit /> : null
}

function RabbitVisit() {
  const [time, setTime] = useState(0)
  const elapsed = useRef(0)
  const stage = useRef<SVGSVGElement>(null)
  const clipId = useId()

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (motion.matches) return
    let frame = 0
    let previous = 0
    let visible = true
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
    if (stage.current) observer.observe(stage.current)
    const tick = (now: number) => {
      if (previous && visible && !document.hidden && !motion.matches) {
        elapsed.current = (elapsed.current + Math.min(now - previous, 50)) % 10000
        setTime(elapsed.current / 1000)
      }
      previous = now
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(frame); observer.disconnect() }
  }, [])

  const arriving = time >= .4 && time < 2.5
  const turning = time >= 5.4 && time < 5.82
  const leaving = time >= 5.82 && time < 7.22
  const moving = arriving || leaving
  const progress = arriving ? clamp((time - .4) / 2.1) : time >= 2.5 && time < 7.22 ? 1 : 0
  const distance = ease(progress)
  const descent = leaving ? clamp((time - 5.82) / 1.4) : 0
  // Descend close behind the crest instead of travelling sideways across the picture.
  const x = leaving ? 193 - 24 * ease(descent) : lerp(45, 193, distance)
  const y = leaving ? 191 + 78 * (.45 * descent + .55 * descent * descent) : lerp(266, 191, distance)
  const size = leaving ? lerp(81, 60, ease(descent)) : lerp(63, 81, distance)
  const stride = moving ? Math.min(7, Math.floor(((time - (arriving ? .4 : 5.82)) % .7) / .7 * 8)) : 0
  const idle = time < 3.3 ? 12 : time < 4.1 ? 13 : time < 4.23 ? 14 : 15
  const cell = moving ? stride + (leaving ? 8 : 0) : turning ? Math.min(11, Math.floor((time - 5.4) / .42 * 12)) : idle
  const shadow = distance * (leaving ? 1 - ease(descent * 3) : 1) * .15

  return <svg ref={stage} className="lp-rabbit-stage" viewBox="0 0 480 276" preserveAspectRatio="xMidYMid slice" fill="none" aria-hidden="true">
    <defs><clipPath id={clipId}>
      {/* Foreground pixels are reused from forest.jpg; the existing hill is unchanged. */}
      <path d="M0 208 C51 196 105 184 147 186 C203 185 260 193 294 207 C336 224 368 248 395 276 H480 V276 H0Z" />
    </clipPath></defs>
    <g className="lp-rabbit-art" transform={`translate(${x} ${y}) rotate(${leaving ? -5 * ease(descent * 3) : 0})`} opacity={time < .4 || time >= 7.22 ? 0 : 1} data-motion={arriving ? 'arrive' : turning ? 'turn' : leaving ? 'leave' : 'rest'}>
      <svg x={-size / 2} y={-size * .9} width={size} height={size} viewBox={`${cell % 4 * CELL} ${Math.floor(cell / 4) * CELL} ${CELL} ${CELL}`} overflow="hidden">
        {/* Keep both decoded sheets mounted: changing href and crop together can flash
            a frame from the previous sheet during the first image decode. */}
        <image href="/landing/rabbit-walk.png" width="1254" height="1254" visibility={moving ? 'visible' : 'hidden'} />
        <image href="/landing/rabbit-turn.png" width="1254" height="1254" visibility={moving ? 'hidden' : 'visible'} />
      </svg>
    </g>
    <image href="/student-assets/theme-card/forest.jpg" width="480" height="276" clipPath={`url(#${clipId})`} />
    <ellipse cx="193" cy="190" rx="21" ry="2.7" fill="#43552b" opacity={shadow} />
  </svg>
}
