/**
 * 학생 화면 둘러보기 대사(#1038, docs/proposals/onboarding.md 5.2). 화면 아래 대화창에서 캐릭터가 설명하며 화면을 옮겨 다닌다.
 * 강조할 곳은 각 화면의 `data-tour` 표시로 찾는다(CSS 클래스에 기대지 않음). 한 대사에 여러 경우(variants)를 두고,
 * 앞쪽 표시가 있으면 그것을, 없으면 뒤쪽(상태별 대체 대사)을 쓴다. ring이 false면 강조 없이 화면 전체만 어둡게 한다.
 * 화면 데이터: 홈 StudentHome, 내 공책 StudentJournal, 생각 활동 ThinkingActivities, 친구 생각 StudentCommunity, 내 방 StudentRoom
 * 첫 대사는 학부모가 답을 볼 수 있다는 고지를 겸한다(#1064, 완료 기록은 /students/me/onboarding 그대로).
 * 아이 화면이라 결제·이용권 문구는 넣지 않고, 시작 영상·오늘 장면·문제 화면 안으로는 들어가지 않는다(시도 기록이 생기지 않게)
 */
export type TourPage = 'home' | 'journal' | 'activities' | 'community' | 'room'
export type TourVariant = { target: string; ring?: boolean; line: (name: string) => string }
export type TourStep = { page: TourPage; variants: TourVariant[]; fallback: (name: string) => string }

/** 받침이 있으면 a, 없으면 b("솜뭉치야"·"이끼뭉치야", "솜뭉치와") */
export const josa = (word: string, withFinal: string, withoutFinal: string) => {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? withFinal : withoutFinal
}

const TODAY = "여기 '오늘 문제 풀기'를 누르면 그날 문제가 열려."
const DAYS = '월요일부터 금요일까지 하루에 하나씩 열려. 못 푼 날은 토요일까지 풀 수 있어.'
const COMMUNITY = "'친구 생각'에서는 친구들이 쓴 생각을 볼 수 있어. 친구들에게 내 답을 보여 줄지는 네가 정해."

export const TOUR_STEPS: TourStep[] = [
  { page: 'home', variants: [], fallback: (n) => `안녕! 나는 ${n}${josa(n, '이야', '야')}. 네가 쓴 답은 학부모님도 보실 수 있어. 지금부터 화면을 하나씩 같이 둘러보자!` },
  {
    page: 'home',
    variants: [
      { target: 'home-today', line: () => TODAY },
      { target: 'home-resume', line: () => "여기 '이어서 풀기'를 누르면 쓰던 오늘 문제가 다시 열려." },
      // 오늘 문제를 다 풀었거나 주말·정답 고르기처럼 큰 버튼이 다른 일일 때
      { target: 'home-no-today', ring: false, line: () => "오늘 풀 문제가 있는 날에는 여기에 '오늘 문제 풀기' 버튼이 생겨." },
      // 테마가 아직 안 열린 주
      { target: 'home-no-theme', ring: false, line: () => "이번 주 테마를 준비하고 있어. 테마가 열리면 여기에서 '오늘 문제 풀기'를 할 수 있어." },
    ],
    fallback: () => TODAY,
  },
  {
    page: 'home',
    variants: [
      { target: 'home-days', line: () => DAYS },
      { target: 'home-no-theme', ring: false, line: () => '테마가 열리면 월요일부터 금요일까지 하루에 하나씩 문제가 열려.' },
    ],
    fallback: () => DAYS,
  },
  {
    page: 'journal',
    variants: [
      { target: 'journal-tabs', line: () => "여기는 '내 공책'이야. 네가 쓴 답이 모두 여기에 남아." },
      // 빈 공책
      { target: 'journal-empty', ring: false, line: () => "여기는 '내 공책'이야. 아직 비어 있지만, 문제를 풀면 네가 쓴 답이 모두 여기에 남아." },
    ],
    fallback: () => "여기는 '내 공책'이야. 네가 쓴 답이 모두 여기에 남아.",
  },
  {
    page: 'activities',
    variants: [{ target: 'activities-list', line: () => "'생각 활동'에서는 다섯 가지 생각 놀이를 더 해 볼 수 있어." }],
    fallback: () => "'생각 활동'에서는 다섯 가지 생각 놀이를 더 해 볼 수 있어.",
  },
  {
    page: 'community',
    variants: [
      { target: 'community-posts', line: () => COMMUNITY },
      // 공개 미동의: 내 답이 친구들에게 안 보이는 상태
      { target: 'community-private', ring: false, line: () => "'친구 생각'에서는 친구들이 쓴 생각을 볼 수 있어. 지금은 내 답이 친구들에게 안 보여. 설정에서 바꿀 수 있어." },
      // 마무리한 미션이 없거나 친구 생각이 아직 없음
      { target: 'community-empty', ring: false, line: () => "'친구 생각'에서는 미션을 끝까지 한 뒤에 친구들이 쓴 생각을 볼 수 있어. 친구들에게 내 답을 보여 줄지는 네가 정해." },
    ],
    fallback: () => COMMUNITY,
  },
  {
    page: 'room',
    variants: [{ target: 'room-decor', line: () => '여기는 내 방! 문제를 풀고 모은 포인트로 방을 꾸밀 수 있어.' }],
    fallback: () => '여기는 내 방! 문제를 풀고 모은 포인트로 방을 꾸밀 수 있어.',
  },
  { page: 'home', variants: [], fallback: () => '이제 오늘 문제 풀러 가 볼까? 다시 보고 싶으면 도움말에서 언제든 불러 줘!' },
]

