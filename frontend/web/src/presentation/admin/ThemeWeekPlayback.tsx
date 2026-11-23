import { useEffect, useRef, useState } from 'react'
import { Pause, Play, RotateCcw } from 'lucide-react'
import { versionName } from '../../domain/admin/sceneVersions.ts'
import { ThemeMotionPlayer } from '../common/ThemeMotionPlayer.tsx'
import { useReducedMotion } from '../common/useReducedMotion.ts'
import type { StoryboardScenes } from '../../data/admin/themeReviewQueries.ts'
import { ThemeStoryboard } from './ThemeStoryboard.tsx'
import './theme-week-playback.css'

export function ThemeWeekPlayback({ scenes, still, onClose }: {
  scenes: StoryboardScenes; still: boolean; onClose: () => void
}) {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [finished, setFinished] = useState(false)
  const [replay, setReplay] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const video = useRef<HTMLVideoElement>(null)
  const reduced = useReducedMotion()
  const row = scenes[index]
  const current = row.selected
  const videoUrl = still || reduced ? null : current?.videoUrl
  const available = !!(current?.imageUrl || videoUrl)

  useEffect(() => {
    const player = video.current
    if (!player || error) return
    if (paused || finished) { player.pause(); return }
    let active = true
    void player.play().catch((cause: unknown) => {
      if (!active || (cause instanceof DOMException && cause.name === 'AbortError')) return
      setPaused(true)
      setNotice(cause instanceof DOMException && cause.name === 'NotAllowedError'
        ? '재생 버튼을 눌러 이어보기를 시작하세요.' : '이 장면을 재생하지 못했습니다. 재생을 다시 눌러 주세요.')
    })
    return () => { active = false }
  }, [paused, finished, index, replay, current?.versionId, videoUrl, error])

  function choose(next: number) {
    setIndex(next)
    setReplay(n => n + 1)
    setFinished(false)
    setNotice('')
    setError('')
  }
  function ended() {
    if (index + 1 < scenes.length) {
      choose(index + 1)
      setPaused(false)
    } else {
      setPaused(true)
      setFinished(true)
    }
  }
  function toggle() {
    if (finished || error) { choose(finished ? 0 : index); setPaused(false); return }
    setNotice('')
    setPaused(value => !value)
  }
  function mediaFailed() {
    setError(row.label + ' 선택본을 불러오지 못했습니다. 다시 재생해 주세요.')
    setPaused(true)
  }
  return <div className="rv-workbench rv-full">
    <ThemeStoryboard scenes={scenes} active={row.scene} playlist onChoose={scene => choose(scenes.findIndex(s => s.scene === scene))} />
    <div className="rv-full-content">
      <section className="rv-full-player" aria-label="주간 선택본 이어보기">
        <header className="rv-full-head"><div><small><Play size={14} aria-hidden="true" />전체 이어보기</small><h2>{row.title}</h2></div>
          <button type="button" onClick={onClose}>이어보기 닫기</button></header>
        <div className="rv-full-media" onPlay={event => {
          if (event.target === video.current) { setPaused(false); setFinished(false); setNotice('') }
        }} onPause={event => {
          if (event.target === video.current && !video.current?.ended) setPaused(true)
        }}>
          {row.error ? <div className="rv-full-empty" role="alert"><p>{row.label} 선택본 이력을 불러오지 못했습니다.</p><button onClick={() => void row.refetch()}>다시 불러오기</button></div>
            : row.loading ? <p className="rv-full-empty" role="status">{row.label} 선택본을 불러오는 중입니다.</p>
            : error ? <p className="rv-full-empty" role="alert">{error}</p>
            : !available || !current ? <p className="rv-full-empty" role="alert">{row.label}에 재생할 {still || reduced ? '선택본 그림' : '선택본'}이 없습니다.</p>
            : <ThemeMotionPlayer key={`${row.scene}-${current.versionId}-${replay}`} imageUrl={current.imageUrl} videoUrl={videoUrl ?? null}
              motion={current.motion} still={still} paused={paused} stillSeconds={4} videoRef={video}
              label={row.label} onEnded={ended} onImageError={mediaFailed} onVideoError={mediaFailed} />}
        </div>
        <div className="rv-full-foot"><div><span>{index + 1} / {scenes.length} · {row.label}</span>
          {current && <strong>{versionName(current)}</strong>}</div>
          <button type="button" disabled={!available || !!row.error || row.loading} onClick={toggle}>
            {finished || error ? <RotateCcw size={15} /> : paused ? <Play size={15} /> : <Pause size={15} />}
            {finished ? '처음부터 다시 재생' : error ? '다시 재생' : paused || !available ? '재생' : '일시정지'}</button>
        </div>
        {(finished || notice) && <p className="rv-full-notice" role="status">{finished ? '종료 영상까지 모두 재생했습니다.' : notice}</p>}
      </section>
      {row.scene !== 'INTRO' && row.scene !== 'OUTRO' && <section className="rv-mission-context">
        <div><small>{row.label.replace(/ 장면$/, '')} 미션</small><h3>{row.title}</h3>{row.question && <p>{row.question}</p>}</div>
      </section>}
    </div>
  </div>
}
