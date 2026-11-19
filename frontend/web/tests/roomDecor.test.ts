import test from 'node:test'
import assert from 'node:assert/strict'
import { readDecorSpots } from '../src/domain/retention.ts'
import { allMatsReachable, cellSpan, decorCenter, decorFaces, drawableDecor, firstPlace, isBlockedCell, onPcScreen, placeableCells, placeProblem, stepCell } from '../src/presentation/student/world/decorArt.ts'
import { decorColor, decorColors, decorSvg } from '../src/presentation/student/world/decorDraw.ts'
import { DECORS } from '../src/presentation/student/world/roomAssets.ts'

// #705 방 소품 놓기(core #723 칸 계약): 웹이 보는 규칙(가구 칸·겹침·길·맞는 면·크기)과 그림·색
const PLANT = 'room/decor-plant.svg', RUG = 'room/decor-rug.svg', LIGHTS = 'room/decor-lights.svg', CLOCK = 'room/decor-clock.svg'
const spot = (surface: 'FLOOR' | 'WALL_BACK' | 'WALL_LEFT', col: number, row: number, assetKey: string) => ({ surface, col, row, assetKey })

test('#705 막힌 칸: 가구·발판 자리는 막고, 줄 조명(drape)만 추억의 벽·창문 위에 걸 수 있다', () => {
  // 바닥: 책장(왼쪽 뒤 구석), 옷장 앞 발판
  assert.equal(isBlockedCell('FLOOR', 1, 0), true, '책장')
  assert.equal(isBlockedCell('FLOOR', 10, 2), true, '옷장 발판')
  assert.equal(isBlockedCell('FLOOR', 12, 6), false, '빈 바닥')
  // 방 가운데(예전 러그 자리)는 막지 않는다(원래 러그를 뺌, 사용자 결정 2026-11-17)
  assert.equal(isBlockedCell('FLOOR', 8, 5), false)
  // 뒷벽 추억의 벽(게시판): 시계는 못 걸고 줄 조명은 걸 수 있다
  assert.equal(isBlockedCell('WALL_BACK', 3, 2, CLOCK), true)
  assert.equal(isBlockedCell('WALL_BACK', 3, 2, LIGHTS), false)
  // 왼쪽 벽 창문(커튼 봉): 시계는 막고 줄 조명은 된다
  assert.equal(isBlockedCell('WALL_LEFT', 8, 1, CLOCK), true)
  assert.equal(isBlockedCell('WALL_LEFT', 8, 1, LIGHTS), false)
  // 옷장·문 자리는 줄 조명도 못 건다
  assert.equal(isBlockedCell('WALL_BACK', 12, 3, LIGHTS), true, '옷장')
})

test('#705 놓기 검사: 맞는 면·칸 범위·막힌 칸·겹침·출발 자리·길 막힘', () => {
  assert.equal(placeProblem([], null, spot('WALL_BACK', 0, 0, PLANT)), '바닥에 놓는 소품이에요.')
  assert.equal(placeProblem([], null, spot('FLOOR', 12, 6, LIGHTS)), '벽에 거는 소품이에요.')
  assert.equal(placeProblem([], null, spot('FLOOR', 16, 12, RUG)), '방 끝을 넘어가요.', '2×2라 오른쪽·아래로 넘침')
  assert.equal(placeProblem([], null, spot('FLOOR', 1, 0, PLANT)), '가구나 창문이 있는 자리예요.')
  assert.equal(placeProblem([], null, spot('FLOOR', 6, 7, RUG)), null)
  assert.equal(placeProblem([spot('FLOOR', 6, 7, RUG)], null, spot('FLOOR', 7, 8, PLANT)), '다른 방 소품과 겹쳐요.', '러그 2×2가 7,8까지 차지')
  // 칸 범위 안이어도 PC 화면 밖(바닥 앞쪽 오른쪽 구석)이면 못 놓는다
  assert.equal(onPcScreen('FLOOR', 16, 12), false)
  assert.equal(onPcScreen('FLOOR', 8, 5), true)
  assert.equal(placeProblem([], null, spot('FLOOR', 16, 12, PLANT)), '방 끝을 넘어가요.')
  // 옮기는 중인 자기 자리는 겹침에서 뺀다
  assert.equal(placeProblem([spot('FLOOR', 9, 6, PLANT)], 0, spot('FLOOR', 9, 7, PLANT)), null)
  // 뭉치 출발 자리(방 가운데)에는 선 소품을 못 놓고, 밟는 러그는 놓을 수 있다
  assert.equal(placeProblem([], null, spot('FLOOR', 8, 5, PLANT)), '뭉치가 서 있는 자리예요.')
  assert.equal(placeProblem([], null, spot('FLOOR', 7, 4, RUG)), null)
  // 빈 방에서는 모든 발판에 갈 수 있다
  assert.equal(allMatsReachable([]), true)
})

