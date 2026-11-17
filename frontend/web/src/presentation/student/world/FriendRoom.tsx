import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../../data/apiClient.ts'
import { useFriendRoom } from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { FRAME_SLOT_COUNT } from '../../../domain/retention.ts'
import type { FriendRoom as FriendRoomData } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { FrameScene } from './FrameScene.tsx'
import { SpeechBubble } from './SpeechBubble.tsx'
import { boardTagTransform, faceStyle, MATS, projectToHolder, roomFaces, RUG, slotTransform, WORLD_TOP } from './roomArt.ts'
import { skinOf } from './roomAssets.ts'
import { useLook } from './lookContext.ts'
import { CAN_WALK, clamp, useRoomWalk } from './useRoomWalk.ts'
import { blockedByDecor, decorFaces, decorFloorBlocks, drawableDecor } from './decorArt.ts'
import './room.css'

/** 방 주인 뭉치는 방 가운데(출발 자리)에 서 있다(사용자 결정 2026-11-17). 내 뭉치는 이 둘레를 지나가지 못한다 */
const FRIEND_SPOT = { x: RUG.x, z: RUG.z } as const
const FRIEND_RADIUS = 125
/** 이만큼 가까이 와서 멈추면 친구 뭉치가 인사한다 */
const GREET_RADIUS = 210
/** 내 뭉치는 처음에 문 앞에 서 있고 학생이 움직일 때만 걷는다(사용자 결정 2026-11-17) */
const DOOR_MAT = MATS.find((m) => m.id === 'door')!
/** 좁은 화면에서 문 앞이 방 칸 밖이면 문에 가까운 순서로 보이는 자리에 세운다 */
const ENTRY_FALLBACKS = [{ x: DOOR_MAT.x - 110, z: DOOR_MAT.z + 60 }, { x: 330, z: -20 }, { x: 330, z: 140 }, { x: -120, z: -40 }]
/** 친구 뭉치 인사(고정 문구, AI 호출 없음, 기준안). 들어올 때마다 하나를 고른다 */
const GREETINGS = ['놀러 와 줘서 고마워!', '내 방 어때? 천천히 구경해!', '액자도 구경해 봐! 내가 모은 거야.']

/**
 * 친구 방 놀러 가기(#709, FN-RET-14). 친구 생각 글에서 그 작성자의 방을 읽기 전용으로 본다.
 * 그림은 내 방과 같은 방 그림(roomFaces·액자 자리), 걷기는 내 방과 같은 useRoomWalk.
 * 액자를 누르면 방 위에 그 그림을 크게, 아래에 테마 제목(사용자 결정 2026-11-17, 방 안 제목 띠는 없음). 회차 상세(문제·답·정답)는 열지 않는다(회차 키가 없음).
 * 없는 것: 가구 앞 발판 메뉴·이름표 이동, 방 꾸미기·저장, 포인트·해금. 위치는 저장하지 않는다.
 * 바닥 아이템·방 소품은 #705·#723 뒤에 같이 그린다(지금은 벽지 세트의 바닥).
 */
export function FriendRoom({ child, postId, nickname, onBack }: { child: Child; postId: string; nickname: string; onBack: () => void }) {
  const room = useFriendRoom(child.id, postId)
  return (
    <main className="st-paper st-sheet st-fit st-room-page st-friend-room" aria-labelledby="friend-room-title">
      <div className="st-room-head">
        <h1 id="friend-room-title" className="st-title-mix"><span>{room.data?.nickname ?? nickname}의 </span>방에 놀러 왔어요</h1>
        <div className="st-room-actions">
          <button type="button" className="st-room-btn" onClick={onBack}><span aria-hidden="true">←</span>{' '}친구 생각으로 돌아가기</button>
        </div>
      </div>
      {room.isPending && <p role="status">{nickname}의 방으로 가고 있어요.</p>}
      {room.error && <FriendRoomError error={room.error} retry={() => void room.refetch()} />}
      {room.data && <FriendRoomScene data={room.data} />}
    </main>
  )
}

/** 이유를 말하지 않고 막는 경우: 글이 없거나 숨겨짐·작성자가 공개를 끔·보호자 동의 없음(404), 내 글(409, 보통 생기지 않음) */
const CLOSED_CODES = ['COMMUNITY_POST_NOT_FOUND', 'COMMUNITY_OWN_POST']
const LOCKED_CODES = ['COMMUNITY_LOCKED', 'COMMUNITY_LOCKED_UNTIL_ENDING']
const korean = (t?: string | null) => (t && /[가-힣]/.test(t) ? t : '')

/**
 * 친구 방을 열 수 없을 때(#709 오류 안내, 기준안 문구).
 * 404·409는 이유를 드러내지 않는 한 문장(공개를 끈 친구인지 알 수 없게), 403 잠금은 서버 문구 그대로, 그 밖은 공통 오류와 다시 시도.
 * 404면 친구 생각 목록도 다시 받아 돌아갔을 때 그 글이 남아 있지 않게 한다.
 */
