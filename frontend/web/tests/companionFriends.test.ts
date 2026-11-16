// #648 뭉치 친구들 12종: 화면 친구 ↔ 서버 값(5종) 대응, 친구 그림, 착용 기준점
import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  COMPANIONS,
  companionLabel,
  companionToFriend,
  FRIENDS,
  friendById,
  friendToCompanion,
  isFriendId,
} from '../src/domain/studentLook.ts'
import type { CompanionId, FriendId } from '../src/domain/studentLook.ts'
import { FRIEND_VIEWBOX, friendArt } from '../src/presentation/student/world/friendArt.ts'
import { FRIEND_WEAR_ANCHORS, WEAR_ANCHORS, WEAR_SLOTS } from '../src/presentation/student/world/roomAssets.ts'

const MAPPED: Record<CompanionId, FriendId> = { mungchi: 'cotton', monggeul: 'cloud', tori: 'cone', mongdol: 'sand', kongi: 'moss' }
const SOON: FriendId[] = ['snow', 'yarn', 'star', 'foam', 'paper', 'petal', 'ice']

test('친구 12종은 설계 캔버스 순서·이름 그대로이고 id가 겹치지 않는다', () => {
  assert.deepEqual(FRIENDS.map((f) => f.name), [
    '솜뭉치', '구름뭉치', '눈뭉치', '털실뭉치', '이끼뭉치', '모래뭉치', '별뭉치', '거품뭉치', '종이뭉치', '꽃잎뭉치', '솔방울뭉치', '얼음뭉치',
  ])
  assert.equal(new Set(FRIENDS.map((f) => f.id)).size, 12)
  for (const f of FRIENDS) assert.match(f.color, /^#[0-9A-F]{6}$/, f.id)
  assert.equal(isFriendId('cone'), true)
  assert.equal(isFriendId('tori'), false)
})

test('서버 값 5종은 정해진 친구와 서로 대응하고, 나머지 7종은 서버 값이 없다', () => {
  for (const c of COMPANIONS) {
    assert.equal(companionToFriend(c.id), MAPPED[c.id], c.id)
    assert.equal(friendToCompanion(MAPPED[c.id]), c.id, c.id)
  }
  assert.deepEqual(FRIENDS.filter((f) => f.companion === null).map((f) => f.id), SOON)
  for (const id of SOON) assert.equal(friendToCompanion(id), null, id)
  // 기본(무료) 캐릭터 뭉치는 솜뭉치
  assert.equal(companionToFriend('mungchi'), 'cotton')
  assert.equal(companionToFriend('unknown' as CompanionId), 'cotton', '알 수 없는 값은 기본 친구')
})

test('화면에서 부르는 캐릭터 이름은 대응하는 친구 이름이다', () => {
  assert.deepEqual(COMPANIONS.map((c) => companionLabel(c.id)), ['솜뭉치', '솔방울뭉치', '모래뭉치', '이끼뭉치', '구름뭉치'])
  // 서버 아이템 이름(목업 목록 이름)은 그대로 둔다
  assert.deepEqual(COMPANIONS.map((c) => c.label), ['뭉치', '토리', '몽돌', '콩이', '몽글'])
})

test('친구 그림: 12종 모두 발·몸·얼굴을 그리고 친구마다 몸 색이 다르다', () => {
  const bodyColor: Record<FriendId, string> = {
    cotton: '#FFF6E9', cloud: '#CFE6FA', snow: '#BFDDF5', yarn: '#F7AEC4', moss: '#B4D69A', sand: '#EBCE96',
    star: '#FFDE6B', foam: '#DDD2F5', paper: '#F4F1E8', petal: '#F9B8CF', cone: '#B98857', ice: '#C4ECF7',
  }
  for (const f of FRIENDS) {
    const svg = renderToStaticMarkup(createElement('svg', { viewBox: FRIEND_VIEWBOX }, friendArt(f.id)))
    assert.match(svg, new RegExp(`data-friend="${f.id}"`), f.id)
    assert.ok(svg.includes(bodyColor[f.id]), `${f.id} 몸 색`)
    assert.ok(svg.includes('d="M91 148 Q100 158 109 148"'), `${f.id} 입`)
    assert.equal((svg.match(/<ellipse cx="(80|120)" cy="205"/g) ?? []).length, 2, `${f.id} 발`)
    assert.ok(svg.includes('stroke-width') && !svg.includes('strokeWidth'), `${f.id} 속성 이름이 SVG 이름으로 나온다`)
  }
})

test('서버 값 5종은 각각 대응하는 친구 그림으로 그린다', () => {
  for (const c of COMPANIONS) {
    const svg = renderToStaticMarkup(friendArt(companionToFriend(c.id)))
    assert.match(svg, new RegExp(`data-friend="${MAPPED[c.id]}"`), c.id)
  }
})

test('착용 기준점: 친구 12종 모두 칸마다 있고, 서버 값 기준점은 대응하는 친구 값이다', () => {
  for (const f of FRIENDS) for (const slot of WEAR_SLOTS) {
    const a = FRIEND_WEAR_ANCHORS[f.id][slot]
    assert.ok(Number.isFinite(a.x) && Number.isFinite(a.y) && a.scale > 0, `${f.id} ${slot}`)
  }
  for (const c of COMPANIONS) assert.deepEqual(WEAR_ANCHORS[c.id], FRIEND_WEAR_ANCHORS[MAPPED[c.id]], c.id)
  // 캔버스 HAT 표에서 옮긴 값: 솜뭉치 [0, 8, 1] → 가운데 (100, 48), 배율 2 / 모래뭉치 [0, 12, .86] → (100, 54.8), 1.7
  assert.deepEqual(FRIEND_WEAR_ANCHORS.cotton.HAT, { x: 100, y: 48, scale: 2 })
  assert.deepEqual(FRIEND_WEAR_ANCHORS.sand.HAT, { x: 100, y: 54.8, scale: 1.7 })
  assert.equal(friendById('sand').name, '모래뭉치')
})

test('친구 그림 보는 방향(캔버스 Mungchi view): 앞은 두 눈, 옆은 한 눈·옆 볼, 뒤는 얼굴 없이 등 선', () => {
  for (const id of ['cotton', 'star', 'ice'] as FriendId[]) {
    const html = (view: 'front' | 'side' | 'back') => renderToStaticMarkup(createElement('svg', null, friendArt(id, view)))
    const eyes = (s: string) => (s.match(/r="1?0"|r="9.5"/g) ?? []).length
    assert.match(html('front'), /data-view="front"/)
    assert.equal(eyes(html('front')), 2, `${id} 앞모습 눈 2개`)
    assert.equal(eyes(html('side')), 1, `${id} 옆모습 눈 1개`)
    assert.match(html('side'), /scale\(\.94 1\)/, `${id} 옆모습은 몸을 조금 좁게`)
    assert.equal(eyes(html('back')), 0, `${id} 뒷모습은 얼굴 없음`)
    assert.match(html('back'), /stroke-opacity="0.18"/, `${id} 뒷모습 등 선`)
  }
})
