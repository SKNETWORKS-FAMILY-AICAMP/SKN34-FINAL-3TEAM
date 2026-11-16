import type { ThemeId } from '../../../domain/studentLook.ts'

/**
 * 홈 "우리 집" 장면 그림(테마별)의 위치 값. 그림마다 5% 눈금을 그어 잰 값이다:
 * cx 발판 윗면 가로 가운데 x%, cb 발 bottom%(발판 윗면 앞뒤 가운데에 서도록), house 집 누르는 영역 [left, top, width, height]%.
 * 홈(HomeScene)과 꾸미기 화면 테마 미리 보기가 같이 써서 캐릭터가 같은 자리·비율로 선다(2026-11-16 "가운데 안 서 있어", "비율을 이런 식으로").
 */
export const SCENE: Record<ThemeId, { cx: number; cb: number; house: [number, number, number, number] }> = {
  lake: { cx: 52, cb: 39, house: [68, 15, 31, 34] },
  forest: { cx: 49, cb: 35.5, house: [68, 16, 31, 34] },
  factory: { cx: 52, cb: 32, house: [64, 18, 35, 40] },
  space: { cx: 52, cb: 35, house: [72, 21, 28, 35] },
  sea: { cx: 51, cb: 34, house: [70, 18, 30, 40] },
}
/** 캐릭터 폭(장면 그림 폭 %). 위치는 left = cx − 이 값의 절반 */
export const BUDDY_WIDTH = 18
