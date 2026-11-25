import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  TOUR_RESTART_PATH, TOUR_STEPS, josa, pickLine, shouldRecordTour, tourAdvance, tourIndex, tourPath,
} from '../src/presentation/student/world/tourSteps.ts'

// #1038 학생 화면 둘러보기: 대사 8개의 화면·강조 표시(data-tour), 넘기기·끝내기, 완료 기록, 다시 하기, 상태별 대체 대사
const world = (file: string) => readFileSync(new URL(`../src/presentation/student/world/${file}`, import.meta.url), 'utf8')
const PAGE_FILES: Record<string, string> = {
  home: 'StudentHome.tsx', journal: 'StudentJournal.tsx', activities: 'ThinkingActivities.tsx', community: 'StudentCommunity.tsx', room: 'StudentRoom.tsx',
}

test('대사 8개는 이슈 순서의 화면이고, 강조 표시(data-tour)가 그 화면 코드에 실제로 있다', () => {
  assert.deepEqual(TOUR_STEPS.map((s) => s.page), ['home', 'home', 'home', 'journal', 'activities', 'community', 'room', 'home'])
  for (const [i, step] of TOUR_STEPS.entries()) {
    const source = world(PAGE_FILES[step.page])
    for (const v of step.variants)
      assert.ok(source.includes(`'${v.target}'`) || source.includes(`"${v.target}"`), `${i + 1}번 ${v.target}가 ${PAGE_FILES[step.page]}에 없음`)
  }
  // 강조는 CSS 클래스가 아니라 data-tour로 찾는다
  assert.match(world('StudentTour.tsx'), /\[data-tour="\$\{target\}"\]/)
})

test('대사 문구: 이슈 초안 그대로, 캐릭터 이름과 조사, 결제·이용권 문구 없음', () => {
  const lines = (name: string) => TOUR_STEPS.map((s) => pickLine(s, (t) => s.variants[0]?.target === t, name).line)
  assert.deepEqual(lines('솜뭉치'), [
    '안녕! 나는 솜뭉치야. 지금부터 화면을 하나씩 같이 둘러보자!',
    "여기 '오늘 문제 풀기'를 누르면 그날 문제가 열려.",
    '월요일부터 금요일까지 하루에 하나씩 열려. 못 푼 날은 토요일까지 풀 수 있어.',
    "여기는 '내 공책'이야. 네가 쓴 답이 모두 여기에 남아.",
    "'생각 활동'에서는 다섯 가지 생각 놀이를 더 해 볼 수 있어.",
    "'친구 생각'에서는 친구들이 쓴 생각을 볼 수 있어. 내 답을 보여 줄지는 네가 정해.",
    '여기는 내 방! 문제를 풀고 모은 포인트로 방을 꾸밀 수 있어.',
    '이제 오늘 문제 풀러 가 볼까? 다시 보고 싶으면 도움말에서 언제든 불러 줘!',
  ])
  assert.equal(josa('솜뭉치', '이야', '야'), '야')
  assert.equal(josa('콩', '이야', '야'), '이야')
  const every = TOUR_STEPS.flatMap((s) => [s.fallback('솜뭉치'), ...s.variants.map((v) => v.line('솜뭉치'))])
  for (const line of every) assert.doesNotMatch(line, /결제|구매|이용권|프리미엄/)
})

test('상태별 대체 대사: 테마 없는 주·오늘 문제 없음·빈 공책·공개 미동의는 강조 없이 화면만 어둡게', () => {
  const only = (...targets: string[]) => (t: string) => targets.includes(t)
  const at = (i: number, ...targets: string[]) => pickLine(TOUR_STEPS[i], only(...targets), '솜뭉치')

  assert.deepEqual(at(1, 'home-today', 'home-days'), { line: "여기 '오늘 문제 풀기'를 누르면 그날 문제가 열려.", target: 'home-today', ring: true })
  assert.equal(at(1, 'home-resume').target, 'home-resume')
  assert.deepEqual({ ...at(1, 'home-no-today'), line: '' }, { line: '', target: 'home-no-today', ring: false })
  const noTheme = [at(1, 'home-no-theme'), at(2, 'home-no-theme')]
  for (const l of noTheme) assert.equal(l.ring, false)
  assert.match(noTheme[0].line, /테마를 준비하고 있어/)
  assert.match(noTheme[1].line, /테마가 열리면/)

  assert.equal(at(3, 'journal-tabs').ring, true)
  assert.deepEqual([at(3, 'journal-empty').ring, /아직 비어 있지만/.test(at(3, 'journal-empty').line)], [false, true])

  // 친구 생각: 친구 답이 있으면 목록 강조가 먼저, 없으면 공개 미동의 → 빈 목록 순
  assert.equal(at(5, 'community-posts', 'community-private').target, 'community-posts')
  assert.deepEqual([at(5, 'community-private', 'community-empty').target, at(5, 'community-private').ring], ['community-private', false])
  assert.match(at(5, 'community-private').line, /내 답이 친구들에게 안 보여/)
  assert.equal(at(5, 'community-empty').ring, false)

  // 표시를 끝내 못 찾으면 대체 대사(강조 없음)
  assert.deepEqual(at(6), { line: '여기는 내 방! 문제를 풀고 모은 포인트로 방을 꾸밀 수 있어.', target: null, ring: false })
})

test('넘기기: 글자가 덜 나왔으면 한 번에 다 보이고, 다 나왔으면 다음, 마지막이면 끝', () => {
  assert.deepEqual(tourAdvance(0, 3, 10), { kind: 'reveal' })
  assert.deepEqual(tourAdvance(0, 10, 10), { kind: 'next', index: 1 })
  assert.deepEqual(tourAdvance(6, 10, 10), { kind: 'next', index: 7 })
  assert.deepEqual(tourAdvance(7, 10, 10), { kind: 'finish' })
})

test('주소 ?tour=N으로 대사를 잇고, 범위 밖이면 꺼짐. 다시 하기는 홈 1번부터', () => {
  assert.equal(tourIndex('?tour=1'), 0)
  assert.equal(tourIndex('?tour=8'), 7)
  for (const bad of ['', '?tour=0', '?tour=9', '?tour=a', '?tour=1.5']) assert.equal(tourIndex(bad), null, bad)
  assert.equal(tourPath(3), '/student/journal?tour=4')
  assert.equal(TOUR_RESTART_PATH, '/student/home?tour=1')
  assert.match(world('StudentHelp.tsx'), /TOUR_RESTART_PATH[\s\S]*화면 둘러보기 다시 하기/)
})

test('완료 기록: 기록이 없을 때만 남기고, 다시 하기(이미 기록 있음)는 서버 기록을 그대로 둔다', () => {
  assert.equal(shouldRecordTour(null), true)
  assert.equal(shouldRecordTour('2026-11-24T09:00:00+09:00'), false)
  // 조회 전·실패면 모르는 상태라 기록하지 않는다(다음 홈 진입 때 다시 판단)
  assert.equal(shouldRecordTour(undefined), false)
  // 그만 볼래·Esc·끝까지 모두 같은 close로 기록한다
  const tour = world('StudentTour.tsx')
  assert.match(tour, /onClick=\{close\}>그만 볼래/)
  assert.match(tour, /e\.key === 'Escape'[\s\S]*close\(\)/)
  assert.match(tour, /kind === 'finish'\) close\(\)/)
})
