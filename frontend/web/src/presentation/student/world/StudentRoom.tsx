import { useState } from 'react'
import { BookOpenCheck, DoorOpen, Images, Shirt } from 'lucide-react'
import { useStudentLook } from '../../../data/studentLook/queries.ts'
import { useAlbum, useFrameSlots, useLookItems, useSaveFrameSlots } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { companionLabel } from '../../../domain/studentLook.ts'
import { episodeKey, FRAME_SLOT_COUNT, weekLabel } from '../../../domain/retention.ts'
import type { AlbumItem, FrameSlot, FurnitureSlot, LookItem } from '../../../domain/retention.ts'
import { ErrorNotice, Modal } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { Customize } from './Customize.tsx'
import { Desk, FrameBorder, MemoryWall, Wallpaper, Wardrobe } from './RoomArt.tsx'
import { FRAME_POSITIONS, FRAME_SIZE } from './roomAssets.ts'
import { useLook } from './lookContext.ts'
import './room.css'

type Placed = { slotNo: number; themeId: string; weekStart: string; title: string }
/** 착용 itemKey → 그림 assetKey. 목록을 못 받으면 기본 그림 */
const assetOf = (items: LookItem[] | undefined, itemKey: string | null | undefined) =>
  (itemKey && items?.find((i) => i.itemKey === itemKey)?.assetKey) || null

const saveMessage = (e: unknown) => {
  const code = e instanceof ApiError ? e.problem.code : ''
  if (code === 'THEME_FRAME_NOT_FOUND') return '가지고 있지 않은 액자가 있어요. 앨범을 다시 확인하고 골라 주세요.'
  if (code === 'VALIDATION_FAILED') return '같은 액자를 두 번 걸었거나 자리 번호가 맞지 않아요.'
  return '벽에 걸지 못했어요. 고른 그대로 두었으니 잠시 뒤에 다시 저장해 주세요.'
}

/**
 * 내 방(/student/room, P27·FN-RET-09, #556). 이동·편집 없이 고정 배치이고 가구를 눌러 이동한다.
 * 책상 → 주간 테마(생각 지도), 추억의 벽 → 앨범·액자 걸기, 옷장 → 꾸미기(가구 스킨).
 * 벽지는 착용 배경(BACKGROUND), 없으면 기본 벽지. 캐릭터 착용 아이템은 그림 파일이 있으면 겹쳐 그린다(#455).
 */
