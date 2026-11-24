import { useEffect, useRef } from 'react'
import { Film } from 'lucide-react'
import type { StoryboardScenes } from '../../data/admin/themeReviewQueries.ts'
import type { ThemeSceneName } from '../../domain/admin/themeDrafts.ts'

export function ThemeStoryboard({ scenes, active, onChoose, playlist = false }: {
  scenes: StoryboardScenes; active: ThemeSceneName; onChoose: (scene: ThemeSceneName) => void; playlist?: boolean
}) {
  const strip = useRef<HTMLElement>(null)
  useEffect(() => {
    const nav = strip.current, row = nav?.querySelector<HTMLElement>('[aria-current="true"]')
    if (!nav || !row || nav.scrollWidth <= nav.clientWidth) return
    const bounds = nav.getBoundingClientRect(), tile = row.getBoundingClientRect()
    if (tile.left < bounds.left) nav.scrollLeft += tile.left - bounds.left
    if (tile.right > bounds.right) nav.scrollLeft += tile.right - bounds.right
  }, [active])
  return <aside className="rv-board"><header><h2>주간 스토리보드</h2><span>{scenes.length}개 장면</span></header>
    <nav ref={strip} aria-label={playlist ? '전체 재생 장면 선택' : '검수 장면 선택'}>{scenes.map(row =>
      <button className="rv-board-shot" key={row.scene} aria-current={row.scene === active ? 'true' : undefined}
        aria-label={row.label + ' · ' + row.title} onClick={() => onChoose(row.scene)}>
        {row.image ? <img src={row.image} alt="" /> : <Film size={28} aria-hidden="true" />}
        <span><small>{row.label}</small><strong title={row.title}>{row.title}</strong><em>{row.status}</em></span>
      </button>)}</nav>
  </aside>
}
