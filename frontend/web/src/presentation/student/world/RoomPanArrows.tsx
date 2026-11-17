import { ChevronLeft, ChevronRight } from 'lucide-react'

/**
 * 밀어 보기 화살표(#705): 좁은 화면에서 화면 밖에 놓인 방 소품이 있으면 그쪽 가장자리에 작은 화살표.
 * 누르면 그쪽 끝까지 방을 민다. 내 방·친구 방이 같이 쓴다.
 */
export function RoomPanArrows({ points, toHolder, width, limX, panX, panTo }: {
  points: { x: number; y: number; z: number }[]
  toHolder: (x: number, y: number, z: number) => { x: number; y: number }
  width: number
  limX: number
  panX: number
  panTo: (side: -1 | 1) => void
}) {
  if (!limX || !points.length) return null
  const xs = points.map((p) => toHolder(p.x, p.y, p.z).x)
  // 소품 가운데가 화면 끝 24px 안쪽에 없으면 "밖"(이미 그쪽 끝까지 밀었으면 화살표 없음)
  const left = panX < limX - 1 && xs.some((x) => x < 24)
  const right = panX > -limX + 1 && xs.some((x) => x > width - 24)
  return (
    <>
      {left && (
        <button type="button" className="st-room-pan is-left" data-room-ui aria-label="왼쪽에 방 소품이 더 있어요. 방을 왼쪽으로 밀어 보기" onClick={() => panTo(-1)}>
          <ChevronLeft aria-hidden="true" />
        </button>
      )}
      {right && (
        <button type="button" className="st-room-pan is-right" data-room-ui aria-label="오른쪽에 방 소품이 더 있어요. 방을 오른쪽으로 밀어 보기" onClick={() => panTo(1)}>
          <ChevronRight aria-hidden="true" />
        </button>
      )}
    </>
  )
}