export function StudentRoom({ child, onTheme, onAlbum }: { child: Child; onTheme: () => void; onAlbum: () => void }) {
  const { companion, worn } = useLook()
  const look = useStudentLook(child.id)
  const items = useLookItems(child.id)
  const slots = useFrameSlots(child.id)
  const album = useAlbum(child.id, 0, 50)
  const [dressing, setDressing] = useState(false)
  const [editing, setEditing] = useState(false)
  const catalog = items.error ? undefined : items.data
  const equipped = look.data?.equipped
  const furniture = (slot: FurnitureSlot) => assetOf(catalog, equipped?.[slot])
  const unseen = album.data?.items.filter((i) => !i.seen).length ?? 0
  const placed = slots.data ?? []

  return (
    <main className="st-paper st-sheet st-room-page">
      <div className="st-sheet-head">
        <h1><DoorOpen aria-hidden="true" /> 내 방</h1>
        <p>가구를 누르면 그곳으로 가요. {companionLabel(companion)}가 방에서 기다리고 있어요.</p>
      </div>
      <ErrorNotice error={look.error} retry={() => void look.refetch()} />
      <div className="st-room">
        <svg className="st-room-art" viewBox="0 0 800 480" aria-hidden="true" focusable="false">
          <Wallpaper assetKey={assetOf(catalog, equipped?.BACKGROUND)} />
          <g transform="translate(60 60)">
            <MemoryWall assetKey={furniture('WALL')}>
              {FRAME_POSITIONS.map((p) => {
                const frame = placed.find((s) => s.slotNo === p.slotNo)
                return (
                  <g key={p.slotNo} transform={`translate(${p.x} ${p.y})`}>
                    <FrameBorder filled={!!frame}>{frame && <MiniScene seed={frame.themeId} />}</FrameBorder>
                  </g>
                )
              })}
            </MemoryWall>
          </g>
          <g transform="translate(420 242)"><Desk assetKey={furniture('DESK')} /></g>
          <g transform="translate(640 130)"><Wardrobe assetKey={furniture('WARDROBE')} /></g>
          <ellipse cx="368" cy="366" rx="50" ry="9" fill="rgba(31,36,33,0.18)" />
          <g transform="translate(313 246)"><Companion kind={companion} size={110} decorative worn={worn} /></g>
        </svg>
        {/* 가구 위 투명 버튼: 키보드로도 같은 곳에 간다 */}
        <button type="button" className="st-room-spot st-spot-wall" onClick={() => setEditing(true)}>
          <span><Images aria-hidden="true" /> 추억의 벽{unseen > 0 && <em> · 새 액자 {unseen}</em>}</span>
        </button>
        <button type="button" className="st-room-spot st-spot-desk" onClick={onTheme}>
          <span><BookOpenCheck aria-hidden="true" /> 학습 책상</span>
        </button>
        <button type="button" className="st-room-spot st-spot-wardrobe" onClick={() => setDressing(true)}>
          <span><Shirt aria-hidden="true" /> 옷장</span>
        </button>
      </div>
      <div className="st-room-actions">
        <button type="button" className="st-button" onClick={onTheme}>이번 주 테마 보러 가기</button>
        <button type="button" className="st-button st-primary" onClick={onAlbum}>추억 앨범 열기</button>
        <button type="button" className="st-button" onClick={() => setEditing(true)}>추억의 벽에 액자 걸기</button>
      </div>
      {editing && (
        <Modal title="추억의 벽 꾸미기" onClose={() => setEditing(false)}>
          {slots.isPending || album.isPending ? <p role="status">추억의 벽을 불러오고 있어요.</p>
            : slots.error || album.error ? <ErrorNotice error={slots.error ?? album.error} retry={() => { void slots.refetch(); void album.refetch() }} />
            : <WallEditor child={child} saved={placed} owned={album.data?.items ?? []} onAlbum={onAlbum} onDone={() => setEditing(false)} />}
        </Modal>
      )}
      {dressing && (
        <Modal title="옷장 · 꾸미기" onClose={() => setDressing(false)}>
          <Customize child={child} section="furniture" onDone={() => setDressing(false)} />
        </Modal>
      )}
    </main>
  )
}

/** 액자 속 작은 그림(이미지가 없을 때). 회차마다 색만 달라진다 */
function MiniScene({ seed }: { seed: string }) {
  const hues = ['#9CCB8C', '#7FC8D8', '#E9B949', '#F2B8A0', '#B8C2CC']
  const hue = hues[[...seed].reduce((n, c) => n + c.charCodeAt(0), 0) % hues.length]
  return (
    <g>
      <rect x="6" y="6" width={FRAME_SIZE.w - 12} height={FRAME_SIZE.h - 12} fill="#C6EAE1" />
      <circle cx="44" cy="20" r="6" fill="#F2C14E" />
      <path d={`M6 ${FRAME_SIZE.h - 6} L22 34 L34 46 L46 30 L${FRAME_SIZE.w - 6} ${FRAME_SIZE.h - 6}Z`} fill={hue} stroke="#1F2421" strokeWidth="2" />
    </g>
  )
}

/**
 * 추억의 벽 편집: 빈 자리(또는 걸린 자리) 고르기 → 보유 액자 고르기 → 저장·취소.
 * 저장은 전체 교체(PUT). 실패하면 고른 그대로 두고 안내한다(FN-RET-09).
 */
