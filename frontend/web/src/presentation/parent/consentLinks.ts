/** 정보 관리 화면의 커뮤니티 선택 동의 영역 앵커(#433). 대시보드 카드에서 이 위치로 바로 보낸다. */
export const COMMUNITY_CONSENT_ANCHOR = 'community-consent'

/** 현재 자녀·기간 조건을 그대로 둔 채 정보 관리의 커뮤니티 동의 영역으로 간다. */
export const communityConsentLink = (search: string) => ({
  pathname: '/parent/settings',
  search,
  hash: `#${COMMUNITY_CONSENT_ANCHOR}`,
})
