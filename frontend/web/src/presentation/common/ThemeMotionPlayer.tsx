import { useEffect, useRef, useState } from 'react'
import { captionAt, readThemeMotion } from '../../domain/themeMotion.ts'
import type { MotionPoint } from '../../domain/themeMotion.ts'
import { MotionEffects } from './MotionEffects.tsx'
import { useReducedMotion } from './useReducedMotion.ts'
import './theme-motion.css'

/** 카메라 위치(그림 % 좌표·확대)를 그림 변환으로. 확대한 만큼만 중심을 옮겨 가장자리가 비지 않게 한다 */
const cameraTransform = (p: MotionPoint) => {
  const room = (1 - 1 / p.zoom) * 50
  const dx = Math.max(-room, Math.min(room, 50 - p.x)), dy = Math.max(-room, Math.min(room, 50 - p.y))
  return `scale(${p.zoom}) translate(${dx}%, ${dy}%)`
}

/**
 * 장면 움직임 재생기(형식 v1, domain/themeMotion.ts). 관리자 테마 초안 미리보기(#441)와 학생 시작·끝 이야기(#440)가 쓴다.
 * - 영상이 있으면 영상 위에 컷 문구(captions). 없으면 그림에 전환(transition.kind)·카메라 이동·효과(effects)를 입히고 문구는 시간에 맞춰
 * - 살펴보기 지점(spots)은 관리자 미리보기에서만(showSpots). 학생 화면에는 넣지 않음(사용자 결정 2026-11-13)
 * - still이거나 기기 '동작 줄이기'면 정지 그림만(영상은 자동 재생하지 않고 직접 재생)
 * - 영상을 못 불러오면 그림으로, 그림도 못 불러오면 "그림을 불러오지 못했어요" 칸(onImageError·onVideoError로 부르는 쪽도 앎)
 * 움직임이 형식 v1이 아니면 움직임 없이 그림·영상만 보인다.
 */
export function ThemeMotionPlayer({ imageUrl, videoUrl, motion: raw, label, still = false, showSpots = false, onEnded, onImageError, onVideoError }: {
  imageUrl: string | null
  videoUrl: string | null
  motion: unknown
  label: string
  still?: boolean
  showSpots?: boolean
  /** 영상이 끝까지 재생되거나 그림 장면의 움직임·문구가 끝나면(학생 이야기 화면이 이야기로 넘어갈 때, #440) */
  onEnded?: () => void
  /** 그림을 못 불러왔을 때(학생 이야기 화면은 글만으로 바꿈, #440) */
  onImageError?: () => void
  /** 영상을 못 불러왔을 때(그림이 있으면 그림으로 이어 감) */
  onVideoError?: () => void
}) {
  const motion = readThemeMotion(raw)
  const reduce = useReducedMotion() || still
  const [seconds, setSeconds] = useState(0)
  const [run, setRun] = useState(0)
  // 못 불러온 주소(주소가 바뀌면 다시 시도)
  const [badImage, setBadImage] = useState<string | null>(null)
  const [badVideo, setBadVideo] = useState<string | null>(null)
  const image = imageUrl && imageUrl !== badImage ? imageUrl : null
  const video = videoUrl && videoUrl !== badVideo ? videoUrl : null
  const img = useRef<HTMLImageElement>(null)
  const onEndedRef = useRef(onEnded)
  useEffect(() => { onEndedRef.current = onEnded }, [onEnded])
  const length = Math.max(motion?.camera?.seconds ?? 0, ...(motion?.captions.map((c) => c.end) ?? [0]))

  // 그림 장면: 카메라 이동과 문구 시간
  useEffect(() => {
    if (reduce || video || !image || !motion) return
    const el = img.current, cam = motion.camera
    const animation = el && cam
      ? el.animate([{ transform: cameraTransform(cam.from) }, { transform: cameraTransform(cam.to) }],
        { duration: cam.seconds * 1000, easing: 'ease-in-out', fill: 'forwards' })
      : null
    const started = performance.now()
    const timer = window.setInterval(() => {
      const now = (performance.now() - started) / 1000
      setSeconds(now)
      // 그림 장면도 영상처럼 끝을 알린다(학생 시작·끝 이야기가 화면 가득 재생 뒤 이야기로 넘어갈 때, 2026-11-16)
      if (now > length) { window.clearInterval(timer); onEndedRef.current?.() }
    }, 200)
    return () => { animation?.cancel(); window.clearInterval(timer) }
  }, [reduce, video, image, motion?.camera?.seconds, length, run]) // eslint-disable-line react-hooks/exhaustive-deps

  const caption = reduce ? null : captionAt(motion, seconds)
  const transition = !reduce && motion ? motion.transition : null
  if (!image && !video)
    return (
      <div className="tm-player tm-empty" role="img" aria-label={imageUrl || videoUrl ? `${label} 그림을 불러오지 못했어요` : `${label} 그림 없음`}>
        {imageUrl || videoUrl ? '그림을 불러오지 못했어요' : '그림 없음'}
      </div>
    )
  return (
    <figure className="tm-player" data-motion={reduce ? 'static' : 'animated'}>
      <div className="tm-stage" key={run}>
        <div className="tm-shot" data-transition={transition?.kind} style={transition ? { animationDuration: `${transition.seconds}s` } : undefined}>
          {video && (!reduce || !image) ? (
            <video src={video} poster={image ?? undefined} controls muted playsInline autoPlay={!reduce} aria-label={`${label} 영상`}
              onTimeUpdate={(e) => setSeconds(e.currentTarget.currentTime)} onEnded={onEnded}
              onError={() => { setBadVideo(videoUrl); onVideoError?.() }} />
          ) : (
            <img ref={img} src={image!} alt={`${label} 장면`} onError={() => { setBadImage(imageUrl); onImageError?.() }} />
          )}
          {!reduce && !video && motion && motion.effects.length > 0 && <MotionEffects effects={motion.effects} />}
        </div>
        {showSpots && motion?.spots.map((s, i) => (
          <span key={i} className="tm-spot" data-evidence={s.evidence || undefined} style={{ left: `${s.x}%`, top: `${s.y}%` }}
            title={s.line ? `${s.label}: ${s.line}` : s.label}>{i + 1}</span>
        ))}
        {caption && <figcaption className="tm-caption" aria-live="polite">{caption}</figcaption>}
      </div>
      {!reduce && !video && motion && (motion.camera || motion.captions.length > 0) && (
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