function WallEditor({ child, saved, owned, onAlbum, onDone }: {
  child: Child
  saved: FrameSlot[]
  owned: AlbumItem[]
  onAlbum: () => void
  onDone: () => void
}) {
  const save = useSaveFrameSlots(child.id)
  const [draft, setDraft] = useState<Placed[]>(() => saved.map(({ slotNo, themeId, weekStart, title }) => ({ slotNo, themeId, weekStart, title })))
  const [picking, setPicking] = useState<number | null>(null)
  const changed = JSON.stringify(draft.map((d) => [d.slotNo, episodeKey(d)]).sort()) !==
    JSON.stringify(saved.map((d) => [d.slotNo, episodeKey(d)]).sort())
  const hung = new Set(draft.map(episodeKey))
  const put = (slotNo: number, frame: AlbumItem | null) => {
    setDraft((before) => [
      ...before.filter((d) => d.slotNo !== slotNo && (!frame || episodeKey(d) !== episodeKey(frame))),
      ...(frame ? [{ slotNo, themeId: frame.themeId, weekStart: frame.weekStart, title: frame.title }] : []),
    ].sort((a, b) => a.slotNo - b.slotNo))
    setPicking(null)
    save.reset()
  }
  return (
    <div className="st-wall-editor">
      {!owned.length && (
        <p className="st-meta">아직 걸 액자가 없어요. 한 주 테마 문제 다섯 개를 모두 마무리하면 기념 액자를 받아요.</p>
      )}
      <ol className="st-wall-slots" aria-label="추억의 벽 자리">
        {Array.from({ length: FRAME_SLOT_COUNT }, (_, i) => i + 1).map((slotNo) => {
          const frame = draft.find((d) => d.slotNo === slotNo)
          return (
            <li key={slotNo}>
              <button type="button" className="st-wall-slot" aria-pressed={picking === slotNo}
                disabled={save.isPending || !owned.length} onClick={() => setPicking(picking === slotNo ? null : slotNo)}>
                <span className="st-wall-no">{slotNo}번 자리</span>
                <strong>{frame ? frame.title || '이름 없는 테마' : '빈 자리'}</strong>
                {frame && <small>{weekLabel(frame.weekStart)}</small>}
              </button>
            </li>
          )
        })}
      </ol>
      {picking !== null && (
        <section className="st-wall-picker" aria-label={`${picking}번 자리에 걸 액자`}>
          <h3>{picking}번 자리에 무엇을 걸까?</h3>
          <ul>
            {owned.map((f) => {
              const here = draft.find((d) => d.slotNo === picking)
              const current = here && episodeKey(here) === episodeKey(f)
              return (
                <li key={episodeKey(f)}>
                  <button type="button" className="st-button" aria-pressed={!!current} onClick={() => put(picking, f)}>
                    {f.title || '이름 없는 테마'} · {weekLabel(f.weekStart)}
                    {!current && hung.has(episodeKey(f)) && ' (다른 자리에서 옮겨요)'}
                  </button>
                </li>
              )
            })}
            {draft.some((d) => d.slotNo === picking) && (
              <li><button type="button" className="st-button" onClick={() => put(picking, null)}>이 자리 비우기</button></li>
            )}
          </ul>
        </section>
      )}
      {save.isError && <p role="alert">{saveMessage(save.error)}</p>}
      {save.isSuccess && !changed && <p role="status">벽에 걸었어요!</p>}
      <div className="cj-modal-actions">
        <button type="button" className="st-button" onClick={onAlbum}>앨범 보기</button>
        <button type="button" className="st-button" disabled={save.isPending}
          onClick={() => { setDraft(saved.map(({ slotNo, themeId, weekStart, title }) => ({ slotNo, themeId, weekStart, title }))); setPicking(null); save.reset(); onDone() }}>
          취소
        </button>
        <button type="button" className="cj-primary" disabled={!changed || save.isPending}
          onClick={() => save.mutate(draft.map(({ slotNo, themeId, weekStart }) => ({ slotNo, themeId, weekStart })))}>
          {save.isPending ? '거는 중이에요' : '저장'}
        </button>
      </div>
    </div>
  )
}
