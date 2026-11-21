const metricSources: Record<string, string> = {
  RECORD: '학습 기록', RULE: '정해진 판정 기준', ANSWER_KEY: '문항 정답', AI_OBSERVATION: 'AI 관찰',
}
export const metricSourceLabel = (source: string | null | undefined) =>
  source ? metricSources[source] ?? '출처 확인 필요' : '출처 확인 필요'

const accountActions: Record<string, string> = {
  UNLINK: '보호자 연결 해제', PROFILE: '프로필과 학습 기록 삭제', RECORDS: '학습 기록 삭제',
}
export const accountActionLabel = (scope: string) => accountActions[scope] ?? '처리 범위 확인 필요'

/** 기존 API의 개발 문구를 이용자 안내로 표시하되 삭제 범위와 이용 제한은 보존한다. */
export function accountEffectText(effect: string) {
  return effect.replaceAll('학생 세션 폐기', '학생 로그인 종료')
    .replaceAll('학습 재개는 후속 계약 필요', '삭제 후 학습을 다시 시작하는 기능은 아직 지원하지 않습니다')
}

/** 다른 메뉴에는 자녀·기간만 이어가고 신고 대상·상세 화면 상태는 넘기지 않는다. */
export function parentMenuSearch(search: string) {
  const source = new URLSearchParams(search), next = new URLSearchParams()
  for (const key of ['childId', 'from', 'to']) {
    const value = source.get(key)
    if (value) next.set(key, value)
  }
  return next.size ? '?' + next.toString() : ''
}
