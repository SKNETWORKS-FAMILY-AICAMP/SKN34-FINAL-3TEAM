import type { Permission } from '../../domain/admin/operations.ts'
import type { Child } from '../../domain/classroom.ts'
import type { ConsentDocument, ConsentHistory } from '../../domain/parent.ts'
export const mockAccountChildren = new Map<string, Child[]>()
export const mockAccounts = new Set([
  'parent@example.test',
  'admin@example.test',
  'content@example.test',
  'ops@example.test',
  'payment@example.test',
  'refund@example.test',
])
export const mockIdentity = {
  userId: 'mock-user',
  name: '시연 보호자',
  email: 'parent@example.test',
  permissions: [] as Permission[],
}
export const permissionsFor = (email: string): Permission[] =>
  email === 'admin@example.test'
    ? ['CONTENT', 'SERVICE_OPS', 'PAYMENT_VIEW', 'PAYMENT_REFUND']
    : email === 'content@example.test'
      ? ['CONTENT']
      : email === 'ops@example.test'
        ? ['SERVICE_OPS']
        : email === 'payment@example.test'
          ? ['PAYMENT_VIEW']
          : email === 'refund@example.test'
            ? ['PAYMENT_REFUND']
            : []
/**
 * #415 ID·비밀번호 학부모(core parent_credential과 같은 규칙). 개발 목업 전용이며 비밀번호는 메모리에만 둔다.
 * 목업 저장소는 이메일을 키로 쓰므로 `<id>@id.example.test`를 내부 키로만 쓴다(/me에는 노출하지 않음).
 */
export const mockPasswordParents = new Map<string, { password: string; email: string; failed: number; lockedUntil: number }>()
export const mockPasswordLogin = { loginId: null as string | null }
export const passwordParentKey = (loginId: string) => `${loginId}@id.example.test`
export let workspaceScenario = 'normal'
export function setWorkspaceScenario(value: string) {
  workspaceScenario = value
}


// Development fixture state only; never imported by the production API path.
/**
 * 현재 동의 문서. 문서 ID·버전은 core V39(TERMS 1.1)·V54(PRIVACY 1.2)와 같고 제목·본문은 시연 문구.
 * GUARDIAN 1.2는 학부모에게 자녀 답변 원문 제공을 필수 목적으로 더한 판(#1064, core #1061 V60 예정)이라 ID는 목업 값이다.
 */
export const consentDocuments: ConsentDocument[] = [
  {
    documentId: '00000000-0000-4000-8000-000004150001',
    kind: 'TERMS',
    version: '1.1',
    title: '이용 안내',
    content: '가상 데이터로 학습 흐름을 확인하는 개발 시연입니다. 실제 개인정보를 입력하지 마세요.',
    required: true,
  },
  {
    documentId: '00000000-0000-4000-8000-000007320001',
    kind: 'PRIVACY',
    version: '1.2',
    title: '개인정보 처리 동의',
    content: '이 화면은 개발용 목업입니다. 운영 동의 문서는 법률·서비스 검토 후 확정해야 합니다.',
    required: true,
  },
  {
    documentId: '00000000-0000-4000-8000-000010640001',
    kind: 'GUARDIAN',
    version: '1.2',
    title: '법정대리인 동의',
    content:
      '만 14세 미만 자녀의 법정대리인임을 확인하고 자녀 정보 처리에 동의합니다. 학부모(법정대리인)에게 자녀의 답변·생각 메모·돌아보기 원문을 제공하는 것이 필수 목적에 포함됩니다. 개발 시연 문구입니다.',
    required: true,
  },
]
/** 개정 전 문서(V39 PRIVACY 1.1·V25 GUARDIAN 1.0). 상태 시연 "동의 문서 개정(재동의)"의 기존 동의 이력에만 쓴다 */
export const previousConsentDocuments: ConsentDocument[] = [
  { ...consentDocuments[1], documentId: '00000000-0000-4000-8000-000004150002', version: '1.1' },
  { ...consentDocuments[2], documentId: '00000000-0000-4000-8000-000002350003', version: '1.0' },
]
export const mockConsentHistory = new Map<string, ConsentHistory[]>()
// core 규칙: 현재 문서에 대한 최신 이력이 동의여야 한다. 이력은 최신순이라 종류별 첫 행이 현재 문서가 아니면 재동의 대상
const currentAgreed = (entry: ConsentHistory | undefined) =>
  !!entry?.agreed && entry.status === 'AGREED' && consentDocuments.some((d) => d.documentId === entry.document.documentId)
export function mockConsentRequired(email = mockIdentity.email) {
  const rows = mockConsentHistory.get(email)
  if (!rows) return false // legacy demo fixtures start with consent already completed
  return ['TERMS', 'PRIVACY'].some((kind) => !currentAgreed(rows.find((r) => !r.studentId && r.document.kind === kind)))
}
export function mockGuardianConsentRequired(childId: string, email = mockIdentity.email) {
  const entry = mockConsentHistory.get(email)?.find((r) => r.studentId === childId && r.document.kind === 'GUARDIAN') // 선택 동의(COMMUNITY)는 이용 제한과 무관
  return !!entry && !currentAgreed(entry)
}
