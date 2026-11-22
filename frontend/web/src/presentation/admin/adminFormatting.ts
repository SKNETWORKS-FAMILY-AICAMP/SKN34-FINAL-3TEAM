import type { OperationQueue } from '../../domain/admin/operations.ts'

const auditActions: Record<string, string> = {
  JOB_RETRY: '작업 재처리',
  JOB_RETRY_REQUESTED: '작업 재처리 요청',
  JOB_RETRY_COMPLETED: '작업 재처리 완료',
  JOB_RETRY_FAILED: '작업 재처리 실패',
  MISSION_CREATE: '미션 등록',
  MISSION_UPDATE: '미션 수정',
  MISSION_RUBRIC: '미션 판정 기준 저장',
  RUBRIC_UPDATE: '미션 판정 기준 저장',
  MISSION_REVIEW_REQUEST: '미션 검토 요청',
  MISSION_REVIEW: '미션 검토',
  MISSION_PUBLISH: '미션 게시',
  MISSION_UNPUBLISH: '미션 게시 중단',
  MISSION_DRAFT_REQUEST: '미션 초안 생성 요청',
  MISSION_DRAFT_ADOPT: '미션 초안 채택',
  MISSION_DRAFT_DISCARD: '미션 초안 버리기',
  WEEKLY_THEME_CREATE: '주간 테마 등록',
  WEEKLY_THEME_UPDATE: '주간 테마 수정',
  WEEKLY_THEME_REVIEW_REQUEST: '주간 테마 검토 요청',
  WEEKLY_THEME_PUBLISH: '주간 테마 게시',
  WEEKLY_THEME_UNPUBLISH: '주간 테마 게시 중단',
  THEME_DRAFT_PLAN: '주간 테마 후보 편성',
  THEME_SCENE_SELECT: '테마 장면 선택본 저장',
  THEME_SCENE_ANNOTATE: '테마 장면 별표·메모 수정',
  THEME_DRAFT_REQUEST: '주간 테마 초안 생성 요청',
  THEME_DRAFT_ADOPT: '주간 테마 초안 채택',
  THEME_DRAFT_DISCARD: '주간 테마 초안 버리기',
  THEME_DRAFT_REGENERATE: '주간 테마 초안 다시 생성',
  MODEL_REGISTER: '모델 버전 등록',
  MODEL_PREFLIGHT: '모델 사전 검사',
  MODEL_ACTIVATE: '모델 버전 활성화',
  MODEL_ROLLBACK: '이전 모델 버전으로 복귀',
  SUPPORT_ORIGINAL_VIEW: '신고에 연결된 원문 열람',
  EXPRESSION_REVIEW_VIEW: '표현 검토 목록 열람',
  EXPRESSION_REVIEW_LABEL: '표현 검토 라벨',
  ERROR_REPORT_VIEW: '오류 신고 상세 열람',
  SUPPORT_REVIEW: '오류 신고 검토',
  ERROR_REPORT_REVIEW: '오류 신고 검토',
  JUDGMENT_CORRECTION: '판정 정정',
  CORRECTION_REQUESTED: '판정 정정 요청',
  CORRECTION_COMPLETED: '판정 정정 완료',
  INQUIRY_ANSWERED: '문의 답변',
  NOTICE_CREATED: '공지 등록',
  NOTICE_UPDATED: '공지 수정',
  NOTICE_ENDED: '공지 종료',
  LOOK_ITEM_CREATED: '꾸미기 아이템 등록',
  LOOK_ITEM_UPDATED: '꾸미기 아이템 수정',
  LOOK_ITEM_STOPPED: '꾸미기 아이템 판매 중단',
  LOOK_ITEM_RESUMED: '꾸미기 아이템 판매 재개',
  PAYMENT_REFUND_APPROVED: '환불 승인',
  PAYMENT_REFUND_REJECTED: '환불 반려',
  ACCOUNT_UPDATED: '계정 정보 수정',
  WITHDRAWAL_REQUESTED: '계정 탈퇴 요청',
  ADMIN_PASSWORD_LOGIN: '관리자 비밀번호 로그인',
  PARENT_PASSWORD_LOGIN: '학부모 비밀번호 로그인',
  PARENT_PASSWORD_SIGNUP: '학부모 비밀번호 계정 가입',
  GUARDIAN_PASSWORD_CHANGED: '보호자 비밀번호 변경',
  GOOGLE_REAUTHENTICATED: 'Google 본인 확인',
  PASSWORD_REAUTHENTICATED: '비밀번호 본인 확인',
  STUDENT_DEVICE_REGISTERED: '학생 기기 등록',
  STUDENT_DEVICE_REVOKED: '학생 기기 등록 해제',
  STUDENT_PIN_CHANGED: '학생 기기 PIN 변경',
  CHILD_UPDATED: '자녀 정보 수정',
  CHILD_UNLINKED: '자녀 연결 해제',
  CHILD_DELETION_CONFIRMED: '자녀 데이터 삭제 확인',
  GUARDIAN_TRANSFER_REQUESTED: '보호자 변경 요청',
  GUARDIAN_TRANSFER_ACCEPTED: '보호자 변경 수락',
  GUARDIAN_TRANSFER_REJECTED: '보호자 변경 거절',
  GUARDIAN_TRANSFER_CANCELLED: '보호자 변경 취소',
}
const auditStages: Record<string, string> = {
  REQUESTED: '요청 접수', SUCCEEDED: '완료', REJECTED: '요청 거절', UNKNOWN: '결과 미확인',
}

