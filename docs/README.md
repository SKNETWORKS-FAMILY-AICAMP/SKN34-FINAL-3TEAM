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

- `design/`: 구현 기준 설계 문서 (기능 명세·유스케이스·아키텍처·API·ERD·클래스·시퀀스·상태)
- `report/`: 주제별 결정 근거·구현 기록·검증 방법

| 보고서 | 내용 |
|---|---|
| [auth-account](report/auth-account.md) | Google OAuth·토큰(#36), 동의·자녀(#37), 재인증·삭제·탈퇴(#45), 학생 기기·PIN(P01 개정·#58) |
| [core-gateway](report/core-gateway.md) | core 학습 프록시·멱등성(#38), 피드백 SSE(#39), 대시보드(#40), 알림(#44) |
| [learning](report/learning.md) | 미션·데모 시드·성취기준(#22), 시도·초안(#23), 답변(#24), 피드백(#25), 마무리(#26), 기록 조회(#27), 판정 규칙(#79), 판정 정정 수신(#80), 학생 삭제 소비(#128), 관리자 미션(#145), 신고 지원 조회(#146), 학생 피드백 화면 계약(#82), domain 프레임워크 의존 정리(#169) |
| [ai](report/ai.md) | 판정·되묻기(#6)·OpenAI 전환, 분석 대화 에이전트, 모델 레지스트리·AI 사용량(#43), M2 정렬(#4) |
| [report](report/report.md) | core 주간 리포트(#42), 생성·계산·서술·렌더링·조회·삭제(#50~#55), 이용권 연결(#129), 종료 유실 복구(#132), 연결 상태 |
| [db-schema](report/db-schema.md) | DB 기술 결정(#5), 확정 정책 반영과 기존 데이터 전환 절차(#19) |
| [db-dev-guide](report/db-dev-guide.md) | 마이그레이션 CI(#13), Repository·SQLAlchemy 사용법(#14) |
| [local-platform](report/local-platform.md) | kind·Calico·ingress·MinIO 설정과 자원 예산(#17) |
| [frontend](report/frontend.md) | 웹 공통 기반·학생·학부모·관리자 화면(#7~#9·#59), 테마·대시보드, QR 시연 |
| [audit](report/audit.md) | develop 종합 검증(c608f52·640e0a2)과 설계 문서 정합성 점검, 남은 결함·테스트 공백 |

- [이슈 #46 신고·문의·공지·도움말](report/issue-46-support.md): 요청 역할·학생 scope, 정정 재시도·감사, 알림 연결과 공급자 필요 계약

- [이슈 #85 scoring 모델 레지스트리·S3 로딩](report/issue-85-scoring-model-registry.md): 승인 모델 로딩·scope·readiness 및 실제 모델 검증

- [이슈 #86 scoring 모델 활성화 이벤트](report/issue-86-scoring-model-events.md): 버전 교체·롤백·두 레플리카 재연결 검증

- [scoring #87](report/issue-87-scoring-m2.md): M2 채점 계약·실제 모델 검증
- [scoring #88](report/issue-88-scoring-m1.md): 미학습 M1 비활성 계약·입력 검증 및 활성화 후속 범위
- [scoring #85~#88 통합 제출](report/scoring-85-88-integration.md): 통합 브랜치·PR 범위·검증 결과·후속 연동 구분
- [report #152 관리자 실패 재처리](report/issue-152-report-admin-retry.md): 새 jobId 재사용·중복/판 보존·실제 연동 및 #47 요청·결과 예시
- [report #130 기본 worker 완료 근거](report/issue-130-worker-closure.md): 기존 생성기·별명 조회 재사용 및 최신 검증
- [#135·#139·#140 클라이언트·테스트 보강](report/issues-135-139-140.md): 설정 유지 근거·조회 연결 재사용·report/scoring 테스트
- [이슈 #47 관리자 운영](report/issue-47-admin-operations.md): 운영 현황·작업 재처리·감사 이력·큐 조회·관리자 미션 프록시
- [이슈 #48 결제·구독](report/issue-48-payments.md): 토스페이먼츠 테스트 결제·정기 청구·환불과 실제 상품 권한 공급
- [이슈 #119 학생 별명 조회](report/issue-119-student-profile.md): 리포트 생성용 core 내부 학생 별명 API
- [#56 리포트 worker 통합](report/report-worker-integration.md): 기본 worker 생성 파이프라인 연결과 완료 조건 검증
- [프론트 요구사항 대조](report/frontend-requirements-20261029.md): 요구사항 정의서 기능 ID별 화면 대조·구현
- [웹 develop 통합 PR](report/pr-web-develop-integration.md): 프론트 요구사항 보완과 develop 통합(#93·#97·#134)

## 개발 규칙

### 작업 규칙
- 모든 코드는 [설계 구조](design/architecture.md)의 서비스 경계·통신 방식·레이어 규칙·디렉토리 구조를 준수
- 설계와 다른 구조가 필요하면 설계 문서를 먼저 갱신한 뒤 구현
- 설계 변경 시 변경 내용과 근거를 `docs/report/`의 해당 주제 보고서에 절로 추가 (새 주제일 때만 새 파일)

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

#### core 임시 통합 경로

- core 병렬 작업의 통합 검증에 한해 `feature/* → feature/core-integration → develop` 경로를 사용한다.
- `feature/core-integration`은 최신 develop에서 만들며, 개별 core PR의 base로 사용한다. 이후 develop의 변경을 merge하고 통합 검증한 뒤 develop 대상 최종 PR로 반영한다.
- 이 경로는 core 병렬 작업이 develop에 모두 반영되면 종료하는 임시 예외다. main 반영은 기존 `develop → main` 흐름을 유지하고, 기존 기능 커밋을 임의로 squash·rebase하지 않는다.
- 기본 브랜치가 아닌 통합 브랜치 대상 PR의 `Closes`는 이슈를 자동 종료하지 않는다. 실제 해결 범위를 확인한 최종 develop PR에도 해당 `Closes #이슈번호`를 포함한다.

- [이슈 #41 분석 대화·SSE·한도](report/issue-41-analysis-conversations.md): core 대화·SSE·권한·사용 한도와 공급자 연동 검증
- [이슈 #131 report Outbox 복구](report/issue-131-outbox-recovery.md): 학생별 순서·지연 재시도·격리·수동 재처리와 DB 적용 절차
