import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Pause, Play, RotateCcw } from 'lucide-react'

type VideoRef = RefObject<HTMLVideoElement | null>

export function ThemePairPlayback({ left, right, disabled, linked, setLinked }: {
  left: VideoRef; right: VideoRef; disabled: boolean; linked: boolean; setLinked: (linked: boolean) => void
}) {
  const [active, setActive] = useState(false)
  const [nativePlaying, setNativePlaying] = useState(false)
  const [error, setError] = useState('')
  const session = useRef<AbortController | null>(null)
  useLayoutEffect(() => () => session.current?.abort(), [])
  useEffect(() => {
    const a = left.current, b = right.current
    if (!a || !b || disabled) return
    const events = new AbortController()
    const options = { signal: events.signal }
    const track = () => setNativePlaying(!a.paused || !b.paused)
    function align(from: HTMLVideoElement, to: HTMLVideoElement) {
      if (Number.isFinite(to.duration) && !from.seeking && Math.abs(to.currentTime - from.currentTime) > 0.12)
        to.currentTime = Math.min(from.currentTime, to.duration)
    }
    function followPlay(to: HTMLVideoElement) {
      void to.play().catch((cause: unknown) => {
        if (!events.signal.aborted && !(cause instanceof DOMException && cause.name === 'AbortError'))
          setError('두 영상을 함께 재생하지 못했습니다. 재생 상태를 확인해 주세요.')
      })
    }
    for (const from of [a, b]) {
      const to = from === a ? b : a
      from.addEventListener('play', () => {
        track()
        if (linked && !session.current && !from.paused && to.paused) {
          align(from, to)
          followPlay(to)
        }
      }, options)
      from.addEventListener('pause', () => {
        track()
        if (linked && !session.current && from.paused && !to.paused) to.pause()
      }, options)
      from.addEventListener('seeked', () => {
        if (linked && !session.current) align(from, to)
      }, options)
    }
    if (linked && !session.current) {
      align(a, b)
      if (a.paused) b.pause()
      else if (b.paused) followPlay(b)
    }
    track()
    return () => events.abort()
  }, [left, right, linked, disabled])

  function start(restart: boolean) {
    const a = left.current, b = right.current
    setError('')
    if (!a || !b || a.error || b.error) {
      setError('두 영상 파일을 모두 불러온 뒤 함께 재생할 수 있습니다.')
      return
    }
    session.current?.abort()
    const players = [a, b]
    if (!linked) {
      if (restart || players.some(video => video.ended)) {
        for (const video of players) video.currentTime = 0
      }
      void Promise.all(players.map(video => video.play())).catch(() => {
        for (const video of players) video.pause()
        setError('두 영상을 함께 재생하지 못했습니다. 재생 상태를 확인해 주세요.')
      })
      return
    }
    const controller = new AbortController()
    session.current = controller
    const options = { signal: controller.signal }
    const end = Math.min(a.duration, b.duration)
    const startTime = restart || players.some(video => video.ended) || a.currentTime >= end ? 0 : a.currentTime
    let playing = false
    let playAttempt = 0

    function stop() {
      controller.abort()
      setActive(false)
    }
    function fail() {
      if (controller.signal.aborted) return
      stop()
      setError('함께 재생하지 못했습니다. 두 영상의 재생 상태를 확인한 뒤 다시 시도하세요.')
    }
    function pauseBoth() {
      playAttempt++
      playing = false
      for (const video of players) video.pause()
    }
    function resumeWhenReady() {
      if (playing || controller.signal.aborted || players.some(video => video.seeking || video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA)) return
      playing = true
      const attempt = ++playAttempt
      void Promise.all(players.map(video => video.play())).catch(() => {
        if (attempt === playAttempt) fail()
      })
    }
    for (const video of players) {
      const other = video === a ? b : a
      video.pause()
      video.playbackRate = 1
      video.currentTime = startTime
      video.addEventListener('waiting', pauseBoth, options)
      video.addEventListener('pause', () => {
        if (playing && video.paused && !video.ended) stop()
      }, options)
      video.addEventListener('ended', stop, options)
      video.addEventListener('error', fail, options)
      video.addEventListener('canplay', resumeWhenReady, options)
      video.addEventListener('seeked', () => {
        if (!other.seeking && Number.isFinite(other.duration) && Math.abs(other.currentTime - video.currentTime) > 0.12)
          other.currentTime = Math.min(video.currentTime, other.duration)
        resumeWhenReady()
      }, options)
      video.addEventListener('ratechange', () => {
        if (other.playbackRate !== video.playbackRate) other.playbackRate = video.playbackRate
      }, options)
    }
    // Both elements use their own media clock. Keep the right frame aligned after buffering.
    const timer = window.setInterval(() => {
      if (!playing) { resumeWhenReady(); return }
      if (!a.seeking && !b.seeking && Math.abs(a.currentTime - b.currentTime) > 0.12) b.currentTime = a.currentTime
    }, 80)
    controller.signal.addEventListener('abort', () => {
      window.clearInterval(timer)
      pauseBoth()
      session.current = null
    }, { once: true })
    setActive(true)
    resumeWhenReady()
  }

  const playing = active || nativePlaying
  return <div aria-label="동시 재생 조작">
    <div className="ws-actions"><label className="tw-check"><input type="checkbox" disabled={disabled} checked={linked} onChange={event => {
      if (session.current) {
        const playing = [left.current, right.current].filter(video => video && !video.paused)
        session.current.abort()
        setActive(false)
        void Promise.all(playing.map(video => video?.play())).catch(() => setError('영상의 재생 상태를 확인해 주세요.'))
      }
      setLinked(event.target.checked)
    }} />재생 위치 연결</label>
      <button disabled={disabled} onClick={() => {
        if (playing) {
          session.current?.abort()
          left.current?.pause()
          right.current?.pause()
          setActive(false)
        } else start(false)
      }}>{playing ? <><Pause size={14} aria-hidden="true" />함께 일시정지</> : <><Play size={14} aria-hidden="true" />함께 재생</>}</button>
      <button disabled={disabled} onClick={() => start(true)}><RotateCcw size={14} aria-hidden="true" />처음부터 함께 재생</button></div>
    {error && <p role="alert">{error}</p>}
  </div>
}
