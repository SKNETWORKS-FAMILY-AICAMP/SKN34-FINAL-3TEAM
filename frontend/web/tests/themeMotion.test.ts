import test from 'node:test'
import assert from 'node:assert/strict'
import { effectParticles, effectVector, readThemeMotion } from '../src/domain/themeMotion.ts'
import type { MotionEffect } from '../src/domain/themeMotion.ts'

// #440 움직임 형식 v1을 ai 계약(ai-service.yaml ThemeMotion·models.py)대로 읽고 재생 값으로 바꾼다. 가상 값만 쓴다.
const aiMotion = {
  version: 1,
  transition: { kind: 'slide-left', seconds: 0.8 },
  camera: { from: { x: 50, y: 50, zoom: 1 }, to: { x: 30, y: 60, zoom: 1.4 }, seconds: 12 },
  speakers: { 뭉치: { x: 40, y: 70, zoom: 1.2 } },
  effects: [{ shape: 'leaf', color: '#8BC34A', count: 8, size: 3, direction: 20, speed: 5, opacity: 0.6 }],
  captions: [],
  spots: [{ x: 25, y: 70, label: '발자국', line: '어디로 이어질까?', evidence: true }, { x: 70, y: 40, label: '깃발', line: '바람 쪽', evidence: false }],
}

test('ai가 보내는 숫자 방향·확대 1.4·전환 종류를 그대로 읽는다(예전 웹은 방향을 글자로, 확대를 1~4로 읽었음)', () => {
  const m = readThemeMotion(aiMotion)!
  assert.equal(m.effects[0].direction, 20)
  assert.equal(m.camera?.to.zoom, 1.4)
  assert.equal(m.transition.kind, 'slide-left')
  assert.equal(m.spots.length, 2)
  // 같은 값을 다시 읽어도 같다(retention 응답을 읽은 값을 재생기가 다시 읽음)
  assert.deepEqual(readThemeMotion(m), m)
  // 예전 웹 목업 모양(방향 글자, 카메라 6초, 빠르기 1)은 계약 밖이라 그림만
  assert.equal(readThemeMotion({ ...aiMotion, effects: [{ ...aiMotion.effects[0], direction: 'up' }] }), null)
  assert.equal(readThemeMotion({ ...aiMotion, camera: { ...aiMotion.camera, seconds: 6 } }), null)
  assert.equal(readThemeMotion({ ...aiMotion, effects: [{ ...aiMotion.effects[0], speed: 1 }] }), null)
  assert.equal(readThemeMotion({ ...aiMotion, effects: [{ ...aiMotion.effects[0], shape: 'square' }] }), null)
  assert.equal(readThemeMotion({ ...aiMotion, camera: undefined }), null, '카메라 칸은 null로라도 와야 함')
})

test('효과 방향: 0은 아래로 떨어짐, 화면에서 시계 방향으로 90 왼쪽·180 위·270 오른쪽', () => {
  assert.deepEqual(effectVector(0), { dx: 0, dy: 1 })
  assert.deepEqual(effectVector(90), { dx: -1, dy: 0 })
  assert.deepEqual(effectVector(180), { dx: 0, dy: -1 })
  assert.deepEqual(effectVector(270), { dx: 1, dy: 0 })
})

const fx = (over: Partial<MotionEffect> = {}): MotionEffect => ({ shape: 'circle', color: '#FFFFFF', count: 10, size: 2, direction: 0, speed: 10, opacity: 0.5, ...over })

test('효과 입자: 크기는 그림 너비 %, 빠르기는 초당 그림 높이 %, 그림 밖에서 들어와 반대편 밖으로 나간다', () => {
  const w = 800, h = 450
  const down = effectParticles(fx(), w, h)
  assert.equal(down.length, 10)
  for (const p of down) {
    assert.equal(p.size, 16) // 800 × 2%
    assert.ok(p.y0 <= -p.size / 2 && p.y1 >= h + p.size / 2, '위 밖 → 아래 밖')
    assert.equal(p.x0, p.x1)
    assert.ok(p.x0 >= 0 && p.x0 <= w)
    // (450 + 2×16) px ÷ (450 × 10%/초)
    assert.ok(Math.abs(p.seconds - (h + 32) / 45) < 1e-9)
    assert.ok(p.delay <= 0 && p.delay > -p.seconds)
  }
  const up = effectParticles(fx({ direction: 180 }), w, h)
  assert.ok(up.every((p) => p.y0 > h && p.y1 < 0), '180은 아래에서 위로')
  const right = effectParticles(fx({ direction: 270 }), w, h)
  assert.ok(right.every((p) => p.x0 < 0 && p.x1 > w && p.y0 === p.y1 && p.y0 >= 0 && p.y0 <= h), '270은 왼쪽에서 오른쪽으로')
  // 들어오는 자리는 고르게(같은 자리에 몰리지 않음), 같은 값이면 늘 같은 자리
  assert.equal(new Set(down.map((p) => Math.round(p.x0))).size, 10)
  assert.deepEqual(effectParticles(fx(), w, h), down)
  assert.deepEqual(effectParticles(fx(), 0, h), [], '크기를 모르면 그리지 않음')
})
