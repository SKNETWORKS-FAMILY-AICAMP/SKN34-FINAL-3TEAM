import { useEffect, useRef, useState } from 'react'
import { captionAt, readThemeMotion } from '../../domain/themeMotion.ts'
import type { MotionPoint } from '../../domain/themeMotion.ts'
import './theme-motion.css'

const prefersReduced = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
/** 카메라 위치(그림 % 좌표·확대)를 그림 변환으로. 확대한 만큼만 중심을 옮겨 가장자리가 비지 않게 한다 */
const cameraTransform = (p: MotionPoint) => {
  const room = (1 - 1 / p.zoom) * 50
  const dx = Math.max(-room, Math.min(room, 50 - p.x)), dy = Math.max(-room, Math.min(room, 50 - p.y))
  return `scale(${p.zoom}) translate(${dx}%, ${dy}%)`
}

/**
 * 장면 움직임 재생기(형식 v1, domain/themeMotion.ts). 관리자 테마 초안 미리보기(#441)에서 쓰고 학생 이야기 화면(#440)도 쓸 수 있다.
 * - 영상이 있으면 영상 위에 컷 문구(captions)를 띄움. 없으면 그림에 카메라 이동·전환·효과를 입히고 문구는 시간에 맞춰
 * - 살펴보기 지점(spots)은 그림 위 표시(showSpots)
 * - still이거나 기기 '동작 줄이기'면 정지 그림만(영상은 자동 재생하지 않고 직접 재생)
 * 움직임이 형식 v1이 아니면 움직임 없이 그림·영상만 보인다.
 */
export function ThemeMotionPlayer({ imageUrl, videoUrl, motion: raw, label, still = false, showSpots = false }: {
  imageUrl: string | null
  videoUrl: string | null
  motion: unknown
  label: string
  still?: boolean
  showSpots?: boolean
}) {
  const motion = readThemeMotion(raw)
  const reduce = still || prefersReduced()
  const [seconds, setSeconds] = useState(0)
  const [run, setRun] = useState(0)
  const image = useRef<HTMLImageElement>(null)
  const length = Math.max(motion?.camera?.seconds ?? 0, ...(motion?.captions.map((c) => c.end) ?? [0]))

  // 그림 장면: 카메라 이동과 문구 시간
  useEffect(() => {
    if (reduce || videoUrl || !motion) return
    const el = image.current, cam = motion.camera
    const animation = el && cam
      ? el.animate([{ transform: cameraTransform(cam.from) }, { transform: cameraTransform(cam.to) }],
        { duration: cam.seconds * 1000, easing: 'ease-in-out', fill: 'forwards' })
      : null
    const started = performance.now()
    const timer = window.setInterval(() => {
      const now = (performance.now() - started) / 1000
      setSeconds(now)
      if (now > length) window.clearInterval(timer)
    }, 200)
    return () => { animation?.cancel(); window.clearInterval(timer) }
  }, [reduce, videoUrl, motion?.camera?.seconds, length, run]) // eslint-disable-line react-hooks/exhaustive-deps

  const caption = reduce ? null : captionAt(motion, seconds)
  const fade = !reduce && motion?.transition ? `${motion.transition.seconds}s` : undefined
  if (!imageUrl && !videoUrl) return <div className="tm-player tm-empty" role="img" aria-label={`${label} 그림 없음`}>그림 없음</div>
  return (
    <figure className="tm-player" data-motion={reduce ? 'static' : 'animated'}>
      <div className="tm-stage" style={fade ? { animationDuration: fade } : undefined} key={run}>
        {videoUrl && (!reduce || !imageUrl) ? (
          <video src={videoUrl} poster={imageUrl ?? undefined} controls muted playsInline autoPlay={!reduce} aria-label={`${label} 영상`}
            onTimeUpdate={(e) => setSeconds(e.currentTarget.currentTime)} />
        ) : (
          <img ref={image} src={imageUrl!} alt={`${label} 장면`} />
        )}
        {!reduce && !videoUrl && motion?.effects.map((fx, i) => (
          <span key={i} className="tm-effect" data-direction={fx.direction} aria-hidden="true">
            {Array.from({ length: Math.min(fx.count, 24) }, (_, n) => (
              <i key={n} style={{ left: `${(n * 37) % 100}%`, animationDelay: `${(n % 7) * 0.4}s`, animationDuration: `${Math.max(1.5, 6 / (fx.speed || 1))}s`,
                width: fx.size, height: fx.size, background: fx.color, opacity: fx.opacity, borderRadius: fx.shape === 'square' ? 2 : '50%' }} />
            ))}
          </span>
        ))}
        {showSpots && motion?.spots.map((s, i) => (
          <span key={i} className="tm-spot" data-evidence={s.evidence || undefined} style={{ left: `${s.x}%`, top: `${s.y}%` }}
            title={s.line ? `${s.label}: ${s.line}` : s.label}>{i + 1}</span>
        ))}
        {caption && <figcaption className="tm-caption" aria-live="polite">{caption}</figcaption>}
      </div>
      {!reduce && !videoUrl && motion && (motion.camera || motion.captions.length > 0) && (
        <button type="button" className="tm-replay" onClick={() => { setSeconds(0); setRun((n) => n + 1) }}>움직임 다시 보기</button>
      )}
      {showSpots && motion && motion.spots.length > 0 && (
        <ol className="tm-spot-list" aria-label={`${label} 살펴보기 지점`}>
          {motion.spots.map((s, i) => <li key={i}><b>{s.label}</b>{s.evidence && <em> · 증거</em>}{s.line && ` — ${s.line}`}</li>)}
        </ol>
      )}
    </figure>
  )
}
