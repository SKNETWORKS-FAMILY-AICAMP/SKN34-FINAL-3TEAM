/** 공개·동의 탭의 커뮤니티 선택 동의 영역 앵커(#433). */
export const COMMUNITY_CONSENT_ANCHOR = 'community-consent'

/** 현재 자녀·기간 조건을 유지하고 공개·동의 탭의 커뮤니티 동의 영역으로 간다. */
export function communityConsentLink(search: string) {
  const params = new URLSearchParams(search)
  params.set('section', 'sharing')
  return { pathname: '/parent/settings', search: '?' + params.toString(), hash: `#${COMMUNITY_CONSENT_ANCHOR}` }
}
