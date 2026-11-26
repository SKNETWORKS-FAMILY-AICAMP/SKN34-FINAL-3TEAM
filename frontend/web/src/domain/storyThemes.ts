/** learning StoryType와 같은 이야기 종류. 게시 테마의 제목·문제 제목과 구분한다. */
export const STORY_THEMES = [
  { key: 'LOST', label: '잃어버린 것 찾기' },
  { key: 'TREASURE', label: '보물 쪽지 따라가기' },
  { key: 'PRANK', label: '동물 장난꾸러기 찾기' },
  { key: 'FOOTPRINT', label: '발자국 주인 찾기' },
  { key: 'ORIGIN', label: '출처 찾기' },
  { key: 'GIFT', label: '선물 상자 수수께끼' },
  { key: 'SECRET_INGREDIENT', label: '비밀 재료 찾기' },
  { key: 'WHEN', label: '시간 탐정' },
  { key: 'ROUTE', label: '어느 길로 왔을까' },
  { key: 'VEHICLE', label: '무엇을 타고 왔을까' },
  { key: 'SOUND', label: '소리 탐정' },
] as const

export type StoryThemeType = typeof STORY_THEMES[number]['key']
