// 학부모 첫 사용 안내(#1037) 단계 데이터. 문구는 docs/proposals/onboarding.md 5.1 초안 기준.
// 웹 정적 데이터이며 서버 응답에 따라 바꾸지 않는다.

export type ParentGuideStep = {
  title: string
  body: string
  /** 강조할 메뉴 경로. 둘 이상이면 함께 강조하고 첫 메뉴 옆에 안내를 둔다. */
  targets: string[]
}

export const PARENT_GUIDE_DEVICES = '/parent/devices'
/** 도움말 "처음 안내 다시 보기"가 학습 현황으로 보낼 때 쓰는 이동 상태 */
export const parentGuideReplayState = { parentGuide: 'replay' } as const
export const isParentGuideReplay = (state: unknown) => (state as { parentGuide?: unknown } | null)?.parentGuide === 'replay'

export const parentGuideSteps: ParentGuideStep[] = [
  {
    title: '먼저 아이 기기를 등록해 주세요',
    body: '아이가 학습할 기기를 먼저 등록해 주세요. QR을 찍고 PIN을 정하면 아이가 바로 시작할 수 있습니다.',
    targets: ['/parent/devices'],
  },
  {
    title: '학습 현황과 리포트',
    body: '아이가 푼 문제와 답은 학습 현황에서, 일일·주간 리포트와 AI 챗봇 질문은 리포트에서 봅니다.',
    targets: ['/parent/journal', '/parent/report'],
  },
  {
    title: '공개 동의는 계정·자녀 설정에서',
    body: '친구들과 답을 나누려면 여기서 공개에 동의해 주세요. 공개는 아이가 직접 켭니다.',
    targets: ['/parent/settings'],
  },
]

// parentNavigation.tsx의 label·short와 같아야 한다(아이콘 JSX가 있어 Node 단위 시험에서 직접 못 읽는다).
const menuNames: Record<string, [label: string, short: string]> = {
  '/parent/journal': ['학습 현황', '학습'],
  '/parent/report': ['리포트·AI 챗봇', '리포트'],
  '/parent/settings': ['계정·자녀 설정', '설정'],
  '/parent/devices': ['기기·PIN', '기기'],
}
const menuLabel = (path: string, short = false) => menuNames[path]?.[short ? 1 : 0] ?? path
const quoted = (paths: string[], short = false) => paths.map(p => `'${menuLabel(p, short)}'`).join('·')

/**
 * 강조 메뉴가 어디에 보이는지 말로 안내한다.
 * - side: 왼쪽 메뉴에 보임(넓은 화면)
 * - bottom: 폰 하단 바에 짧은 이름으로 보임
 * - collapsed: 접힌 '메뉴' 창 안에 있음
 */
export function parentGuidePlace(targets: string[], where: 'side' | 'bottom' | 'collapsed') {
  if (where === 'side') return `왼쪽 메뉴의 ${quoted(targets)}입니다.`
  if (where === 'bottom') return `화면 아래 메뉴의 ${quoted(targets, true)}입니다.`
  return `화면 위 '메뉴'를 열면 ${quoted(targets)}이 있어요.`
}
