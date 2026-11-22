import type { ErrorReport } from '../../domain/admin/operations.ts'
import type { ThemeGrade } from '../../domain/admin/retention.ts'
import type { Child, Mission } from '../../domain/classroom.ts'
import { fixtureStore } from './student.ts'
import {
  baseLookCatalog,
  companionKey,
  FREE_COMPANION,
  FREE_THEME,
  kstWeekday,
  POINT_RULES,
  REACTIONS,
  THEME_DAYS,
  themeKey,
} from '../../domain/retention.ts'
import type {
  ItemSlot,
  PointEvent,
  PointEventType,
  PostStatus,
  Reaction,
  ThemeDay,
} from '../../domain/retention.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import type { CompanionId } from '../../domain/studentLook.ts'

/**
 * 개발 목업 전용: 2026-11-06 결정(에픽 #396) 참여 기능의 가상 상태.
 * 실제 적립·해금·공개 판정은 core·learning 몫이고, 여기서는 화면 흐름을 확인할 만큼만 흉내 낸다.
 * 새로고침해도 유지되도록 sessionStorage에 가상 값만 둔다.
 */
const storageKey = 'sagomungchi:msw-retention:v1'
/** 요일을 바꿔 보려면 개발 도구에서 sessionStorage에 0(월)~6(일)을 넣는다. */
export const MOCK_WEEKDAY_KEY = 'sagomungchi:msw-weekday'

export interface MockPost {
  postId: string
  studentId: string
  nickname: string
  companion: CompanionId
  /** 작성자 착용(아이템 키). 친구 생각 응답의 `author.look.equipped`(#635) */
  equipped?: Partial<Record<'HAT' | 'OUTFIT' | 'ACCESSORY', string>>
  missionId: string
  missionTitle: string
  answer: string
  status: PostStatus
  createdAt: string
}
export interface MockLookItem {
  itemId: string
  code: string
  slot: ItemSlot
  name: string
  pricePoints: number
  assetKey: string
  status: 'ON_SALE' | 'STOPPED'
  /** 관리자 등록일(#704 학생 목록 `createdAt`). 전에 저장한 개발 상태에는 없어서 그때는 updatedAt을 쓴다 */
  createdAt?: string
  updatedAt: string
}
/** 방 소품 사기 응답(#704 `LookDecorPurchaseResult`) */
export interface MockDecorPurchase { itemKey: string; ownedCount: number; balance: number }
export interface MockWeeklyTheme {
  themeId: string
  missionSnapshots?: Mission[]
  version?: number
  grade: ThemeGrade
  weekStart: string
  title: string
  intro: string
  days: { day: ThemeDay; missionId: string }[]
  status: 'DRAFT' | 'REVIEW_REQUIRED' | 'PUBLISHED' | 'UNPUBLISHED'
  updatedAt: string
  /** 테마 초안 채택(#441 목업)에서 온 이야기 칸. 수정 본문에 없으면 이어받음 */
  outro?: string | null
  introImageUrl?: string | null
  outroImageUrl?: string | null
  introVideoUrl?: string | null
  outroVideoUrl?: string | null
  introMotion?: unknown
  outroMotion?: unknown
}
interface State {
  ledger: Record<string, (PointEvent & { sourceKey: string })[]>
  unlocked: Record<string, string[]>
  unlockKeys: Record<string, string>
  unlockResults: Record<string, { itemKey: string; unlocked: true; balance: number }>
  /** 방 소품 보유(#704): studentId → 아이템 코드 → 산 개수(core는 구매 1번 = 1행) */
  decor: Record<string, Record<string, number>>
  /** 방 소품 놓은 칸(#705, core #723 계약안): studentId → 칸 목록 */
  decorSpots?: Record<string, { surface: 'FLOOR' | 'WALL_BACK' | 'WALL_LEFT'; col: number; row: number; itemKey: string; color?: string | null }[]>
  /** 방 소품 사기 멱등 키: `학생:키` → 그 키로 산 아이템 코드 */
  purchaseKeys: Record<string, string>
  /** 방 소품 사기 멱등 키별 처음 응답(같은 키 재요청은 이 응답을 그대로) */
  purchaseResults: Record<string, MockDecorPurchase>
  community:Record<string, { enabled: boolean; updatedAt: string | null }>
  consent: Record<string, boolean>
  posts: MockPost[]
  communityReports: { reporterId: string; key: string; report: ErrorReport }[]
  /** postId → studentId → 반응 */
  reactions: Record<string, Record<string, Reaction[]>>
  reviewViews: string[]
  items: MockLookItem[]
  themes: MockWeeklyTheme[]
  /** `학생:주:INTRO|OUTRO` 이야기 열람 기록(주 1회). */
  storyViews: string[]
  /** `학생:주` → 큰 질문 정답 고르기(한 주 한 번). */
  picks: Record<string, { pick: string; correct: boolean; at: string }>
  /** `학생:주:미션` → 마지막 학습 완료 요일(0=월 … 6=일)·시각. 당일 풀이·틀린 뒤 다시 풀기 판정에 쓴다. */
  completions: Record<string, { weekday: number; at: string }>
  /** 기념 액자(P27): studentId → 보유 회차. 지난 주 회차만 */
  frames: Record<string, MockFrame[]>
  /** 추억의 벽: studentId → 슬롯 */
  frameSlots: Record<string, { slotNo: number; themeId: string; weekStart: string }[]>
}
export interface MockFrame {
  themeId: string
  weekStart: string
  title: string
  awardedAt: string
  seenAt: string | null
  missions: { day: ThemeDay; missionId: string; title: string; thinkingType: string }[]
  endingSeen: boolean
  outro: string
  answer: string
}