/** 주소 `?tour=N`(1부터)을 대사 순서(0부터)로. 범위 밖이면 null(둘러보기 꺼짐) */
export function tourIndex(search: string): number | null {
  const raw = new URLSearchParams(search).get('tour')
  const n = raw === null ? NaN : Number(raw)
  return Number.isInteger(n) && n >= 1 && n <= TOUR_STEPS.length ? n - 1 : null
}
export const tourPath = (index: number) => `/student/${TOUR_STEPS[index].page}?tour=${index + 1}`
/**
 * 이 탭에서 둘러보기가 이미 켜졌던 학생 ID. 자동 시작은 여기 없을 때만 한다.
 * 끝낸 직후 완료 기록 요청(PUT)이 아직 안 끝나 조회가 '미완료'로 남아 있어도 다시 1번부터 뜨지 않게(새로 고침 뒤 주소로 이어 본 경우 포함).
 * 기록이 실패하면 다음 접속(새 탭·새로 고침) 때 다시 뜬다
 */
export const tourSeen = new Set<string>()

/** 도움말 "화면 둘러보기 다시 하기": 서버 완료 기록은 그대로 두고 1번부터 */
export const TOUR_RESTART_PATH = tourPath(0)

export type TourLine = { line: string; target: string | null; ring: boolean }
/**
 * 화면에 있는 `data-tour` 표시(present)로 이 대사의 경우를 고른다. 앞쪽 경우가 먼저.
 * 아무것도 없으면 대체 대사(강조 없음)
 */
export function pickLine(step: TourStep, present: (target: string) => boolean, name: string): TourLine {
  for (const v of step.variants) if (present(v.target)) return { line: v.line(name), target: v.target, ring: v.ring !== false }
  return { line: step.fallback(name), target: null, ring: false }
}

/**
 * 대화창을 누르거나 Enter·Space: 글자가 다 안 나왔으면 남은 글자를 한 번에, 다 나왔으면 다음 대사, 마지막이면 끝
 */
export function tourAdvance(index: number, shown: number, length: number): { kind: 'reveal' } | { kind: 'next'; index: number } | { kind: 'finish' } {
  if (shown < length) return { kind: 'reveal' }
  return index + 1 >= TOUR_STEPS.length ? { kind: 'finish' } : { kind: 'next', index: index + 1 }
}

/** 끝까지 보거나 그만 볼래·Esc로 닫을 때 완료를 기록할지. 이미 기록이 있으면(다시 하기) 서버 기록을 그대로 둔다 */
export const shouldRecordTour = (completedAt: string | null | undefined) => completedAt === null
