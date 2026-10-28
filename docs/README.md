# 사고뭉치
아이의 생각을 기록하고, 그 기록을 학부모가 대화로 분석하는 사고력 학습 플랫폼
(과정 공통 주제 "대화형 데이터 기반 분석 에이전트 및 자동 리포팅 플랫폼"을 초~중학생 사고력 학습에 적용)

## 프로젝트 개요
- 사용자: 학생(초3~6 중심) / 학부모
- 핵심 기능
  - 미션: 미션을 풀며 생각 작성 → 되묻기로 한 걸음 더 생각 → 정답·예시 답 확인 및 돌아보기
  - 대화형 분석 에이전트: 학부모 질문에 학습 기록을 도구로 조회·계산해 답변, 답변 속 숫자·인용은 실제 기록과 자동 대조
  - 자동 리포팅: 주간 리포트 자동 생성 (숫자 근거·분모·계산식, 다섯 가지 생각 유형, 되묻기 전후 변화, 아이 원문 인용, 이번 주 저녁 질문)
- 다섯 가지 생각 유형: 분석하기·따져 보기·새로 만들기·문제 해결하기·돌아보기 (기초 사고력: 비교·분류·순서·규칙·원인과 결과·추론)

## 서비스 흐름

### 학생 미션
1. 미션 장면·질문을 보고 답을 쓰거나 고름 (막히면 생각 열기 질문·메모장 활용)
2. 판정: 고르기·수학 최종 답은 규칙, 서술·논술은 채점 기준표 요소별로 LLM이 근거 구절을 찾고 코드가 그 구절이 답에 실제 있는지 확인
3. 결과에 따라 "한 걸음 더" / "더 말해 보기" / "다시 살펴보기" 중 하나로 연결, 근거가 없으면 판정 보류
4. 생각을 다 낸 뒤에만 정답·예시 답과 "들어가면 좋은 생각" 체크 공개, 돌아보기 기록

### 학부모
1. 가입·자녀 등록 시 법정대리인 동의 및 동의 기록 저장
2. 주간 리포트 확인
3. 리포트에 질문 → 에이전트가 학습 기록 조회·계산 후 답변 (숫자·인용 대조 후 제시)

## 구현 제약
- 범위: 초3~6 서술형·논술형 + 다섯 가지 생각 유형 중심 (중·고, 초1~2는 확장)
- 하지 않는 것: 답 대신 써 주기, 맞춤법 교정, 사고력 진단 검사, 성적 향상 보장
- 숫자 레벨은 검증 전까지 학생·학부모에게 비공개
- 답변은 덮어쓰지 않고 버전별 저장
- 학생 이름은 LLM API로 전송 금지
- 12/7 배포는 데모 계정만 운영
- 결제는 토스페이먼츠 테스트 환경(테스트 키)까지만 연동, 실결제 미도입
- API 키는 환경 변수·GitHub Secrets에만 보관
- LLM 호출마다 토큰 사용량 기록 (학생 ID·답변 내용 미기록)

## 문서 구성