export function auditActionLabel(action: string) {
  if (Object.hasOwn(auditActions, action)) return auditActions[action]
  const parts = /^(.*)_(REQUESTED|SUCCEEDED|REJECTED|UNKNOWN)$/.exec(action)
  if (parts && Object.hasOwn(auditActions, parts[1])) return auditActions[parts[1]] + ' · ' + auditStages[parts[2]]
  return '기타 작업'
}

const aiScopeNames: Record<string, string> = {
  'ai/judgment': 'AI 판정',
  'ai/followup': '되묻기 질문',
  'ai/analysis': '분석 대화',
  'ai/report-narrative': '리포트 서술',
  'ai/report-explanation': '리포트 설명',
  'ai/report-template': '리포트 양식',
  'ai/mission-draft': '미션 초안 생성',
}
export function modelScopeLabel(scope: string) {
  const judgment = /^judgment\/grade-([1-6])\/(narrative|essay)$/.exec(scope)
  if (judgment) return '초등 ' + judgment[1] + '학년 · ' + (judgment[2] === 'essay' ? '논술형' : '서술형') + ' 판정'
  return Object.hasOwn(aiScopeNames, scope) ? aiScopeNames[scope] : scope
}

const queueNames: Record<string, string> = {
  'report.report.generate': '주간 리포트 생성',
  'core.report.events': '리포트 처리 결과 반영',
  'core.llm.usage.recorded': 'AI 사용량 기록',
  'core.event.audit': '감사 이력 기록',
  'learning.student.deleted': '학습 기록 삭제 반영',
  'report.student.deleted': '리포트 기록 삭제 반영',
  'core.model.loading.reported': '모델 준비 상태 반영',
}

export function queueHeading({ name, kind }: Pick<OperationQueue, 'name' | 'kind'>) {
  const base = name.replace(/(?:\.retry\.\d+|\.dlq)$/, '')
  const label = queueNames[base] ?? '기타 작업'
  if (kind === 'DLQ') return label + ' · 실패 보관'
  if (kind === 'RETRY') {
    const attempt = name.match(/\.retry\.(\d+)$/)?.[1]
    return label + ' · ' + (attempt ? attempt + '차 ' : '') + '재시도'
  }
  return label
}

export const jobTypeLabel: Record<string, string> = { CONVERSATION: '분석 대화', REPORT: '주간 리포트', NOTIFICATION: '알림' }
export const reportStatusLabel: Record<string, string> = { RECEIVED: '접수', IN_REVIEW: '검토 중', RESOLVED: '처리 완료' }
export const modelKindLabel: Record<string, string> = { RUBRIC: '판정 기준', MODEL: '판정 모델', PROMPT: '프롬프트', GENERATION: '생성 설정' }
export const number = (v: number) => v.toLocaleString('ko-KR')
export { formatKoreanDateTime as date } from '../common/dateTime.ts'
