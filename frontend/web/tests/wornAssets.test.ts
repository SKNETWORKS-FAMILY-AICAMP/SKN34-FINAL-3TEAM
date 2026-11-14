// #455·#557 착용 그림 연결: 그림 키 → 파일 주소, 착용 itemKey → 그림 키
import test from 'node:test'
import assert from 'node:assert/strict'
import { wearAssetUrl, WEAR_ANCHORS, WEAR_SLOTS } from '../src/presentation/student/world/roomAssets.ts'
import { wornAssets, NO_EQUIPPED } from '../src/domain/retention.ts'
import type { LookItem } from '../src/domain/retention.ts'
import { COMPANIONS } from '../src/domain/studentLook.ts'

test('그림 키는 public/student-assets 안 경로만 파일 주소가 된다', () => {
  assert.equal(wearAssetUrl('looks/hat-acorn.svg'), '/student-assets/looks/hat-acorn.svg')
  assert.equal(wearAssetUrl('looks/outfit_rain-2.png'), '/student-assets/looks/outfit_rain-2.png')
  for (const bad of [null, undefined, '', '../secret.svg', '/looks/a.svg', 'looks/a.gif', 'https://x.test/a.svg', 'looks/A.svg', 'looks/a.svg?x=1'])
    assert.equal(wearAssetUrl(bad), null, String(bad))
})

test('착용한 캐릭터 칸만 목록의 그림 키로 바꾸고, 목록이 없거나 칸이 다르면 비운다', () => {
  const item = (itemKey: string, slot: LookItem['slot'], assetKey: string | null): LookItem =>
    ({ itemKey, slot, name: itemKey, pricePoints: 10, unlocked: true, onSale: true, assetKey })
  const items = [item('HAT_ACORN', 'HAT', 'looks/hat-acorn.svg'), item('OUTFIT_RAIN', 'OUTFIT', null), item('BG_STARS', 'BACKGROUND', 'looks/bg-stars.svg')]
  const equipped = { ...NO_EQUIPPED, HAT: 'HAT_ACORN', OUTFIT: 'OUTFIT_RAIN', ACCESSORY: 'HAT_ACORN', BACKGROUND: 'BG_STARS' }
  assert.deepEqual(wornAssets(equipped, items), { HAT: 'looks/hat-acorn.svg' })
  assert.deepEqual(wornAssets(equipped, undefined), {})
  assert.deepEqual(wornAssets(undefined, items), {})
})

test('캐릭터 5종 모두 착용 칸마다 기준점이 있다', () => {
  for (const c of COMPANIONS) for (const slot of WEAR_SLOTS) {
    const a = WEAR_ANCHORS[c.id][slot]
    assert.ok(Number.isFinite(a.x) && Number.isFinite(a.y) && a.scale > 0, `${c.id} ${slot}`)
  }
})