function FriendRoomError({ error, retry }: { error: Error; retry: () => void }) {
  const cache = useQueryClient()
  const p = error instanceof ApiError ? error.problem : null
  const closed = !!p?.code && CLOSED_CODES.includes(p.code)
  useEffect(() => {
    if (closed) void cache.invalidateQueries({ queryKey: ['community', 'mission'] })
  }, [closed, cache])
  if (closed) {
    return (
      <div className="st-friend-room-closed" role="alert">
        <strong>지금은 이 친구 방에 놀러 갈 수 없어요.</strong>
        <p>친구 생각으로 돌아가서 다른 친구 방에 놀러 가 볼까요?</p>
      </div>
    )
  }
  if (p?.code && LOCKED_CODES.includes(p.code)) {
    return (
      <div className="st-friend-room-closed" role="alert">
        <strong>{korean(p.detail) || korean(p.title) || '아직 이 친구 방에 놀러 갈 수 없어요.'}</strong>
      </div>
    )
  }
  return <ErrorNotice error={error} retry={retry} />
}

function FriendRoomScene({ data }: { data: FriendRoomData }) {
  const { companion, worn } = useLook()
  const near = (x: number, z: number, r: number) => Math.hypot(x - FRIEND_SPOT.x, z - FRIEND_SPOT.z) < r
  // 친구가 놓은 방 소품(#723 칸 모양): 그릴 수 있는 것만, 선 것은 걷기 막힘
  const shownDecor = drawableDecor(data.decor)
  const decorBlocked = blockedByDecor(decorFloorBlocks(shownDecor))
  const {
    view, pos, facing, pose, moving, jumping, stageRef, holderRef, roomRef,
    fit, holderH, scale, worldScale, onKeyDown, onKeyUp, onBlur, onPointerDown, onFloorClick, faceCamera, canStand, placeAt,
  } = useRoomWalk({ start: { x: DOOR_MAT.x, z: DOOR_MAT.z }, blocked: (x, z) => near(x, z, FRIEND_RADIUS) || decorBlocked(x, z) })
  const [greeting] = useState(() => GREETINGS[Math.floor(Math.random() * GREETINGS.length)])
  // 크게 보는 액자: 열면 닫기 단추로, 닫으면 누른 액자로 초점을 돌린다
  const [viewing, setViewing] = useState<number | null>(null)
  const frameRefs = useRef<Record<number, HTMLButtonElement | null>>({})
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { if (viewing !== null) closeRef.current?.focus() }, [viewing])
  const closeView = () => { const n = viewing; setViewing(null); if (n !== null) frameRefs.current[n]?.focus() }
  const shown = viewing !== null ? data.frames.find((f) => f.slotNo === viewing) : undefined
  const narrow = fit.w < 700
  // 문 앞이 화면 밖이면(좁은 화면) 보이는 자리로 옮긴다 — 화면 밖에서 시작하면 첫걸음부터 막힘.
  // 방 칸 크기를 잰 뒤에 봐야 해서 한 박자 뒤에(크기 재기는 그린 직후 레이아웃 단계)
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (!canStand(DOOR_MAT)) { const spot = ENTRY_FALLBACKS.find((p) => canStand(p)); if (spot) placeAt(spot) }
    }, 0)
    return () => clearTimeout(id)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- 들어올 때 한 번만(걷기 함수는 그릴 때마다 새로 만들어짐)

  const faces = roomFaces({ wallpaper: data.room.wallpaper, floor: data.room.floor, desk: data.room.desk, wall: data.room.wall, wardrobe: data.room.wardrobe })
    .filter((f) => !f.key.startsWith('mat-')) // 가구 앞 발판은 내 방 메뉴용이라 친구 방에서는 그리지 않음
    .concat(decorFaces(shownDecor, faceCamera))
  const frameWood = skinOf('WALL', data.room.wall).set[0]
  const greet = !moving && near(pos.x, pos.z, GREET_RADIUS)
  const bubbleAt = projectToHolder(FRIEND_SPOT.x, -250, FRIEND_SPOT.z, { ...view, ws: worldScale, stageScale: scale, holderW: fit.w })

  return (
    <section ref={roomRef} className="st-mini-room" aria-label={`${data.nickname}의 방`}>
      <div ref={holderRef} className="st-room-holder" style={{ height: Math.round(holderH), '--st-frame-wood': frameWood } as CSSProperties}>
        <div ref={stageRef} className="st-room-stage" style={{ transform: `scale(${scale.toFixed(3)})` }} tabIndex={CAN_WALK ? 0 : undefined} role="group"
          aria-label={`${data.nickname}의 방 그림. 바닥을 누르면 걸어가고, 방을 누른 뒤 방향키로 움직여요. 친구 뭉치에게 가까이 가면 인사해요`}
          onKeyDown={onKeyDown} onKeyUp={onKeyUp} onBlur={onBlur} onPointerDown={onPointerDown}>
          <div className="st-room-world" data-top={WORLD_TOP} style={{ transform: `scale(${worldScale}) rotateX(${view.rx}deg) rotateY(${view.ry}deg)` }}>
            {faces.map((f) => (
              <div key={f.key} className={`st-f${f.floor && CAN_WALK ? ' st-room-floor' : ''}`} style={faceStyle(f)} onClick={f.floor && CAN_WALK ? onFloorClick : undefined} aria-hidden="true" />
            ))}
            <div className="st-f st-room-boardtag" style={{ transform: boardTagTransform }} aria-hidden="true">추억의 벽</div>
            {Array.from({ length: FRAME_SLOT_COUNT }, (_, i) => {
              const frame = data.frames.find((f) => f.slotNo === i + 1)
              const style = { transform: slotTransform(i, !!frame) }
              return frame ? (
                <button key={i} ref={(el) => { frameRefs.current[frame.slotNo] = el }} type="button" className="st-f st-room-slot is-filled st-friend-frame"
                  style={style} aria-label={`액자 크게 보기: ${frame.title || '이름 없는 테마'}`} onClick={() => setViewing(frame.slotNo)}>
                  <FriendFrameArt frame={frame} />
                </button>
              ) : (
                <div key={i} className="st-f st-room-slot" style={style} role="img" aria-label={`${i + 1}번 자리 비어 있음`} />
              )
            })}
            {/* 방 주인 뭉치: 착용 그대로 방 가운데에 서 있고 이름표가 위에 */}
            <div className="st-f st-room-shadow" aria-hidden="true" style={{ transform: `translate3d(${FRIEND_SPOT.x}px,-2px,${FRIEND_SPOT.z}px) rotateX(90deg)` }} />
            <div className="st-f st-room-char st-friend-char" aria-hidden="true" style={{ transform: faceCamera(FRIEND_SPOT.x, 0, FRIEND_SPOT.z) }}>
              <div className="st-room-bob"><Companion kind={data.companion} size={140} decorative worn={data.worn} /></div>
            </div>
            <div className="st-f st-friend-name" aria-hidden="true" style={{ transform: faceCamera(FRIEND_SPOT.x, -205, FRIEND_SPOT.z) }}>{data.nickname}</div>
            {/* 내 뭉치 */}
            <div className={`st-f st-room-shadow${moving ? ' is-moving' : ''}`} aria-hidden="true"
              style={{ transform: `translate3d(${pos.x}px,-2px,${pos.z}px) rotateX(90deg) scale(${jumping ? 0.6 : 1})`, opacity: jumping ? 0.5 : 1 }} />
            <div className={`st-f st-room-char${moving ? ' is-moving' : ''}`} aria-hidden="true" style={{ transform: faceCamera(pos.x, jumping ? -70 : 0, pos.z) }}>
              <div className={moving ? 'st-room-walk' : 'st-room-bob'}>
                <div style={{ transform: `scaleX(${facing})` }}><Companion kind={companion} size={140} decorative worn={worn} view={pose} /></div>
              </div>
            </div>
          </div>
        </div>
        {greet && (
          <SpeechBubble className="st-room-bubble" style={{ left: clamp(bubbleAt.x, 110, fit.w - 110), top: Math.max(bubbleAt.y, fit.w < 640 ? 96 : 120) }} role="status" aria-label={`${data.nickname} 뭉치의 인사`}>
            <p>{greeting}</p>
          </SpeechBubble>
        )}
        {CAN_WALK && <p className="st-room-hint" data-room-ui aria-hidden="true">바닥을 누르면 걸어가요 · {data.nickname}에게 가까이 가 봐요</p>}
      </div>
        {shown && (
          // 방 칸 위에 겹쳐 뜨는 창(바깥을 누르거나 Esc·닫기로 닫음). PC는 방 칸 높이에 맞추고, 좁은 화면은 화면 폭에 맞춰 방 칸 아래로 내려온다
          <div className={`st-friend-frame-backdrop${narrow ? ' is-narrow' : ''}`} onClick={closeView}>
            <div className="st-friend-frame-view" role="dialog" aria-modal="true" aria-labelledby="friend-frame-title"
              onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); closeView() } }}>
              <div className="st-friend-frame-art" style={(() => { const w = narrow ? fit.w - 72 : Math.min(clamp(holderH - 130, 90, 380) * 160 / 116, fit.w - 72); return { width: w, height: w * 116 / 160 } })()}>
                <FriendFrameArt frame={shown} />
              </div>
              <h2 id="friend-frame-title">{shown.title || '이름 없는 테마'}</h2>
              <button ref={closeRef} type="button" className="st-room-btn" onClick={closeView}>닫기</button>
            </div>
          </div>
        )}
    </section>
  )
}

/** 친구 액자 그림. 그림이 없으면 내 방·앨범과 같은 작은 풍경(제목으로 장면을 고름) */
function FriendFrameArt({ frame }: { frame: { title: string; imageUrl: string | null } }) {
  if (frame.imageUrl) return <img src={frame.imageUrl} alt="" />
  return <FrameScene className="st-room-scene" themeId={`friend-${frame.title}`} title={frame.title} />
}