test('#705 그리지 않을 방 소품: 그림 목록에 없음·맞지 않는 면·막힌 칸·겹친 것은 빼고 그린다', () => {
  const shown = drawableDecor([
    spot('FLOOR', 12, 6, PLANT),
    spot('FLOOR', 12, 6, RUG), // 같은 칸에 또(겹침)
    spot('WALL_BACK', 14, 1, PLANT), // 바닥 소품을 벽에
    spot('FLOOR', 1, 0, PLANT), // 책장 자리
    spot('FLOOR', 4, 9, 'room/decor-unknown.svg'), // 그림 목록에 없음
    spot('FLOOR', 16, 12, PLANT), // PC 화면 밖
    spot('WALL_BACK', 3, 2, LIGHTS), // 추억의 벽 위 줄 조명은 그림
  ])
  assert.deepEqual(shown.map((s) => `${s.surface}:${s.col},${s.row}:${s.assetKey}`), [`FLOOR:12,6:${PLANT}`, `WALL_BACK:3,2:${LIGHTS}`])
  // 그림 면이 생긴다(입체 화분은 여러 면, 줄 조명은 벽 그림 한 장)
  const faces = decorFaces(shown, () => 'none')
  assert.ok(faces.filter((f) => f.key.startsWith('decor-FLOOR-12-6')).length >= 5)
  assert.equal(faces.filter((f) => f.key.startsWith('decor-WALL_BACK-3-2')).length, 1)
})

test('#705 처음 놓을 자리와 화살표: 놓을 수 있는 칸 안에서 고르고, 왼쪽 벽은 화면 왼쪽이 방 앞', () => {
  const plant = firstPlace([], PLANT)
  assert.ok(plant && plant.surface === 'FLOOR')
  assert.equal(placeProblem([], null, { ...plant!, assetKey: PLANT }), null)
  const lights = firstPlace([], LIGHTS)
  assert.ok(lights && lights.surface === 'WALL_BACK')
  assert.ok(placeableCells([], null, LIGHTS).some((c) => c.surface === 'WALL_LEFT'), '벽 소품은 두 벽 모두')
  assert.deepEqual(stepCell('FLOOR', 'left'), { dc: -1, dr: 0 })
  assert.deepEqual(stepCell('WALL_LEFT', 'left'), { dc: 1, dr: 0 })
})

test('#705 그림 목록 15가지는 모두 그림·색이 있고, 모르는 색은 기본 색', () => {
  assert.equal(Object.keys(DECORS).length, 15)
  for (const key of Object.keys(DECORS)) {
    assert.ok(decorSvg(key), key)
    assert.ok(decorColors(key).length >= 1, key)
  }
  assert.equal(decorColors(PLANT).length, 8, '공통 8색')
  assert.equal(decorColor(PLANT, null)?.key, 'orange', '기본 색')
  assert.equal(decorColor(PLANT, 'blue')?.key, 'orange', '모르는 색은 기본 색')
  assert.equal(decorColor(PLANT, 'navy')?.key, 'navy')
  assert.equal(decorSvg('room/decor-unknown.svg'), null)
})

test('#705 놓은 칸 읽기(core #723): 색 형식이 틀리면 기본 색, 범위 밖·같은 기준 칸 두 번은 계약 오류', () => {
  const spots = readDecorSpots({ spots: [
    { surface: 'FLOOR', col: 12, row: 6, itemKey: 'DECOR_PLANT', color: 'sky', name: '작은 화분', assetKey: PLANT },
    { surface: 'WALL_BACK', col: 3, row: 2, itemKey: 'DECOR_LIGHTS', color: 'Not Valid', name: '줄 조명', assetKey: LIGHTS },
    { surface: 'WALL_LEFT', col: 10, row: 5, itemKey: 'DECOR_CLOCK', name: '벽시계', assetKey: CLOCK },
  ] })
  assert.deepEqual(spots.map((s) => s.color), ['sky', null, null])
  for (const bad of [
    {},
    { spots: [{ surface: 'FLOOR', col: 17, row: 0, itemKey: 'A' }] },
    { spots: [{ surface: 'WALL_LEFT', col: 11, row: 0, itemKey: 'A' }] },
    { spots: [{ surface: 'CEILING', col: 0, row: 0, itemKey: 'A' }] },
    { spots: [{ surface: 'FLOOR', col: 1, row: 1, itemKey: '' }] },
    { spots: [{ surface: 'FLOOR', col: 1, row: 1, itemKey: 'A' }, { surface: 'FLOOR', col: 1, row: 1, itemKey: 'B' }] },
  ]) assert.throws(() => readDecorSpots(bad), /방 소품 자리를 확인하지 못했어요/)
})

test('#705 밀어 보기·놓기 확대: 소품 가운데 좌표, 칸 폭을 잴 두 점, 다시 놓을 때는 자기 자리를 빼고 찾는다', () => {
  // 바닥은 칸 가운데(조금 위), 뒷벽은 벽 면, 왼쪽 벽은 x가 왼쪽 벽
  const floor = decorCenter(spot('FLOOR', 12, 6, PLANT))
  assert.ok(floor.y < 0)
  assert.equal(decorCenter(spot('WALL_BACK', 14, 1, CLOCK)).z, decorCenter(spot('WALL_BACK', 0, 0, CLOCK)).z)
  assert.equal(decorCenter(spot('WALL_LEFT', 2, 1, CLOCK)).x, decorCenter(spot('WALL_LEFT', 9, 4, CLOCK)).x)
  // 칸 폭: 두 점 사이가 그 면 칸 한 개
  for (const surface of ['FLOOR', 'WALL_BACK', 'WALL_LEFT'] as const) {
    const [a, b] = cellSpan(surface)
    assert.ok(Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) >= 75, surface)
  }
  // 막힌 칸(책장)에 있던 소품을 다시 놓으면 그 소품 자리는 빼고 가까운 칸을 찾는다
  const placed = [spot('FLOOR', 1, 0, PLANT)]
  const again = firstPlace(placed, PLANT, 0)
  assert.ok(again)
  assert.equal(placeProblem(placed, 0, { ...again!, assetKey: PLANT }), null)
})