- `design/`: ERD·API·아키텍처 등 구현 기준이 되는 설계 문서
- `report/`: 작업별 검토 결과와 구현·검증 보고서
  - [이슈 #14 Repository 공통 기반](report/repository-foundation.md): 타입 매핑, 트랜잭션 경계, 예시 Repository와 PostgreSQL 테스트 사용법
  - [이슈 #50 리포트 생성 기반](report/report-generation-foundation.md): 공유 v1 계약·worker·Outbox 검증과 후속 생성기 연결 범위
  - [이슈 #51 학습 기록·수치 계산](report/report-metrics.md): P08 계산·항목/근거 저장 검증, #27 입력 구현안과 남은 실제 연동
  - [이슈 #7 프론트 공통 기반](report/issue-7-fe-common.md): MSW 전환·인증 갱신·체크박스 검증 기준·남은 작업
  - [이슈 #7 학생 화면 후속 검증](report/issue-7-student-completion.md): 역할 URL·6종 입력·피드백·초안 회귀
  - [이슈 #8·#9 학부모·관리자 화면](report/issue-8-9-parent-admin.md): 가입·대시보드·대화·리포트·관리자 권한/작업/콘텐츠 및 목업 계약
  - [미체크 항목 후속 작업](report/unchecked-followup.md): 메모 대상 칸 복사·신규 가입 연속 흐름·확정 정책과 오래된 이슈 문구 구분
  - [이슈 #5 DB 변경 대상 검토표](report/erd-change-targets-step1.md): 구현 항목, 조장 확인 항목, 후속 기능과 분류 이유
  - [이슈 #5 DB 스키마 구현·검증](report/db-schema-validation.md): 기술 결정, 마이그레이션 결과와 검증 재현 방법
  - [이슈 #13 DB 마이그레이션 CI](report/db-schema-ci.md): 확정 정책 반영 후 검증 범위와 로컬·CI 실행 방법
  - [이슈 #17 로컬 플랫폼 자원 설계](report/local-platform-resource-plan.md): 기준 PC와 CPU·메모리·볼륨 설정
  - [이슈 #17 로컬 플랫폼 설계 변경 근거](report/local-platform-design-decisions.md): 버전·CNI·MinIO 배포 방식·초기화·자격 증명과 데이터 보존의 기술 근거
  - [이슈 #19 확정 정책 DB 스키마 수정](report/db-policy-schema.md): 변경 대상, 기존 데이터 전환 절차, 1~3단계 검증과 검토 순서
  - [이슈 #6 ai-service 판정·되묻기 API 설계 변경](report/ai-judgment-followup.md): API 계약 변경, 설계와 다르게 구현한 부분과 근거, learning 연동 시 반영할 점
  - [이슈 #4 M2 API 명세 정렬](report/m2-api-alignment.md): 학년 입력·점수 범위·모델 버전 규칙 명세 반영과 근거
  - [이슈 #22 learning 미션 조회와 데모 미션 시드](report/learning-mission.md): 시드 문항·공개 범위·성취기준 근거, 미션 조회 구현 결정과 #14 Repository 기반 사용
  - [이슈 #23 learning 학습 시도·초안·생각 열기](report/learning-attempt.md): 이어하기·동시 시작, 초안 버전 충돌, 생각 열기 순서와 설계 문서 갱신 근거
  - [이슈 #24 learning 답변 제출·버전 저장](report/learning-answer.md): 제출 순서·행 잠금, 같은 키 재요청, 보완 답변 연결, 제출 뒤 초안 비우기와 설계 문서 갱신 근거
  - [이슈 #25 learning 피드백 오케스트레이션](report/learning-feedback.md): 처리 상태 전이·리스, 규칙·ai 판정과 풀이 결합, 되묻기·질문 은행, ai 호출 장애 처리와 설계 문서 갱신 근거
  - [이슈 #26 learning 마무리·돌아보기·자기 평가](report/learning-reflection.md): 마무리 조건·공개 내용·체크리스트, 돌아보기 난이도 코드와 학습 완료, 자기 평가, 마무리 경합과 설계 문서 갱신 근거
  - [이슈 #27 learning 학습 기록 조회](report/learning-records.md): 집계 대상(P08)·지표·상태, KST 기간, 기록 목록·상세(학생 시도 상세 재사용), 전후 변화 계산, 근거·운영 집계와 설계 문서 갱신 근거
  - [이슈 #79 learning 판정 규칙 확정](report/learning-judgment-rules.md): 수학 단위(비교 안 함·답 칸 뒤 고정), 풀이 단계 결합과 최종 답 요소, 분류 그룹 저장(V6)과 기획서 "분류 기준"과의 관계
  - [이슈 #36 Google OAuth·access/refresh](report/issue-36-google-auth.md): HS256·세션 폐기·역할 전환·프론트 계약과 후속 경계
  - [P01 개정 학생·학부모 로그인 분리](report/student-login-separation.md): 등록 기기·PIN 단독 진입 설계 근거와 대안 비교
  - [프론트엔드 UX 정합성(최초 화면 작업)](report/frontend-backend-ux-alignment.md): 백엔드 기준 화면 정렬 기록, 현재 기준은 이슈 #7 보고서
  - [프론트 화면 PR 설명](report/pr-fe-workspace.md): 이슈 #7·#8·#9 학생·학부모·관리자 화면 PR 변경 요약
  - [이슈 #37 추가 리뷰 대응](report/issue-37-review-followup.md): 공유 서킷·기록 service 경계·병렬 조회와 무커밋 검증
  - [이슈 #37 PR 준비·최신 develop 통합](report/issue-37-pr-preparation.md): 충돌 해결·PIN/동의 호환성과 통합 검증
  - [이슈 #37 기록 존재 확인 선행 API](report/issue-37-record-existence.md): #27 최소 공급자·실제 core/learning 데이터 연동
  - [이슈 #37 동의·자녀 등록](report/issue-37-consent-children.md): 버전별 동의·철회·동시 등록·온보딩
  - [이슈 #38 학생 미션 공개 API·멱등성](report/issue-38-core-learning-proxy.md): core→learning 프록시·답변 멱등·서킷과 학생 컨텍스트
  - [이슈 #39 core 피드백 SSE](report/issue-39-core-feedback-sse.md): heartbeat·연결 시간·오류 이벤트·컨텍스트 전달과 리뷰 대응
  - [이슈 #43 모델 레지스트리·AI 사용량](report/issue-43-model-registry.md): 버전 등록·활성화·복귀, 사용량 조회 계약과 검증
  - [이슈 #59 학생 PIN 로그인·기기 관리 화면](report/issue-59-student-device.md): MSW 목업 계약과 백엔드 확인 항목
  - [학부모 대시보드 시안 적용](report/parent-dashboard.md): 대시보드 화면 시안 반영 기록
  - [학생 화면 테마 적용](report/student-theme-world.md): 생각 지도 테마·캐릭터·꾸미기 화면 기록
  - [설계 문서 정합성 점검](report/docs-consistency-audit.md): 코드 대비·문서 간 불일치 수정 내역, 결정 항목 반영(계정 복구·삭제 재확인·내부 OpenAPI 등), 코드 결함 이슈 초안

## 개발 규칙

### 작업 규칙
- 모든 코드는 [설계 구조](design/architecture.md)의 서비스 경계·통신 방식·레이어 규칙·디렉토리 구조를 준수
- 설계와 다른 구조가 필요하면 설계 문서를 먼저 갱신한 뒤 구현
- 설계 변경 시 변경된 내용과 근거를 작성한 문서 docs/report/에 추가

### 커밋 규칙

#### 형식
```
type: subject
```

#### type
| type | 용도 |
|---|---|
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 (README 등) |
| `style` | 코드 포맷팅, 세미콜론 누락 (로직 변경 없음) |
| `refactor` | 코드 리팩토링 (기능 변화 없음) |
| `test` | 테스트 코드 추가 및 수정 |
| `chore` | 빌드 스크립트 수정, 패키지 매니저 설정 등 |

#### 예시
```
feat: 데이터셋 업로드 API 추가
fix: 리포트 생성 실패 시 상태 미갱신 수정
docs: 아키텍처 설계 문서 추가
```

### 브랜치 규칙

#### 전략: Git Flow (간소화)
`hotfix/*`, `release/*` 브랜치는 사용하지 않음.

| 브랜치 | 역할 |
|---|---|
| `main` | 배포 기준 브랜치 |
| `develop` | 개발 통합 브랜치 |
| `feature/*` | 기능 개발 브랜치, `develop`에서 분기 |

#### 병합 흐름
```
feature/* → develop → main
```
- `feature/*`는 `develop`으로만 병합
- `main`은 `develop`에서만 병합
- 순서를 건너뛴 병합(`feature/*` → `main`) 금지

#### core 임시 통합 경로 (2026-10-28)

- core 병렬 작업의 통합 검증에 한해 `feature/* → feature/core-integration → develop` 경로를 사용한다.
- `feature/core-integration`은 최신 develop에서 만들며, 개별 core PR의 base로 사용한다. 이후 develop의 변경을 merge하고 통합 검증한 뒤 develop 대상 최종 PR로 반영한다.
- 이 경로는 core 임시 통합용 예외다. main 반영은 기존 `develop → main` 흐름을 유지하고, 기존 기능 커밋을 임의로 squash·rebase하지 않는다.
- 기본 브랜치가 아닌 통합 브랜치 대상 PR의 `Closes`는 이슈를 자동 종료하지 않는다. 실제 해결 범위를 확인한 최종 develop PR에도 해당 `Closes #이슈번호`를 포함한다.

- [이슈 #45 계정 관리·Google 재인증·삭제·탈퇴](report/issue-45-account-management.md): #58 호출 계약, 삭제 Outbox·서비스별 완료, 탈퇴 차단·세션 폐기 및 통합 조건

- [이슈 #58 학생 기기·PIN 인증](report/issue-58-student-device-auth.md): 실제 재인증·기기·PIN 계약, 삭제 연동과 검증 범위