const now = () => new Date().toISOString()
const seedItems = (): MockLookItem[] => [
  // 관리자 칸·필터 시연용. 학생 그림 표(#705)와 연결되기 전에는 판매하지 않는다.
  { itemId: 'look-floor-preview', code: 'FLOOR_PREVIEW', slot: 'FLOOR', name: '바닥 예시', pricePoints: 30, assetKey: 'room/floor-grass.png', status: 'STOPPED', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-preview', code: 'DECOR_PREVIEW', slot: 'DECOR', name: '방 소품 예시', pricePoints: 30, assetKey: 'room/decor-plant.png', status: 'STOPPED', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-hat-1', code: 'HAT_ACORN', slot: 'HAT', name: '도토리 모자', pricePoints: 40, assetKey: 'looks/hat-acorn.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-outfit-1', code: 'OUTFIT_RAIN', slot: 'OUTFIT', name: '노란 비옷', pricePoints: 60, assetKey: 'looks/outfit-rain.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-acc-1', code: 'ACC_LENS', slot: 'ACCESSORY', name: '돋보기', pricePoints: 30, assetKey: 'looks/acc-lens.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-bg-1', code: 'BG_STARS', slot: 'BACKGROUND', name: '별빛 배경', pricePoints: 50, assetKey: 'looks/bg-stars.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-hat-2', code: 'HAT_CROWN', slot: 'HAT', name: '종이 왕관', pricePoints: 80, assetKey: 'looks/hat-crown.svg', status: 'STOPPED', updatedAt: '2026-11-06T00:00:00Z' },
  // 내 방 가구 추가 스킨(P27, #557 기준안). 기본 스킨은 착용 칸이 비었을 때 그려서 아이템으로 두지 않는다
  { itemId: 'look-desk-1', code: 'DESK_MINT', slot: 'DESK', name: '민트 책상', pricePoints: 60, assetKey: 'room/desk-mint.svg', status: 'ON_SALE', updatedAt: '2026-11-12T00:00:00Z' },
  { itemId: 'look-desk-2', code: 'DESK_NIGHT', slot: 'DESK', name: '밤하늘 책상', pricePoints: 120, assetKey: 'room/desk-night.svg', status: 'ON_SALE', updatedAt: '2026-11-12T00:00:00Z' },
  { itemId: 'look-wall-1', code: 'WALL_WOOD', slot: 'WALL', name: '나무 벽', pricePoints: 60, assetKey: 'room/wall-wood.svg', status: 'ON_SALE', updatedAt: '2026-11-12T00:00:00Z' },
  { itemId: 'look-wall-2', code: 'WALL_PASTEL', slot: 'WALL', name: '구름 벽', pricePoints: 120, assetKey: 'room/wall-pastel.svg', status: 'ON_SALE', updatedAt: '2026-11-12T00:00:00Z' },
  { itemId: 'look-wardrobe-1', code: 'WARDROBE_SKY', slot: 'WARDROBE', name: '하늘 옷장', pricePoints: 60, assetKey: 'room/wardrobe-sky.svg', status: 'ON_SALE', updatedAt: '2026-11-12T00:00:00Z' },
  { itemId: 'look-wardrobe-2', code: 'WARDROBE_BERRY', slot: 'WARDROBE', name: '딸기 옷장', pricePoints: 120, assetKey: 'room/wardrobe-berry.svg', status: 'ON_SALE', updatedAt: '2026-11-12T00:00:00Z' },
  // 목업에서 살 것을 늘림(2026-11-16, 내 방 세트: 책상 → 책장, 옷장 → 문, 추억의 벽 → 액자 테두리, 벽지 → 바닥·러그·커튼)
  { itemId: 'look-desk-3', code: 'DESK_CHERRY', slot: 'DESK', name: '체리 책상', pricePoints: 90, assetKey: 'room/desk-cherry.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-wall-3', code: 'WALL_STAR', slot: 'WALL', name: '별빛 벽', pricePoints: 90, assetKey: 'room/wall-star.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-wardrobe-3', code: 'WARDROBE_LEMON', slot: 'WARDROBE', name: '레몬 옷장', pricePoints: 90, assetKey: 'room/wardrobe-lemon.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-bg-2', code: 'BG_CREAM', slot: 'BACKGROUND', name: '크림 줄무늬', pricePoints: 40, assetKey: 'room/wall-cream.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-bg-3', code: 'BG_SKY', slot: 'BACKGROUND', name: '하늘 구름', pricePoints: 60, assetKey: 'room/wall-sky.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  // 설계 캔버스 Mungchi의 나머지 착용 그림(public/student-assets/looks, 2026-11-16 사용자 의견 "꾸미기에서 옷이 안 돼")
  { itemId: 'look-hat-3', code: 'HAT_DETECTIVE', slot: 'HAT', name: '탐정 모자', pricePoints: 60, assetKey: 'looks/hat-detective.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-hat-4', code: 'HAT_RESCUE', slot: 'HAT', name: '구조대 모자', pricePoints: 60, assetKey: 'looks/hat-rescue.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-hat-5', code: 'HAT_PATROL', slot: 'HAT', name: '순찰대 모자', pricePoints: 60, assetKey: 'looks/hat-patrol.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-outfit-2', code: 'OUTFIT_RESCUE', slot: 'OUTFIT', name: '구조대 조끼', pricePoints: 80, assetKey: 'looks/outfit-rescue.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-outfit-3', code: 'OUTFIT_PATROL', slot: 'OUTFIT', name: '순찰대 옷', pricePoints: 80, assetKey: 'looks/outfit-patrol.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  { itemId: 'look-acc-2', code: 'ACC_LIGHT', slot: 'ACCESSORY', name: '손전등', pricePoints: 40, assetKey: 'looks/acc-light.svg', status: 'ON_SALE', updatedAt: '2026-11-16T00:00:00Z' },
  // 내 방 바닥(#704 FLOOR, #705 기준안): 시안 MyPage 서랍 "바닥". 해금·착용은 가구와 같고 가격도 가구 가격대(60·90·120)
  { itemId: 'look-floor-1', code: 'FLOOR_WOOD', slot: 'FLOOR', name: '나무 마루', pricePoints: 60, assetKey: 'room/floor-wood.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-floor-2', code: 'FLOOR_MINT', slot: 'FLOOR', name: '민트 타일', pricePoints: 90, assetKey: 'room/floor-mint.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-floor-3', code: 'FLOOR_CARPET', slot: 'FLOOR', name: '초록 카펫', pricePoints: 120, assetKey: 'room/floor-carpet.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  // 방 소품(#704 DECOR, #705 기준안): 시안 MyPage 서랍 "소품". 여러 개 사므로 가구 한 개(60)보다 낮게, 착용 소품(30·40)·벽지(40·60) 가격대
  // 방 소품 15가지(#705 기준안, 사용자 결정 2026-11-17 "여러 개, 색상이든 크기든"): 색은 놓을 때 고른다(core #723 color). 일부만 최근 등록(새로 나왔어요)
  { itemId: 'look-decor-1', code: 'DECOR_PLANT', slot: 'DECOR', name: '작은 화분', pricePoints: 30, assetKey: 'room/decor-plant.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-2', code: 'DECOR_PLANT_BIG', slot: 'DECOR', name: '큰 화분', pricePoints: 50, assetKey: 'room/decor-plant-big.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-3', code: 'DECOR_CACTUS', slot: 'DECOR', name: '선인장', pricePoints: 30, assetKey: 'room/decor-cactus.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-4', code: 'DECOR_LAMP', slot: 'DECOR', name: '스탠드 조명', pricePoints: 50, assetKey: 'room/decor-lamp.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-5', code: 'DECOR_DOLL', slot: 'DECOR', name: '뭉치 인형', pricePoints: 60, assetKey: 'room/decor-doll.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-6', code: 'DECOR_BOOKS', slot: 'DECOR', name: '쌓은 책', pricePoints: 20, assetKey: 'room/decor-books.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-7', code: 'DECOR_BEANBAG', slot: 'DECOR', name: '쿠션 소파', pricePoints: 70, assetKey: 'room/decor-beanbag.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-8', code: 'DECOR_RUG', slot: 'DECOR', name: '동그란 러그', pricePoints: 50, assetKey: 'room/decor-rug.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-9', code: 'DECOR_RUG_SQUARE', slot: 'DECOR', name: '네모 러그', pricePoints: 60, assetKey: 'room/decor-rug-square.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-10', code: 'DECOR_RUG_STAR', slot: 'DECOR', name: '별 러그', pricePoints: 60, assetKey: 'room/decor-rug-star.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-11', code: 'DECOR_LIGHTS', slot: 'DECOR', name: '줄 조명', pricePoints: 40, assetKey: 'room/decor-lights.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-12', code: 'DECOR_GARLAND', slot: 'DECOR', name: '깃발 가랜드', pricePoints: 40, assetKey: 'room/decor-garland.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
  { itemId: 'look-decor-13', code: 'DECOR_CLOCK', slot: 'DECOR', name: '벽시계', pricePoints: 30, assetKey: 'room/decor-clock.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-14', code: 'DECOR_PICTURE', slot: 'DECOR', name: '작은 그림', pricePoints: 30, assetKey: 'room/decor-picture.svg', status: 'ON_SALE', createdAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z' },
  { itemId: 'look-decor-15', code: 'DECOR_SHELF', slot: 'DECOR', name: '벽 선반', pricePoints: 50, assetKey: 'room/decor-shelf.svg', status: 'ON_SALE', createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z' },
]
const empty = (): State => ({
  ledger: {},
  unlocked: {},
  unlockKeys: {},
  unlockResults: {},
  decor: {},
  decorSpots: {},
  purchaseKeys: {},
  purchaseResults: {},
  community: {},
  consent: {},
  posts: [],
  communityReports: [],
  reactions: {},
  reviewViews: [],
  items: seedItems(),
  themes: [],
  storyViews: [],
  picks: {},
  completions: {},
  frames: {},
  frameSlots: {},
})
export const retentionState: State = (() => {
  if (typeof sessionStorage === 'undefined') return empty()
  try {
    const raw = sessionStorage.getItem(storageKey)
    if (!raw) return empty()
    const loaded = { ...empty(), ...(JSON.parse(raw) as Partial<State>) }
    // 전에 저장한 개발 상태에도 새로 넣은 목업 아이템(가구 스킨 등)이 보이게 코드 기준으로 채운다
    const codes = new Set(loaded.items.map((i) => i.code))
    loaded.items = [...loaded.items, ...seedItems().filter((i) => !codes.has(i.code))]
    return loaded
  } catch {
    return empty()
  }
})()
export function persistRetention() {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(retentionState))
  } catch {
    /* 저장소를 못 쓰면 메모리 값만 유지 */
  }
}
export function resetRetention() {
  Object.assign(retentionState, empty())
  persistRetention()
}

export function mockWeekday() {
  try {
    const raw = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(MOCK_WEEKDAY_KEY)
    const n = raw === null ? NaN : Number(raw)
    if (Number.isInteger(n) && n >= 0 && n <= 6) return n
  } catch {
    /* 기본은 실제 요일 */
  }
  return kstWeekday()
}
/** 이번 주 월요일(KST) 날짜. */
export function weekStart(date = new Date()) {
  const kst = new Date(date.getTime() + 9 * 3600_000)
  kst.setUTCDate(kst.getUTCDate() - ((kst.getUTCDay() + 6) % 7))
  return kst.toISOString().slice(0, 10)
}

// ---------- 포인트 ----------
const rule = (type: Exclude<PointEventType, 'UNLOCK'>) => POINT_RULES.find((r) => r.type === type)!.amount
/** 처음 보는 학생은 해금을 시험할 수 있게 가상 적립 내역(합계 117)을 조금 둔다. */
function ledgerOf(studentId: string) {
  if (!retentionState.ledger[studentId]) {
    retentionState.ledger[studentId] = [
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-03T01:00:00Z', sourceKey: 'seed-1' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-04T01:00:00Z', sourceKey: 'seed-2' },
      { eventType: 'REVIEW_VIEWED', amount: 10, createdAt: '2026-11-01T01:00:00Z', sourceKey: 'seed-3' },
      { eventType: 'THEME_COMPLETED', amount: 30, createdAt: '2026-11-01T01:00:00Z', sourceKey: 'seed-4' },
      { eventType: 'COMMUNITY_POSTED', amount: 5, createdAt: '2026-11-04T01:10:00Z', sourceKey: 'seed-5' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-05T01:00:00Z', sourceKey: 'seed-6' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-06T01:00:00Z', sourceKey: 'seed-7' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-07T01:00:00Z', sourceKey: 'seed-8' },
      { eventType: 'REACTION_GIVEN', amount: 1, createdAt: '2026-11-07T02:00:00Z', sourceKey: 'seed-9' },
      { eventType: 'REACTION_GIVEN', amount: 1, createdAt: '2026-11-07T02:01:00Z', sourceKey: 'seed-10' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-10-31T01:00:00Z', sourceKey: 'seed-11' },
      { eventType: 'REVIEW_VIEWED', amount: 10, createdAt: '2026-10-25T01:00:00Z', sourceKey: 'seed-12' },
    ]
  }
  return retentionState.ledger[studentId]
}
export const balanceOf = (studentId: string) => ledgerOf(studentId).reduce((sum, e) => sum + e.amount, 0)
export function pointsOf(studentId: string, page = 0, size = 20) {
  const items = [...ledgerOf(studentId)].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  return {
    balance: balanceOf(studentId),
    items: items.slice(page * size, page * size + size).map(({ eventType, amount, createdAt }) => ({ eventType, amount, createdAt })),
    page, size, totalElements: items.length,
  }
}
/** 같은 사건 키는 한 번만 적립(원장 UK `(student_id, event_type, source_key)` 흉내). */
export function earn(studentId: string, eventType: Exclude<PointEventType, 'UNLOCK'>, sourceKey: string) {
  const ledger = ledgerOf(studentId)
  if (ledger.some((e) => e.eventType === eventType && e.sourceKey === sourceKey)) return false
  if (eventType === 'REACTION_GIVEN') {
    const today = now().slice(0, 10)
    if (ledger.filter((e) => e.eventType === eventType && e.createdAt.startsWith(today)).length >= 5) return false
  }
  ledger.push({ eventType, amount: rule(eventType), createdAt: now(), sourceKey })
  return true
}

// ---------- 꾸미기 ----------
export const unlockedOf = (studentId: string) => (retentionState.unlocked[studentId] ??= [])
/** 방 소품 보유 개수(#704): 아이템 코드 → 산 개수 */
export const decorOf = (studentId: string) => (retentionState.decor[studentId] ??= {})
/**
 * 학생 꾸미기 목록(core `LookUnlockService.catalog` 흉내). 방 소품은 보유 개수 `ownedCount`(0이면 unlocked false),
 * 다른 칸은 null. `createdAt`은 관리자 등록일, 테마·캐릭터는 null. 판매 중단은 가진 학생에게만 보인다.
 */
export function lookCatalog(studentId: string) {
  const owned = new Set(unlockedOf(studentId))
  const decor = decorOf(studentId)
  return [
    ...baseLookCatalog().map((i) => ({
      ...i,
      unlocked: i.itemKey === themeKey(FREE_THEME) || i.itemKey === companionKey(FREE_COMPANION) || owned.has(i.itemKey),
    })),
    ...retentionState.items.map((i) => ({
      itemKey: i.code,
      slot: i.slot,
      name: i.name,
      pricePoints: i.pricePoints,
      unlocked: i.slot === 'DECOR' ? (decor[i.code] ?? 0) > 0 : owned.has(i.code),
      onSale: i.status === 'ON_SALE',
      assetKey: i.assetKey,
      ownedCount: i.slot === 'DECOR' ? decor[i.code] ?? 0 : null,
      createdAt: i.createdAt ?? i.updatedAt,
    })),
  ].filter((i) => i.onSale || i.unlocked)
}
export function isUnlocked(studentId: string, itemKey: string) {
  return lookCatalog(studentId).some((i) => i.itemKey === itemKey && i.unlocked)
}

// ---------- 주간 테마 ----------
/** 게시된 관리자 테마가 있으면 그것을, 없으면 학생 미션으로 다섯 유형 하나씩 고른 가상 테마를 쓴다. */
export function themeMissions(missions: Mission[], grade: number) {
  const published = retentionState.themes.find((t) => t.status === 'PUBLISHED' && t.weekStart === weekStart() && t.grade === `G${Math.min(grade, 6)}`)
  if (published) {
    const byId = new Map(missions.map((m) => [m.id, m]))
    const days = published.days.flatMap((d) => {
      const live = byId.get(d.missionId)
      const snapshot = published.missionSnapshots?.find(m => m.id === d.missionId)
      const mission = snapshot ? { ...snapshot, grade, status: live?.status, attemptId: live?.attemptId } : live
      return mission ? [{ day: d.day, mission }] : []
    })
    // 테마 초안 채택(#441 목업)이나 관리자가 넣은 그림·영상·움직임도 학생 응답에 그대로(실서버처럼, #440)
    const scene = { introImageUrl: published.introImageUrl ?? null, introVideoUrl: published.introVideoUrl ?? null, introMotion: published.introMotion ?? null,
      outroImageUrl: published.outroImageUrl ?? null, outroVideoUrl: published.outroVideoUrl ?? null, outroMotion: published.outroMotion ?? null }
    if (days.length === 5) return { themeId: published.themeId, title: published.title, intro: published.intro, reused: false, days, scene }
  }
  const picked = THINKING_ORDER.map((type) => missions.find((m) => m.thinkingType === type)).filter((m): m is Mission => !!m)
  return {
    themeId: `mock-theme-${weekStart()}`,
    title: '이야기 마을의 수수께끼',
    intro: '이번 주에는 이야기 마을에서 일어난 일을 하루에 하나씩 살펴봐요. 금요일까지 다섯 가지 생각을 써 보면 마을의 수수께끼가 풀려요.',
    reused: picked.length < 5,
    days: picked.slice(0, 5).map((mission, i) => ({ day: THEME_DAYS[i], mission })),
    scene: null,
  }
}
/**
 * 가상 테마의 큰 질문·후보·요일 단서(#438 모양). 단서는 rulesOut이 빈 날(힌트)도 섞고,
 * 마지막 틀린 후보는 목요일에 빠진다(기준안 "금요일 전에 답이 드러나지 않게").
 */
export const MOCK_STORY = {
  bigQuestion: '마을 시계탑의 종을 밤마다 몰래 울린 건 누구일까?',
  candidates: ['다람쥐 우체부', '고양이 빵집 주인', '부엉이 선생님', '토끼 정원사'],
  answer: '부엉이 선생님',
  clues: [
    { clue: '종 아래에 도토리 껍질이 하나도 없었어요.', rulesOut: ['다람쥐 우체부'] },
    { clue: '그날 밤 빵집은 일찍 불이 꺼져 있었어요.', rulesOut: ['고양이 빵집 주인'] },
    { clue: '종은 늘 밤 열두 시에만 울렸어요.', rulesOut: [] },
    { clue: '정원사는 그 시각 연못가에서 물을 주고 있었어요.', rulesOut: ['토끼 정원사'] },
    { clue: '종 옆 난간에 커다란 깃털 하나가 걸려 있었어요.', rulesOut: [] },
  ],
  /**
   * 후보 특징 표(#647 단서 근거). 요일 단서는 이 표의 한 특징으로 후보를 뺀다. 학생에게는 단서를 얻은 요일 특징만, 엔딩 뒤에는 전체.
   * 수요일·금요일은 힌트(새로 빠지는 후보 없음). 목요일까지 정답(부엉이 선생님)이 드러나지 않게 값을 골랐다.
   */
  features: [
    { name: '도토리를 먹나요', values: [['다람쥐 우체부', '먹어요'], ['고양이 빵집 주인', '안 먹어요'], ['부엉이 선생님', '안 먹어요'], ['토끼 정원사', '안 먹어요']] },
    { name: '그날 밤 일하는 곳 불', values: [['다람쥐 우체부', '켜짐'], ['고양이 빵집 주인', '꺼짐'], ['부엉이 선생님', '켜짐'], ['토끼 정원사', '켜짐']] },
    { name: '밤 열두 시에', values: [['다람쥐 우체부', '깨어 있어요'], ['고양이 빵집 주인', '깨어 있어요'], ['부엉이 선생님', '깨어 있어요'], ['토끼 정원사', '깨어 있어요']] },
    { name: '그 시각 있던 곳', values: [['다람쥐 우체부', '시계탑 광장'], ['고양이 빵집 주인', '빵집'], ['부엉이 선생님', '시계탑 광장'], ['토끼 정원사', '연못가']] },
    { name: '깃털이 있나요', values: [['다람쥐 우체부', '없어요'], ['고양이 빵집 주인', '없어요'], ['부엉이 선생님', '있어요'], ['토끼 정원사', '없어요']] },
  ].map((f) => ({ name: f.name, values: f.values.map(([candidate, value]) => ({ candidate, value })) })),
  outro: '부엉이 선생님은 밤에 잠들지 못하는 아기 새들을 위해 종을 울려 자장가 시간을 알려 주고 있었어요. 마을 사람들은 이제 열두 시 종소리를 들으면 미소를 지어요.',
}
/** 목업 가상 테마의 시작·끝 장면(2D 만화풍 생성 그림, 목업 전용)과 움직임 v1 예시(카메라·컷 문구·효과). */
const MOCK_SCENE = {
  intro: '/demo/story/intro.jpg',
  outro: '/demo/story/outro.jpg',
  motion: (lines: string[]) => ({
    version: 1,
    transition: { kind: 'fade', seconds: 0.6 },
    camera: { from: { x: 50, y: 40, zoom: 1.18 }, to: { x: 50, y: 55, zoom: 1 }, seconds: 12 },
    speakers: {},
    effects: [{ shape: 'star', color: '#FFE08A', count: 10, size: 3, direction: 180, speed: 4, opacity: 0.6 }],
    captions: lines.map((text, i) => ({ start: i * 4, end: i * 4 + 4, text })),
    spots: [],
  }),
}
const FRIDAY = 4
const isPremium = (plan?: 'FREE' | 'PREMIUM') => plan === 'PREMIUM'
/** 날짜 판정은 learning 몫: 목업은 요일(sessionStorage로 바꿔 보기)과 요금제로만 흉내 낸다. */
export function weekRules(weekday: number, plan?: 'FREE' | 'PREMIUM') {
  const sunday = weekday === 6
  const sundayTheme = sunday && isPremium(plan)
  return {
    sundayTheme,
    /** 무료 일요일: 테마 닫힘(풀기·다시 풀기·새 이야기·정답 고르기 불가). */
    closed: sunday && !sundayTheme,
    /** 토요일·프리미엄 일요일: 안 푼 문제 새로 풀기·다시 풀기·되돌아보기. */
    weekend: weekday === 5 || sundayTheme,
  }
}
const completionKey = (studentId: string, missionId: string) => `${studentId}:${weekStart()}:${missionId}`
/** 학습 완료 시각을 남긴다(core가 아닌 learning 판정 흉내: 당일 풀이·틀린 뒤 금요일 다시 풀기). */
export function recordCompletion(studentId: string, missionId: string) {
  retentionState.completions[completionKey(studentId, missionId)] = { weekday: mockWeekday(), at: now() }
}
export function weeklyThemeFor(studentId: string, missions: Mission[], grade: number, plan?: 'FREE' | 'PREMIUM') {
  const weekday = mockWeekday()
  const rules = weekRules(weekday, plan)
  const theme = themeMissions(missions, grade)
  const week = `${studentId}:${weekStart()}`
  const days = theme.days.map(({ day, mission }, i) => {
    const past = mission.status ? undefined : fixtureStore.snapshot().attempts.filter(a => a.studentId === studentId && a.mission.id === mission.id)
    const latest = past?.find(a => a.status === 'IN_PROGRESS') ?? past?.at(-1)
    const attemptStatus = mission.status ?? latest?.status ?? 'NOT_STARTED'
    const done = attemptStatus === 'COMPLETED'
    const completion = retentionState.completions[completionKey(studentId, mission.id)]
    return {
      day,
      missionId: mission.id,
      thinkingType: mission.thinkingType,
      title: mission.title,
      // 공개된 문제는 토요일(프리미엄 일요일)까지 쌓여 열려 있다. 무료 일요일은 모두 닫힘(#484).
      state: rules.closed ? 'CLOSED' : rules.weekend || i <= weekday ? 'OPEN' : 'LOCKED',
      attemptStatus,
      clue: done ? MOCK_STORY.clues[i].clue : null,
      rulesOut: done ? MOCK_STORY.clues[i].rulesOut : null,
      completedOnDay: done && completion?.weekday === i,
      clueFeature: done ? MOCK_STORY.features[i].name : null,
      clueFacts: done ? MOCK_STORY.features[i].values : null,
    }
  })
  const picked = retentionState.picks[week]
  const fridayMission = days[FRIDAY]?.missionId
  const fridayRedo = fridayMission ? retentionState.completions[completionKey(studentId, fridayMission)] : undefined
  // 틀렸으면 고른 뒤 토요일(프리미엄 일요일) 금요일 문제 다시 풀기를 마무리해야 엔딩(맞든 틀리든 정답 공개).
  const ended = !!picked && (picked.correct || (!!fridayRedo && fridayRedo.weekday >= 5 && fridayRedo.at > picked.at))
  const hasStory = days.length === 5
  // 관리자가 게시한 테마가 아니면(가상 테마) 목업 장면 그림을 붙인다
  const mockScene = hasStory && theme.themeId.startsWith('mock-theme-')
  return {
    themeId: theme.themeId,
    weekStart: weekStart(),
    title: theme.title,
    intro: theme.intro,
    reused: theme.reused,
    days,
    review: {
      open: rules.weekend,
      missions: days.map((d) => ({
        missionId: d.missionId,
        title: d.title,
        completed: d.attemptStatus === 'COMPLETED',
        missed: d.state !== 'LOCKED' && d.attemptStatus !== 'COMPLETED',
      })),
    },
    completed: days.length === 5 && days.every((d) => d.completedOnDay),
    // 목업은 일요일 완료를 따로 세지 않는다(실제 판정은 learning #484).
    finished: days.length === 5 && days.every((d) => d.attemptStatus === 'COMPLETED'),
    ending: ended ? 'ENDED' : 'NOT_ENDED',
    bigQuestion: hasStory ? MOCK_STORY.bigQuestion : null,
    candidates: hasStory ? MOCK_STORY.candidates : null,
    introImageUrl: mockScene ? MOCK_SCENE.intro : (theme.scene?.introImageUrl ?? null),
    introVideoUrl: theme.scene?.introVideoUrl ?? null,
    introMotion: mockScene ? MOCK_SCENE.motion(['밤마다 시계탑 종이 울렸어', '누가 울린 걸까?', '하루에 하나씩 단서를 모아 보자']) : (theme.scene?.introMotion ?? null),
    introSeen: retentionState.storyViews.includes(`${week}:INTRO`),
    outroSeen: retentionState.storyViews.includes(`${week}:OUTRO`),
    outro: ended ? MOCK_STORY.outro : null,
    outroImageUrl: !ended ? null : mockScene ? MOCK_SCENE.outro : (theme.scene?.outroImageUrl ?? null),
    outroVideoUrl: ended ? (theme.scene?.outroVideoUrl ?? null) : null,
    outroMotion: !ended ? null : mockScene ? MOCK_SCENE.motion(['종을 울린 건 부엉이 선생님!', '아기 새들의 자장가 시간이었어']) : (theme.scene?.outroMotion ?? null),
    answer: ended ? MOCK_STORY.answer : null,
    answerClue: ended ? MOCK_STORY.clues[3].clue : null,
    answerPick: picked ? { pick: picked.pick, correct: picked.correct } : null,
    features: ended && hasStory ? MOCK_STORY.features : null,
  }
}

// ---------- 커뮤니티 ----------
const friends: { nickname: string; companion: CompanionId; equipped?: MockPost['equipped']; answer: (title: string) => string }[] = [
  { nickname: '하늘별', companion: 'tori', equipped: { HAT: 'HAT_ACORN' }, answer: (t) => `${t}에서 나는 먼저 무엇이 달라졌는지 찾았어. 왜냐하면 달라진 곳에 까닭이 숨어 있을 것 같았거든.` },
  { nickname: '초록콩', companion: 'kongi', equipped: { OUTFIT: 'OUTFIT_RAIN', ACCESSORY: 'ACC_LENS' }, answer: () => '나는 다른 방법도 생각해 봤어. 그래서 두 가지를 비교하니까 하나가 더 알맞아 보였어.' },
  { nickname: '구름빵', companion: 'snow', answer: () => '처음엔 잘 모르겠었는데 그림을 다시 보니 순서가 보였어. 그 순서대로 쓰면 이해가 돼.' },
]
/**
 * 목업 친구 방(#709): 친구 순서(`friend-0`…)와 같다. 그림 키는 서버처럼 `look_item.asset_key` 그대로.
 * 하늘별은 꾸민 방·액자 두 장, 초록콩은 다른 색·민트 타일 바닥(#705)·그림 없는 액자 한 장, 구름빵은 기본 방(꾸미지 않음)
 */
export const FRIEND_ROOMS: {
  wallpaper: string | null
  floor: string | null
  furniture: { DESK: string | null; WALL: string | null; WARDROBE: string | null }
  frames: { title: string; withImage: boolean }[]
  /** 친구가 놓은 방 소품(#723 칸 모양) */
  decor?: { surface: 'FLOOR' | 'WALL_BACK' | 'WALL_LEFT'; col: number; row: number; color?: string | null; assetKey: string }[]
}[] = [
  { wallpaper: 'room/wall-sky.svg', floor: null, furniture: { DESK: 'room/desk-cherry.svg', WALL: null, WARDROBE: 'room/wardrobe-berry.svg' },
    frames: [{ title: '잃어버린 지도 조각', withImage: true }, { title: '별빛 우체국', withImage: true }],
    decor: [{ surface: 'FLOOR', col: 12, row: 4, color: 'white', assetKey: 'room/decor-plant-big.svg' }, { surface: 'FLOOR', col: 9, row: 6, color: 'pink', assetKey: 'room/decor-rug.svg' },
      { surface: 'FLOOR', col: 7, row: 8, color: 'sky', assetKey: 'room/decor-beanbag.svg' }, { surface: 'WALL_BACK', col: 3, row: 2, color: null, assetKey: 'room/decor-lights.svg' }, { surface: 'WALL_LEFT', col: 1, row: 2, color: 'pink', assetKey: 'room/decor-clock.svg' }] },
  { wallpaper: 'room/wall-cream.svg', floor: 'room/floor-mint.svg', furniture: { DESK: 'room/desk-mint.svg', WALL: 'room/wall-wood.svg', WARDROBE: 'room/wardrobe-lemon.svg' },
    frames: [{ title: '숲속 발명 대회', withImage: false }] },
  { wallpaper: null, floor: null, furniture: { DESK: null, WALL: null, WARDROBE: null }, frames: [] },
]
export function seedFriendPosts(mission: Pick<Mission, 'id' | 'title'>) {
  if (retentionState.posts.some((p) => p.missionId === mission.id && p.studentId.startsWith('friend-'))) return
  friends.forEach((f, i) =>
    retentionState.posts.push({
      postId: `post-${mission.id}-friend-${i}`,
      studentId: `friend-${i}`,
      nickname: f.nickname,
      companion: f.companion,
      equipped: f.equipped,
      missionId: mission.id,
      missionTitle: mission.title,
      answer: f.answer(mission.title),
      status: 'VISIBLE',
      createdAt: `2026-11-0${4 + i}T03:00:00Z`,
    }),
  )
}
export const communityOf = (studentId: string) => (retentionState.community[studentId] ??= { enabled: false, updatedAt: null })
export const consentOf = (studentId: string) => retentionState.consent[studentId] ?? false
export function setConsent(studentId: string, agreed: boolean) {
  retentionState.consent[studentId] = agreed
  if (!agreed) setCommunityEnabled(studentId, false)
}
/** 끄면 공유물 HIDDEN_SETTING, 다시 켜면 HIDDEN_SETTING만 복원(신고 숨김은 유지, P20). */
export function setCommunityEnabled(studentId: string, enabled: boolean) {
  retentionState.community[studentId] = { enabled, updatedAt: now() }
  for (const p of retentionState.posts.filter((p) => p.studentId === studentId)) {
    if (!enabled && p.status === 'VISIBLE') p.status = 'HIDDEN_SETTING'
    if (enabled && p.status === 'HIDDEN_SETTING') p.status = 'VISIBLE'
  }
}
/** 마무리(학습 완료) 후 core가 하는 일: 미션당 최초 적립, 공개가 켜져 있으면 미션당 1개 공유. */
export function onMissionCompleted(student: Child, mission: Pick<Mission, 'id' | 'title'>, answer: string, companion: CompanionId) {
  recordCompletion(student.id, mission.id)
  earn(student.id, 'MISSION_COMPLETED', mission.id)
  if (!communityOf(student.id).enabled || !answer.trim()) return
  if (retentionState.posts.some((p) => p.studentId === student.id && p.missionId === mission.id)) return
  retentionState.posts.push({
    postId: `post-${mission.id}-${student.id}`,
    studentId: student.id,
    nickname: student.nickname,
    companion,
    missionId: mission.id,
    missionTitle: mission.title,
    answer,
    status: 'VISIBLE',
    createdAt: now(),
  })
  earn(student.id, 'COMMUNITY_POSTED', `${student.id}:${mission.id}`)
}
/**
 * 공유 답변 응답 모양(core `CommunityAnswer`, api-spec 2.9, #825). 목업 공유물은 글 답변만 남기므로 서술(NARRATIVE)로 내보낸다.
 * 화면은 `text`만 보여 준다(`answerText`).
 */
export function sharedAnswer(text: string) {
  return { inputType: 'NARRATIVE' as const, text, content: { text } }
}
export function reactionCounts(postId: string) {
  const byStudent = retentionState.reactions[postId] ?? {}
  return Object.fromEntries(
    REACTIONS.map((r) => [r, Object.values(byStudent).filter((list) => list.includes(r)).length]),
  ) as Record<Reaction, number>
}
/** 같은 seed면 같은 순서가 되게 섞는다(정렬·순위 없음, P20). */
export function seededShuffle<T>(items: T[], seed: string) {
  let h = 2166136261
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619)
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0
    const j = h % (i + 1)
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

// ---------- 기념 액자·추억 앨범·추억의 벽 (P27, API 명세 2.12 기준안) ----------
/** 빈 앨범을 보려면 개발 도구에서 sessionStorage에 이 키로 '1'을 넣는다. */
export const MOCK_ALBUM_EMPTY_KEY = 'sagomungchi:msw-album-empty'
/**
 * 지난 회차 시작 이야기 그림: 실제 서버는 액자에 그 주 테마의 시작 이야기 생성 그림을 준다(learning AlbumService introImageUrl).
 * 목업도 같은 그림 생성 설정(ai-service IMAGE_STYLE·뭉치 참조 그림·gpt-image)으로 만든 그림을 쓴다(2026-11-16 사용자 의견 "우리 그림 생성되는 건데 저기 있어야 하는 거 아니야")
 */
const PAST_THEMES = [
  { title: '잃어버린 지도 조각', outro: '다섯 조각을 모두 맞추자 지도가 호수 한가운데 섬을 가리켰어요.', answer: '등대 아래 바위', image: '/demo/album/past-map.jpg' },
  { title: '별빛 우체국', outro: '마지막 편지는 우체국장 할아버지가 어릴 때 쓴 편지였어요.', answer: '우체국장 할아버지', image: '/demo/album/past-post.jpg' },
  { title: '숲속 발명 대회', outro: '다람쥐의 도토리 굴리개가 숲 친구들의 표를 가장 많이 받았어요.', answer: '도토리 굴리개', image: '/demo/album/past-forest.jpg' },
]
/** 회차 시작 그림 주소(저장해 둔 목업 상태에도 쓰이게 제목으로 찾음), 없으면 null */
export const frameImageOf = (f: { title: string }) => PAST_THEMES.find((t) => t.title === f.title)?.image ?? null
const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
/** 처음 보는 학생은 지난 3주 회차를 가상으로 둔다: 1주 전은 새 액자, 2주 전은 엔딩을 못 봄, 3주 전은 벽에 걸림 */
export function framesOf(studentId: string, missions: Mission[]): MockFrame[] {
  const empty = typeof sessionStorage !== 'undefined' && sessionStorage.getItem(MOCK_ALBUM_EMPTY_KEY) === '1'
  if (empty) return []
  if (!retentionState.frames[studentId] && missions.length) {
    const thisWeek = weekStart()
    retentionState.frames[studentId] = PAST_THEMES.map((t, i) => {
      const k = i + 1
      const start = addDays(thisWeek, -7 * k)
      return {
        themeId: `mock-theme-${k}`,
        weekStart: start,
        title: t.title,
        awardedAt: `${addDays(start, 4)}T10:30:00Z`,
        seenAt: k === 1 ? null : `${addDays(start, 5)}T01:00:00Z`,
        missions: THEME_DAYS.map((day, d) => {
          const m = missions[(i * 5 + d) % missions.length]
          return { day, missionId: m.id, title: m.title, thinkingType: m.thinkingType }
        }),
        endingSeen: k !== 2,
        outro: t.outro,
        answer: t.answer,
      }
    })
    retentionState.frameSlots[studentId] ??= [{ slotNo: 1, themeId: 'mock-theme-3', weekStart: addDays(thisWeek, -21) }]
    persistRetention()
  }
  return retentionState.frames[studentId] ?? []
}
export const frameSlotsOf = (studentId: string) => (retentionState.frameSlots[studentId] ??= [])
