# 이슈 #43 모델 레지스트리·AI 사용량

대상: SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM. 원본 체크아웃을 전환하지 않고 별도 worktree의 `feature/core-model-registry`에서 작업한다. 시작 시 fetch한 origin/develop은 `ecd6ecf7880e90341855d2fad6d9e773f3711c67`이며 #36 PR #61 병합을 포함한다. origin은 원본 저장소, upstream은 미등록이다. #37·#38 worktree는 별도 유지한다.


## 현재 PR·CI 상태 (2026-10-27 확인)

구현 커밋 `2022604e34820634fe6bb1463958f65d6a0862bc`는 `feature/core-model-registry`에 push되어 [PR #73](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/73)이 develop 대상으로 열려 있다. 해당 SHA의 원격 CI 세 항목이 모두 성공했다.

| CI | 확인 결과 |
|---|---|
| [ci-core-service](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/40467242558) | success |
| [ci-ai-service](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/40467242580) | success |
| [ci-db-schema](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/40467242551) | success |

이 결과는 명시한 구현 SHA 기준이며 이후 리뷰 수정 커밋의 원격 CI는 별도로 확인한다. 최신 head의 체크 상태는 [PR #73 checks](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/73/checks)에서 확인할 수 있다. 아래 최초 구현·PR 준비 검증은 당시 기록으로 보존한다. 운영 배포·실제 ai/scoring 레플리카 교체를 검증했다는 뜻이 아니다.

## 정책 결정과 계약

NFR-AIQ-05에는 품질 합격 수치·승인 상태·근거 JSON이 확정되어 있지 않아 사용자에게 질문했다. 사용자는 2026-10-27에 **평가 근거 필수·SERVICE_OPS의 명시적 사람 승인·평가된 범위 내 활성화·기존 승인 범위 내 rollback·자동 합격선 없음**을 승인했다. 새 승인 상태를 만들지 않고 기존 REGISTERED·ACTIVE·INACTIVE를 사용한다. 평가 자료·비교·학습/평가 분리·인용·계산·사람 검토 기록을 보존한다. 근거 기록의 사실성·통계적 합격 여부는 운영자의 판단이며 서버가 실제 평가를 실행했다고 주장하지 않는다. 수치 기준(NFR-AIQ-06)은 별도 평가 정책으로 확정해야 한다.

설계(API 5.2·4.6, ERD 3.5, 아키텍처 1.6, 기능 명세) → OpenAPI·이벤트 data 스키마 → core 구현 순서로 반영했다. API의 scopes는 평가 기록과 일치하는 논리 범위 키이며 exact set 포함 관계만 허용한다. 최초 activate만 승인하고 inactive 버전은 rollback을 사용한다. 복귀는 원 승인 범위의 부분 집합만 가능하다. 승인자는 요청 본문이 아닌 인증 계정이다. 재분석 여부는 기록하며 재분석 작업은 실행하지 않는다.

## 호출 흐름·트랜잭션

- PublicAuthFilter → #36 AuthService 최신 세션·SERVICE_OPS 검사 → admin Controller → ModelVersionService → admin Repository/Mapper.
- 동일 kind·name의 PostgreSQL transaction advisory lock → 대상 재조회(캐시 비움) → 기존 ACTIVE를 INACTIVE → 대상 ACTIVE·범위·revision → 감사 행 추가 → 기존 OutboxWriter.append. 외부 HTTP/AMQP를 이 트랜잭션에서 호출하지 않는다.
- 기존 부분 unique index가 ACTIVE 단일성을 최종 강제한다. 그룹별 최대 저장 revision + 1을 같은 잠금에서 계산하므로 최초 활성화·동시 교체·복귀를 순서화한다. 실패한 트랜잭션은 상태·승인·감사·Outbox를 모두 롤백한다. 평가 근거와 최초 승인은 보존한다.
- 기존 OutboxRelay가 events.topic에 model.version.activated를 publisher confirm 후 기록한다. core의 큐·definitions.json·consumer·relay 구현은 수정하지 않는다.
- InternalAuthFilter → 내부 Controller → 동일 서비스의 active 조회. 공개 base 없이 `/internal/model-versions/active`이며 평가·관리자 정보는 반환하지 않는다.
- admin AiUsageController → 기존 LlmUsageService → 기존 usage Mapper의 집계 쿼리. KST 날짜 양 끝 포함, 호출 종류별 성공·실패 전체 평균 지연·토큰 합계·저장 비용 합계를 조회한다. 미산정 비용이 섞이면 costUsd null과 unpricedCalls를 반환한다. 기존 record·단가 계산·event_id 멱등성은 보존한다.

RUBRIC은 learning의 원본 ID만 참조한다. core는 원본 존재·내용 검증이나 편집 API를 새로 만들지 않는다. V1~V8·신규 migration·production 의존성·compose·실행 DB·다른 채팅 서비스는 변경하지 않는다.

## 실제 ai·scoring 연동 경계

ai의 `app/versions.py`는 judgment/followup 프롬프트 상수를 읽으며 이벤트 교체는 범위 밖이라고 명시한다. ai bootstrap에는 버전 소비·core 초기 조회·버전 readiness가 없다. scoring bootstrap도 AMQP 연결·health만 조립하고 버전 소비·초기 조회·실제 교체를 구현하지 않았다.

계약은 각 Pod의 exclusive·auto-delete 큐 바인딩 → core snapshot 조회 → 조회 중 이벤트 보존·조정 → 그룹별 더 높은 revision만 적용·승인 scopes 제한을 요구한다. 실제 브로커의 두 독립 큐 수신 검증은 발행·fan-out 계약 검증이며 ai/scoring의 실제 모든 레플리카 교체 완료를 의미하지 않는다. 미구현 소비자를 대역 결과로 완료 처리하지 않는다.

## 변경 파일의 공유 경계

주 변경은 admin/·usage 조회·해당 Mapper·테스트·이벤트 계약이다. 공통 변경은 core OpenAPI의 #43 경로/스키마 추가와 기존 auth OpenAPI 검사 범위를 인증 경로로 한정한 부분, 설계 문서의 해당 구간뿐이다. _common production 코드·공통 설정·기존 migration·RabbitMQ topology는 보존한다. #37 동의/자녀, #38 learning proxy/멱등성, #47 운영 작업/재처리, #48 결제/구독, 한도·예산 경보는 구현하지 않는다.

## 최종 검증 (2026-10-27)

코드·설정·테스트 작성 완료 후 한 단계로 검증했다. 실패 수정 뒤에는 실패 항목과 수정 영향 범위만 재실행했다.

| 실행 | 실제 결과 |
|---|---|
| JDK 21.0.12.1 `gradlew.bat test bootJar --no-daemon --max-workers=2` | 전체 62개 중 61개 통과, 신규 브로드캐스트 테스트 1개 실패. production 컴파일·bootJar 생성 성공 |
| NULL 평가 경계 추가 후 `test --tests 'com.sagomungchi.core.admin.*' bootJar` | 영향 범위 15개 중 13개 통과, 테스트 비교식 2개 실패. bootJar 재생성 성공 |
| `test --tests 'com.sagomungchi.core.admin.ModelVersionMessagingTest.activation*' --tests 'com.sagomungchi.core.admin.ModelVersionHttpTest.SERVICE_OPS*' bootJar` | 수정된 두 항목 2/2 통과, 실패·건너뜀 0 |
| 위 실행의 testcase 식별자별 최신 결과 대조 | 고유 core 테스트 63개 모두 통과, 미해결 실패·건너뜀 0. 최종 상태를 한 번의 전체 63개 실행으로 표현하지 않음 |
| `python -O -m unittest discover -s scripts/tests -v` | 29/29 통과 |
| OpenAPI 3.1 표준 검사·3개 이벤트 JSON Schema 자체 검사 | 통과 |
| 실제 RabbitMQ 수신 활성화·rollback 봉투/data 및 실제 startup snapshot의 스키마 검사 | 모두 통과. 이벤트 정상 예시와 비정상 6개 거부 사례도 검사 |
| package/디렉터리·Domain 의존 경계·신규 파일 공백·`git diff --check` | 통과 |

Repository는 PostgresRepositoryTest, 실제 발행·수신·commit/rollback·동시성은 IntegrationTestSupport의 PostgreSQL 17.11·RabbitMQ 4.3.7 일회용 컨테이너를 사용했다. 공통 기반이 격리 DB에 V1~V8을 적용했다. 승인 거부·범위 확장 거부·동시 최초 활성화·동일 대상 중복 승인·ACTIVE 부분 UK·rollback 원 승인 보존·감사 수행자/재분석 여부·상태/승인/감사/Outbox 원자성을 확인했다. 사용량 기간 경계·7개 종류·실패·평균 지연·토큰·null 비용·event_id 멱등 수집과 기존 실제 usage consumer 회귀가 포함된다.

MockMvc는 실제 #36 필터·JWT·서버 세션·권한 및 Controller/Service/DB를 연결해 SERVICE_OPS 성공과 부모·유효 학생·무권한/다른 권한 ADMIN의 FORBIDDEN(403), 내부 토큰 없음/오류의 401을 확인했다. 실제 Google 로그인·브라우저·운영 배포 검증은 이번 범위에서 실행하지 않았다.

첫 브로드캐스트 테스트는 짧은 basicConsume 취소로 auto-delete 큐가 삭제되어 실패했다. 테스트만 비차단 basicGet polling으로 수정해 실제 두 독립 큐 수신을 확인했다. JSON 비교의 LongNode/IntNode 차이는 wire JSON으로 정규화했고 테스트 JSON 경로 오타도 수정했다. 신규 브로커 테스트는 공유 usage listener를 끄고 전용 큐만 수신하므로 기존 수집 회귀와 경쟁하지 않는다.

중간 재검증 1회는 RabbitMQ 컨테이너의 기본 기동 대기 시간 초과로 본문 실행 전 실패했으며 이후 동일한 격리 공통 기반에서 실제 기동·발행·수신을 통과했다. Windows JDK의 Unix 도메인 소켓 연결 오류는 독립 Selector 진단에서도 재현했다. JDK 소스의 TCP fallback을 사용하도록 테스트 프로세스에만 `-Djdk.net.unixdomain.tmpdir=<존재하지 않는 공백 없는 임시 경로>`를 주입해 해결했다. 저장소 실행 설정·보안 설정·JDK 설치는 바꾸지 않았다. 준비용 Linux 검증 컨테이너는 이 채팅이 생성한 것만 종료했다.

검사 도구(openapi-spec-validator 0.9.0, jsonschema 4.26.0)는 ignored build 폴더에만 설치했으며 production 의존성·lock 파일을 변경하지 않았다. 실제 수신 JSON·전체/영향/최종 재검증 XML·고유 결과 대조 자료도 ignored build 폴더에 있다. core 실행 JAR 생성은 확인했으나 배포·실제 모든 ai/scoring 레플리카 교체를 뜻하지 않는다. 최초 로컬 검증 시점에는 원격 CI를 실행하지 않았으며, PR 생성 후 확인한 성공 결과는 이 문서 상단의 SHA별 CI 표를 따른다. learning/report 전체 마이그레이션 CLI 검사는 해당 DDL 변경이 없어 실행하지 않았다.

### 기존 NULL 평가 행

기존 ERD의 nullable eval_result 행은 목록에서 null 그대로 읽으며 승인 근거 부족으로 활성화/복귀를 거부한다. 평가·승인·scope가 불완전한 기존 ACTIVE 행은 내부 snapshot에서 MODEL_VERSION_STATE_INVALID(503)로 명시적으로 실패한다. 평가 자료·승인·기본 버전을 임의 생성하지 않는다. 신규 등록의 평가 근거 필수 조건은 유지한다.

### 구현 완료 시 Git 상태 (커밋 전)

최초 구현 기준은 `origin/develop`의 `ecd6ecf7880e90341855d2fad6d9e773f3711c67`이었다. 이후 최신 develop을 반영하고 구현 커밋을 push했으며 사용자가 PR #73을 생성했다. 원본 체크아웃과 #37·#38 worktree를 전환하거나 그 파일을 수정하지 않았고, squash·이력 재작성은 하지 않았다.


## PR 준비 검토 (2026-10-27)

이슈 #43 파일 25개·원본 패치·SHA-256 목록을 ignored build 폴더에 백업했다. 최초 재확인 뒤 PR #70이 병합되어 origin/develop을 다시 fetch했고, `1b600850b0aee73983d646819933585fd2b44934`로 전용 feature 브랜치만 fast-forward했다. #70의 인증 문서 정합성 변경을 보존하면서 네 설계 문서에 #43 변경을 자동 병합했으며 충돌은 없었다. 나머지 21개 파일은 줄바꿈 정규화를 제외하고 백업과 일치함을 확인했다. 다른 worktree를 전환·수정하지 않았고 공용 브랜치 이력도 재작성하지 않았다.

검토 중 scope 배열의 null 요소가 Kotlin의 non-null 제네릭 선언만으로 차단되지 않아 500 오류를 낼 수 있음을 확인했다. 공통 Jackson 설정이나 Domain의 프레임워크 의존성을 추가하지 않고 범위 검증에서 null을 명시적으로 거부한다. 등록·활성화·rollback 세 경로의 422와 상태·감사·Outbox 보존을 HTTP 회귀로 검증한다. 수치 합격선이나 승인 상태는 추가하지 않는다.

PR 검토에서는 새 OpenAPI 경로 검사가 #43의 두 Controller와 여섯 경로만 대조하도록 제한했다. 병렬 이슈가 별도 경로를 추가할 때 전체 API 개수를 고정한 검사 때문에 실패하지 않도록 하며, #43 소유 경로의 누락·불일치는 계속 검출한다.


### PR 준비 최종 검증

- 최신 develop(`1b600850b0aee73983d646819933585fd2b44934`) 반영과 null scope 경계 수정 후 레지스트리 영향 범위 16/16을 통과했다.
- 사용자가 이슈 완료 조건의 전체 test 실행을 확인하도록 요청해 최종 코드에서 `gradlew.bat test bootJar --no-daemon --max-workers=2`를 다시 실행했다. 이번에는 한 번의 전체 실행으로 64/64 통과(실패·오류·건너뜀 0), bootJar 생성 상태를 확인했다. 앞선 63개 결과 합산과 구분한다.
- 최종 `scripts/tests` 29/29, OpenAPI 3.1 표준 검사, 세 이벤트 JSON Schema, 실제 RabbitMQ 활성화/rollback 수신 봉투와 data·core snapshot 스키마 검사를 통과했다. 기존 수집·인증 회귀도 전체 core 실행에 포함된다.
- 이번 작업 25개 파일만 포함하며 환경 파일·임시 산출물·비밀 키 패턴·package 경계와 변경/신규 행 공백을 확인했다. PR #70의 문서 변경은 base에 포함되어 #43 PR 차이로 다시 섞이지 않는다.
- 이슈 #43의 해야 할 일 5개와 완료 조건 3개는 core 구현·검증으로 충족했다. 사용자가 GitHub 체크박스를 직접 표시하기로 했으며 이 작업에서 이슈 본문은 수정하지 않았다. 이 체크는 ai/scoring 실제 소비·전체 레플리카 교체나 배포 완료를 뜻하지 않는다.
- PR 대상은 원본 저장소 develop, head는 feature/core-model-registry다. 구현 변경만 커밋·push했고 사용자가 PR #73을 생성했다. 생성 후 실제 확인한 원격 CI 결과는 상단의 구현 SHA별 표를 따른다.


## PR #73 리뷰 반영

[리뷰 코멘트](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/73#issuecomment-6436404768)의 네 항목을 실제 코드와 대조했다.

1. class-diagram 3.5와 state-diagram 7.1을 실제 Controller 분리·서비스 메서드 인자·불변 ModelVersion·Repository/Mapper·트랜잭션 경계에 맞게 갱신했다. #22의 learning 미션 다이어그램과 다른 후속 설계는 보존했다.
2. 감사 경로의 편차를 명시했다. 공용 AuditLogService는 기존 다이어그램의 후속 설계이며 실제 구현이 없다. #43은 ModelVersionService → ModelVersionRepository.audit → ModelVersionMapper.audit → audit_log로 저장한다. 상태·감사·Outbox를 같은 트랜잭션으로 묶는 현재 경로를 유지한다. #47 등에서 공용 감사 기능을 도입할 때 통합 여부를 검토하며 미래 중복 가능성만으로 이번에 공용 서비스를 추가하지 않는다.
3. 사용자에게 조회 상한을 확인했고 양 끝 날짜 포함 366일로 확정했다. 367일 이상·역전 기간·0001~9999 밖의 연도는 DB/시각 변환 전에 400 VALIDATION_FAILED로 거부한다. 연도 0001·9999의 허용 경계와 윤년 366일·367일 거부를 실제 PostgreSQL·HTTP 경로에서 확인한다. 새 예산·과금·알림 체계는 추가하지 않는다.
4. 원격 CI 미확인·PR 준비 이전 문구를 과거 기록과 현재 상태로 구분해 갱신했다. PR 본문은 사용자가 직접 변경할 수 있도록 최신 검증·CI 문구를 대화로 제공한다. 코멘트 답글·PR 메타데이터 변경은 자동 전송하지 않는다.

원격 develop에 추가된 #22 PR #62의 `7188b696e6e28d537d015a0e7c4eab3346a65976`를 기존 커밋 재작성 없이 병합했다. 통합 커밋은 `74ead83`이며, 새 리뷰 수정은 별도 커밋으로 유지한다. 이 병합의 learning 파일은 develop 자체에 이미 포함되어 #43 PR 차이로 중복 추가되지 않는다.


### 리뷰 반영 검증 결과

- JDK 21 `gradlew.bat test bootJar --no-daemon --max-workers=2`에서 67개 중 46개가 통과했고, RabbitMQ Testcontainer의 기본 기동 대기 시간 초과로 IntegrationTestSupport 초기화가 실패하여 21개가 테스트 본문에 도달하지 못했다. 실제 코드 실패와 구분한다.
- 실패한 MessagingIntegrationTest·AuthFlowIntegrationTest·ModelVersionMessagingTest만 새 격리 환경에서 재실행해 21/21 통과했다. 고유 testcase의 최신 결과는 67개 모두 통과, 건너뜀 0이다. 이번 결과를 한 번의 전체 67개 실행 통과로 표현하지 않는다. bootJar도 생성했다.
- 추가된 366일 허용·367일 거부와 연도 0001/9999 허용·범위 밖 연도/전체 기간 거부는 첫 실행에서 실제 PostgreSQL 및 MockMvc HTTP 경로로 모두 통과했다. 조회 상한은 DB/시각 변환 전에 검사하며 기존 수집·event_id 멱등성·null 비용 계산을 유지한다.
- `python -O -m unittest discover -s scripts/tests -v` 29/29, OpenAPI 3.1·세 이벤트 JSON Schema 검사, 실제 RabbitMQ 활성화/rollback 수신 봉투/data 스키마 검사를 통과했다. 변경 다이어그램의 메서드/관계·상태 전이·문서 참조·코드 package 및 `git diff --check`를 확인했다. Mermaid 렌더링 자체는 실행하지 않았다.
- 공개 소비 경로는 frontend Usage → adminApi.usage(period, callType) → apiFetch → core AiUsageController → LlmUsageService → Mapper다. 기존 클라이언트는 오류를 QueryFeedback으로 표시한다는 점을 코드로 대조했다. 프론트는 목업 계약을 포함하고 있으며 실제 브라우저·운영 UI 실연동을 이번 검증으로 완료 처리하지 않는다.
- 공용 감사 서비스 신설·기존 감사 SQL 이동·마이그레이션·compose·다른 worktree 변경은 없다. 새 커밋의 원격 CI는 push 후 실제 head SHA로 별도 확인하며 PR 본문 교체 문구는 사용자에게 제공한다.
