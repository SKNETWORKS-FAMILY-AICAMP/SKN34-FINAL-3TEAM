import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ALL_ITEM_SLOTS,
  readAlbum,
  readEpisode,
  readEquipped,
  readFrameSlots,
  readLookItems,
  weekLabel,
} from '../src/domain/retention.ts'
import { readLook } from '../src/domain/studentLook.ts'

// 내 방·추억 앨범(P27, API 명세 2.12 기준안, #556·#561) 응답 검사. 가상 값만 쓴다.

test('가구 칸은 서버가 알려 준 때만 두어 가구 칸을 모르는 서버에 보내지 않는다', () => {
  assert.deepEqual(readEquipped({ HAT: 'HAT_ACORN' }), { HAT: 'HAT_ACORN', OUTFIT: null, ACCESSORY: null, BACKGROUND: null })
  assert.deepEqual(readEquipped({ BACKGROUND: 'BG_STARS', DESK: 'DESK_MINT', WALL: null }),
    { HAT: null, OUTFIT: null, ACCESSORY: null, BACKGROUND: 'BG_STARS', DESK: 'DESK_MINT', WALL: null })
  const look = readLook({ theme: 'lake', companion: 'tori', equipped: { HAT: null, WARDROBE: 'WARDROBE_SKY' }, updatedAt: null })
  assert.equal(look.equipped?.WARDROBE, 'WARDROBE_SKY')
  assert.equal('DESK' in (look.equipped ?? {}), false)
  assert.equal('DESK' in (readLook({ theme: 'lake', companion: 'tori', equipped: { HAT: null } }).equipped ?? {}), false)
})

test('가구 스킨 아이템은 목록에 남고 관리자 칸 선택에 가구 칸이 있다', () => {
  const items = readLookItems({ items: [
    { itemKey: 'DESK_MINT', slot: 'DESK', name: '민트 책상', pricePoints: 60, unlocked: false, onSale: true, assetKey: 'room/desk-mint.svg' },
    { itemKey: 'X', slot: 'SOFA', name: '모르는 칸', pricePoints: 1, unlocked: false, onSale: true, assetKey: null },
  ] })
  assert.deepEqual(items.map((i) => i.slot), ['DESK'])
  assert.deepEqual(ALL_ITEM_SLOTS.slice(-3), ['DESK', 'WALL', 'WARDROBE'])
})

test('추억의 벽 슬롯은 1~6번, 번호가 겹치면 계약 오류로 본다', () => {
  const slots = readFrameSlots({ slots: [
    { slotNo: 3, themeId: 't-2', weekStart: '2026-11-02', title: '별빛 우체국', imageUrl: null },
    { slotNo: 1, themeId: 't-1', weekStart: '2026-10-26', title: '숲속 발명 대회', imageUrl: '' },
  ] })
  assert.deepEqual(slots.map((s) => s.slotNo), [1, 3])
  assert.equal(slots[0].imageUrl, null)
  assert.throws(() => readFrameSlots({ slots: [{ slotNo: 7, themeId: 't', weekStart: '2026-11-02' }] }))
  assert.throws(() => readFrameSlots({ slots: [
    { slotNo: 1, themeId: 'a', weekStart: '2026-11-02' }, { slotNo: 1, themeId: 'b', weekStart: '2026-10-26' }] }))
  assert.throws(() => readFrameSlots({}))
})

test('앨범 목록은 새 액자·전시 여부를 그대로 읽고 모양이 다르면 오류', () => {
  const album = readAlbum({ items: [{ themeId: 't-1', weekStart: '2026-11-02', title: '별빛 우체국', imageUrl: null,
    awardedAt: '2026-11-06T10:30:00Z', seen: false, displayed: true }], page: 0, size: 12, totalElements: 1 })
  assert.equal(album.items[0].seen, false)
  assert.equal(album.items[0].displayed, true)
  assert.throws(() => readAlbum({ items: [{ themeId: 't-1', weekStart: '11/02', awardedAt: 'x', seen: 1, displayed: 0 }], page: 0, size: 12, totalElements: 1 }))
})

test('회차 상세는 요일 순서로 정리하고 엔딩을 안 봤으면 끝 이야기·답을 숨긴다(P23)', () => {
  const base = { themeId: 't-1', weekStart: '2026-11-02', title: '별빛 우체국', awardedAt: '2026-11-06T10:30:00Z',
    missions: [
      { day: 'TUE', missionId: 'm2', title: '둘째', thinkingType: 'EVALUATE', attemptId: 'a2' },
      { day: 'MON', missionId: 'm1', title: '첫째', thinkingType: 'ANALYZE', attemptId: null },
    ] }
  const hidden = readEpisode({ ...base, ending: { seen: false, outro: '새어 나온 이야기', answer: '새어 나온 답' } })
  assert.deepEqual(hidden.missions.map((m) => m.day), ['MON', 'TUE'])
  assert.equal(hidden.missions[0].attemptId, null)
  assert.deepEqual(hidden.ending, { seen: false, outro: null, answer: null })
  const shown = readEpisode({ ...base, ending: { seen: true, outro: '끝 이야기', answer: '우체국장 할아버지' } })
  assert.equal(shown.ending.answer, '우체국장 할아버지')
  assert.throws(() => readEpisode({ ...base, ending: {} }))
})

test('회차 주 표시는 그 달 몇째 주인지로 보인다', () => {
  assert.equal(weekLabel('2026-11-02'), '11월 1주')
  assert.equal(weekLabel('2026-11-09'), '11월 2주')
})
