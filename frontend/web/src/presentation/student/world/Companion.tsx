import { useId, useState } from 'react'
import type { CSSProperties } from 'react'
import type { CompanionId, FriendId } from '../../../domain/studentLook.ts'
import { companionToFriend, friendById } from '../../../domain/studentLook.ts'
import { FRIEND_WEAR_ANCHORS, WEAR_ITEM_SIZE, wearAssetUrl } from './roomAssets.ts'
import type { WearSlot } from './roomAssets.ts'
import { FRIEND_VIEWBOX, friendArt, friendSilhouette, frontEdge } from './friendArt.ts'
import type { FriendView } from './friendArt.ts'

/** 옷 그림의 앞 장식 파일(단추·리본 등, 앞모습에만): `looks/outfit-rain.svg` → `looks/outfit-rain.front.svg`. 없으면 그리지 않음 */
const frontPart = (href: string | null) => (href && href.endsWith('.svg') ? href.replace(/\.svg$/, '.front.svg') : null)

/**
 * 착용 아이템 겹쳐 그리기(#455). 칸마다 `public/student-assets/{그림 키}` 파일을 친구별 기준점(FRIEND_WEAR_ANCHORS)에
 * 그린다. 파일이 없거나 못 읽으면 그 칸만 빼고 기본 모습으로 둔다(그림을 넣기만 하면 보임).
 * 2026-11-16(사용자 의견 "옆·뒤도 없고 살짝 옆에 삐져나온대, 캐릭터마다 잘 맞게"): 설계 캔버스 Mungchi처럼
 * 옷은 친구 몸 윤곽(friendSilhouette)으로 잘라 몸 안에만 그리고, 앞·옆·뒤 모두 입힌다(앞 장식 파일은 앞모습만).
 * 모자도 세 방향 모두(옆모습은 캔버스대로 가로 0.9배), 소품은 몸 앞쪽 끝에 들고 뒷모습에서는 몸에 가려 안 보인다.
 */
function Worn({ friend, worn, view, uid }: { friend: FriendId; worn: Partial<Record<WearSlot, string | null>>; view: FriendView; uid: string }) {
  const [broken, setBroken] = useState<string[]>([])
  const ok = (href: string | null): href is string => !!href && !broken.includes(href)
  const lost = (href: string) => () => setBroken((list) => (list.includes(href) ? list : [...list, href]))
  const box = (slot: WearSlot, sx = 1) => {
    const { x, y, scale } = FRIEND_WEAR_ANCHORS[friend][slot]
    const w = WEAR_ITEM_SIZE * scale
    const cx = slot === 'ACCESSORY' && view === 'side' ? frontEdge(friend, 'side') - 2 : x
    return { x: cx - (w * sx) / 2, y: y - w / 2, width: w * sx, height: w }
  }
  const outfit = wearAssetUrl(worn.OUTFIT)
  const front = view === 'front' ? frontPart(outfit) : null
  const hat = wearAssetUrl(worn.HAT)
  const acc = view === 'back' ? null : wearAssetUrl(worn.ACCESSORY)
  const clip = `${uid}-body`
  return (
    <g className="st-worn">
      <clipPath id={clip}>{friendSilhouette(friend, view)}</clipPath>
      {ok(outfit) && (
        <g clipPath={`url(#${clip})`}>
          <image data-slot="OUTFIT" href={outfit} {...box('OUTFIT')} preserveAspectRatio="none" onError={lost(outfit)} />
          {ok(front) && <image data-slot="OUTFIT_FRONT" href={front} {...box('OUTFIT')} preserveAspectRatio="none" onError={lost(front)} />}
        </g>
      )}
      {ok(hat) && <image data-slot="HAT" href={hat} {...box('HAT', view === 'side' ? 0.9 : 1)} preserveAspectRatio="none" onError={lost(hat)} />}
      {ok(acc) && <image data-slot="ACCESSORY" href={acc} {...box('ACCESSORY')} preserveAspectRatio="xMidYMid meet" onError={lost(acc)} />}
    </g>
  )
}

/**
 * 동행 캐릭터: 뭉치 친구들 12종 그림(#648, 설계 캔버스 Mungchi). 서버 값(kind, 12종 #697)은 대응하는 친구로 그리고,
 * 꾸미기 목록처럼 친구를 바로 그릴 때는 friend로 고른다(friend가 우선).
 * decorative면 보조기기에서 숨긴다. worn은 착용 칸 그림 키(#455).
 */
export function Companion({
  kind = 'mungchi',
  friend,
  size = 120,
  decorative = false,
  worn,
  view = 'front',
}: {
  kind?: CompanionId
  friend?: FriendId
  size?: number
  decorative?: boolean
  worn?: Partial<Record<WearSlot, string | null>>
  /** 앞·옆·뒷모습(설계 캔버스 Mungchi view). 착용 그림도 세 방향 모두(옷 앞 장식만 앞모습) */
  view?: FriendView
}) {
  const id = friend ?? companionToFriend(kind)
  // 옷을 자르는 몸 윤곽 clipPath id(한 화면에 친구 그림이 여러 개라 그림마다 다르게)
  const uid = useId().replace(/:/g, '')
  const a11y = decorative
    ? ({ 'aria-hidden': true } as const)
    : ({ role: 'img', 'aria-label': friendById(id).name } as const)
  return (
    <svg
      width={size}
      height={size}
      viewBox={FRIEND_VIEWBOX}
      className="st-companion"
      data-friend={id}
      // 모자처럼 몸 밖으로 나가는 착용 그림이 잘리지 않게
      style={{ '--c': `${size}px`, overflow: 'visible' } as CSSProperties}
      {...a11y}
    >
      {friendArt(id, view)}
      {worn && <Worn friend={id} worn={worn} view={view} uid={uid} />}
    </svg>
  )
}
