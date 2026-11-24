import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { cameraTransform, captionAt, readThemeMotion } from '../../domain/themeMotion.ts'
import { MotionEffects } from './MotionEffects.tsx'
import { useReducedMotion } from './useReducedMotion.ts'
import './theme-motion.css'

/**
 * 장면 움직임 재생기(형식 v1, domain/themeMotion.ts). 관리자 테마 초안 미리보기(#441)와 학생 시작·끝 이야기(#440)가 쓴다.
 * - 영상이 있으면 영상 위에 컷 문구(captions). 없으면 그림에 전환(transition.kind)·카메라 이동·효과(effects)를 입히고 문구는 시간에 맞춰
 * - 살펴보기 지점(spots)은 관리자 미리보기에서만(showSpots). 학생 화면에는 넣지 않음(사용자 결정 2026-11-13)
 * - still이거나 기기 '동작 줄이기'면 정지 그림만(영상은 자동 재생하지 않고 직접 재생)
 * - 영상을 못 불러오면 그림으로, 그림도 못 불러오면 "그림을 불러오지 못했어요" 칸(onImageError·onVideoError로 부르는 쪽도 앎)
 * 움직임이 형식 v1이 아니면 움직임 없이 그림·영상만 보인다.
 */
export function ThemeMotionPlayer({ imageUrl, videoUrl, motion: raw, label, still = false, showSpots = false, onEnded, onImageError, onVideoError, videoRef, stillSeconds, paused, autoPlay = true }: {
  imageUrl: string | null
  videoUrl: string | null
  motion: unknown
  label: string
  still?: boolean
  showSpots?: boolean
  videoRef?: RefObject<HTMLVideoElement | null>
  autoPlay?: boolean
  /** In a playlist, hold a still image for this long after it loads. */
  stillSeconds?: number
  /** 이어보기에서 영상 제어 버튼으로 그림 타이머와 카메라도 멈춘다. */
  paused?: boolean
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
  const [loadedImage, setLoadedImage] = useState<string | null>(null)
  const onEndedRef = useRef(onEnded)
  useEffect(() => { onEndedRef.current = onEnded }, [onEnded])
  const pausedRef = useRef(!!paused)
  const setImagePaused = useRef<((pause: boolean) => void) | null>(null)
  useEffect(() => {
    pausedRef.current = !!paused
    setImagePaused.current?.(!!paused)
  }, [paused])
  const length = Math.max(motion?.camera?.seconds ?? 0, ...(motion?.captions.map((c) => c.end) ?? [0]))

  // 그림 장면: 카메라 이동과 문구 시간
  useEffect(() => {
    if (!image || (video && !reduce) || (stillSeconds !== undefined && loadedImage !== image)) return
    const stationary = reduce || !motion || (stillSeconds !== undefined && !length)
    const duration = stationary ? stillSeconds : length
    if (duration === undefined) return
    const el = img.current, cam = stationary ? null : motion.camera
    const animation = el && cam
      ? el.animate([{ transform: cameraTransform(cam.from) }, { transform: cameraTransform(cam.to) }],
        { duration: cam.seconds * 1000, easing: 'ease-in-out', fill: 'forwards' })
      : null
    let elapsed = 0, started: number | null = null, tick = 0, end = 0
    let finished = false
    function stopClock() {
      if (started !== null) elapsed += performance.now() - started
      started = null
      window.clearInterval(tick)
      window.clearTimeout(end)
    }
    const changePaused = (pause: boolean) => {
      if (finished) return
      if (pause) { stopClock(); animation?.pause(); return }
      if (started !== null) return
      started = performance.now()
      if (animation?.playState === 'paused') animation.play()
      if (!stationary) tick = window.setInterval(() => setSeconds((elapsed + performance.now() - started!) / 1000), 200)
      end = window.setTimeout(() => {
        stopClock()
        finished = true
        if (!stationary) setSeconds(duration)
        onEndedRef.current?.()
      }, Math.max(0, duration * 1000 - elapsed))
    }
    setImagePaused.current = changePaused
    changePaused(pausedRef.current)
    return () => { setImagePaused.current = null; animation?.cancel(); stopClock() }
  }, [reduce, video, image, motion?.camera?.seconds, length, run, stillSeconds, loadedImage]) // eslint-disable-line react-hooks/exhaustive-deps

  const caption = reduce ? null : captionAt(motion, seconds)
  const transition = !reduce && motion ? motion.transition : null
  if (!image && !video)
    return (
      <div className="tm-player tm-empty" role="img" aria-label={imageUrl || videoUrl ? `${label} 그림을 불러오지 못했어요` : `${label} 그림 없음`}>
        {imageUrl || videoUrl ? '그림을 불러오지 못했어요' : '그림 없음'}
      </div>
    )
  return (
    <figure className="tm-player" data-motion={reduce ? 'static' : 'animated'} data-paused={paused || undefined}>
      <div className="tm-stage" key={run}>
        <div className="tm-shot" data-transition={transition?.kind} style={transition ? { animationDuration: `${transition.seconds}s` } : undefined}>
          {video && (!reduce || !image) ? (
            <video ref={videoRef} src={video} poster={image ?? undefined} controls muted playsInline autoPlay={autoPlay && paused === undefined && !reduce} aria-label={label.endsWith('영상') ? label : `${label} 영상`}
              onTimeUpdate={(e) => setSeconds(e.currentTarget.currentTime)} onEnded={onEnded}
              onError={() => { setBadVideo(videoUrl); onVideoError?.() }} />
          ) : (
            <img ref={img} src={image!} alt={label.endsWith('장면') ? label : `${label} 장면`} onLoad={stillSeconds === undefined ? undefined : () => setLoadedImage(image)} onError={() => { setBadImage(imageUrl); onImageError?.() }} />
          )}
          {!reduce && !video && motion && motion.effects.length > 0 && <MotionEffects effects={motion.effects} />}
        </div>
        {showSpots && motion?.spots.map((s, i) => (
          <span key={i} className="tm-spot" data-evidence={s.evidence || undefined} style={{ left: `${s.x}%`, top: `${s.y}%` }}
            title={s.line ? `${s.label}: ${s.line}` : s.label}>{i + 1}</span>
        ))}
        {caption && <figcaption className="tm-caption" aria-live="polite">{caption}</figcaption>}
      </div>
      {paused === undefined && !reduce && !video && motion && (motion.camera || motion.captions.length > 0) && (
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
