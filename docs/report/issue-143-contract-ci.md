# #143 웹 단위 테스트·계약 검사 CI

## 목적과 결정

DB 파일을 바꾸지 않은 API·이벤트 계약 변경도 CI에서 검사하도록 계약 검사를 `ci-contracts.yml`로 분리한다. 2026-10-30 사용자가 전달한 담당자 승인에 따른다. 기존 테스트·검증 스크립트를 재사용하며 제품 API나 DB 스키마는 변경하지 않는다.

기준 develop은 `0e16ef0`이다. 작업 중 병합된 #175·#176·#177·#178·#179를 반영했고, 기존 #143 CI 변경과 충돌은 없었다.

## 변경 범위

| 구성 | 동작 |
|---|---|
| `_web.yml` | 기존 npm ci → lint → **npm test** → build |
| `ci-contracts.yml` | PR·develop/main push·수동 실행. 계약·backend·web·scripts·설계 문서·Compose·RabbitMQ 정의 변경을 검사 |
| 계약 CI의 저장소 검사 | Python 3.12, PyYAML 6.0.3, jsonschema 4.26.0으로 `python -O -m unittest discover -s scripts/tests -v` |
| 계약 CI의 실제 응답 검사 | JDK21에서 core 통합 테스트 8개 클래스로 산출물을 생성하고 리포트·알림·문의·결제·관리자 리포트 재처리·분석 대화·관리자 운영의 validator 7개 실행 (#237 확장) |
| `ci-db-schema.yml` | DB 검증기 회귀와 실제 마이그레이션·ERD 대조 유지. API 계약용 jsonschema 별도 설치와 전체 계약 테스트 중복 실행 제거 |
| `ci-report-service.yml` | PR·push 모두 `contracts/openapi/report-service.yaml` 변경도 report CI 실행 |

계약 테스트가 컨트롤러 외 서비스·DTO·웹 어댑터도 읽으므로 `backend/**`, `frontend/web/**`를 포함한다. 좁은 컨트롤러 경로만 지정해 입력 변경을 놓치지 않는다. 보고서(`docs/report/**`)만 수정하면 CI를 실행하지 않는다. 경로 필터는 GitHub PR 전체 diff 기준이므로 다른 코드 변경이 함께 있으면 해당 CI가 실행될 수 있다.

기존 `_spring.yml`의 서비스 전체 테스트·빌드·이미지 빌드는 유지한다. 계약 CI의 선택 테스트는 실제 산출물 생성에 필요한 범위이며 core 전체 회귀를 대체하지 않는다. `clean test`로 이전 빌드의 JSON 재사용을 막고, 산출물 누락 또는 스키마 불일치는 실패로 처리한다. 실패 무시·continue-on-error·Docker 미존재 시 skip은 추가하지 않는다.

- report: `backend/core-service/build/contracts/report-{generate,started,completed,failed}.json`, `report-detail.json`
- notification: `backend/core-service/build/generated-contracts/notification-{list,settings}.json`
- 검사: `scripts/validate_report_contracts.py`, `scripts/validate_notification_contracts.py`

## 로컬 재현

Docker Desktop/Engine을 먼저 실행하고 `docker info`가 성공하는지 확인한다. core·learning·report 통합 테스트는 Docker 없이 실행하면 실패한다. core 계약 검사는 PostgreSQL·RabbitMQ·Redis를 Testcontainers로 생성하며 합성 데이터·테스트 자격 증명을 사용한다. 실제 AWS·Google 계정이나 모델 파일은 필요하지 않다.

웹 폴더에서 Node 22로 `npm ci`, `npm run lint`, `npm test`, `npm run build`를 순서대로 실행한다.

저장소 루트에서:

```sh
uv venv .venv-contracts --python 3.12
uv pip install --python .venv-contracts/bin/python 'PyYAML==6.0.3' 'jsonschema==4.26.0'
.venv-contracts/bin/python -O -m unittest discover -s scripts/tests -v
cd backend/core-service
./gradlew clean test --no-daemon --tests 'com.sagomungchi.core.report.ReportMessagingTest' --tests 'com.sagomungchi.core.report.ReportHttpTest' --tests 'com.sagomungchi.core.notification.NotificationIntegrationTest'
cd ../..
.venv-contracts/bin/python scripts/validate_report_contracts.py
.venv-contracts/bin/python scripts/validate_notification_contracts.py
```

Windows에서는 Python 경로를 `.venv-contracts/Scripts/python.exe`, Gradle을 `gradlew.bat`로 바꾸고 JAVA_HOME을 JDK21로 설정한다. Python 3.12와 JDK21은 각각 필요하다. Docker 컨테이너에서 Gradle을 실행할 경우 테스트 컨테이너에 접근할 Docker 소켓과 호스트 설정도 필요하다.

## 완료 판정

로컬 검사와 GitHub PR Checks 결과를 구분한다. 워크플로 문법·실행 경로 및 실제 테스트 명령을 로컬에서 검증한 뒤, PR에서 웹·계약·report·DB 워크플로가 실행·통과하는 것까지 확인해야 #143 완료 조건을 충족한다. 별도 workflow_dispatch는 기본 브랜치에 워크플로가 반영된 후 GitHub 수동 실행에 사용할 수 있다.

## 2026-10-30 로컬 검증 결과

아래는 #143 당시 기록이다. #237 확장 내용과 검증은 문서 마지막 절에 구분한다.

- 최신 develop `0e16ef0` 반영 후 웹 lint·단위 125개·운영 빌드 통과. 로컬 Node는 24.18.1이며 CI의 Node22 검증과 구분한다. 기존 번들 500kB 초과 경고는 남아 있다.
- 별도 Python 3.12.10 환경에 CI와 같은 PyYAML·jsonschema만 설치하고 최적화 모드의 저장소 테스트 83개 통과. DB CI가 유지하는 검증기 테스트 18개도 통과.
- JDK21 컨테이너에서 `clean test`로 core 통합 테스트 26개 통과(실패·오류·skip 0): 리포트 메시징 8개, HTTP 11개, 알림 7개. 실제 PostgreSQL·RabbitMQ·Redis 사용.
- 그 실행에서 새로 생성한 리포트 이벤트 4종·상세 HTTP 응답, 알림 목록·설정 HTTP 응답을 두 validator로 검사해 통과.
- 수정한 워크플로 4개는 actionlint 문법·shellcheck 통과. 저장소 전체 검사에서는 수정하지 않은 `_python.yml`의 기존 SC2046 경고가 있어 전체 무경고로 표현하지 않는다.
- 대표 입력 경로 12개 × PR/push 경로 필터, 보고서만 변경할 때 제외, report OpenAPI 경로 포함을 대조했다. GitHub 원격 이벤트 실행을 대체하는 검사는 아니다.
- `git diff --check` 통과. 위 결과에는 PR Checks가 포함되지 않으며 원격 결과는 PR에서 별도 확인한다.

## #237 계약 검사 범위 확장 (2026-11-02)

사용자가 전달한 담당자 승인에 따라 분석 대화·관리자 운영도 응답 자동 생성부터 CI에 포함한다. 기준은 #248이 병합된 develop `9595e8f`다. 제품 API·DB·권한 정책은 변경하지 않는다.

| 검사 | 실제 응답 생성 테스트 | 산출물 (core-service/build 기준) |
|---|---|---|
| 리포트 | ReportMessagingTest, ReportHttpTest | contracts/report-*.json |
| 알림 | NotificationIntegrationTest | generated-contracts/notification-*.json |
| 문의 | SupportIntegrationTest | generated-contracts/support-*.json |
| 결제 | PaymentIntegrationTest | generated-contracts/payment-*.json |
| 관리자 리포트 재처리 | AdminReportRetryIntegrationTest | admin-retry-contracts/report-retry-*.json |
| 분석 대화 | ConversationIntegrationTest | generated-contracts/analysis.json |
| 관리자 운영 | AdminOperationsIntegrationTest | generated-contracts/admin-operations.json |

분석 대화는 기존 다섯 결과 유형(LLM, VERIFICATION_FAILED, AI_UNAVAILABLE, NO_RECORD, UNSUPPORTED) 테스트에서 core가 반환한 최종 SSE result를 내보낸다. AI 대역 응답 자체를 파일로 복사하지 않는다. 관리자 운영은 인증된 MockMvc 요청으로 overview·jobs·job·queues·audit-logs 응답을 받는다. 큐 조회는 Testcontainers RabbitMQ 관리 API를 사용한다. 파일에는 인증 헤더나 토큰을 저장하지 않는다.

PostgreSQL·Redis·RabbitMQ 및 core 코드는 실제이며 AI·learning·외부 결제 등은 기존 테스트 대역이다. 운영 외부 연동 E2E 검사로 해석하지 않는다.

기존 `backend/**` 경로가 payment·support·admin·conversation을 모두 포함하므로 PR/push 경로 필터는 유지한다. `clean test` 뒤 일곱 검증기를 실행하고 누락 산출물을 무시하거나 이전 파일을 재사용하지 않는다. `test_contract_artifact_presence.py`는 산출물이 없는 임시 디렉터리에서 일곱 검증기 모두 실패하는지 검사한다.

로컬 재현은 위 #143 명령 대신 현재 `.github/workflows/ci-contracts.yml`의 테스트 8개 클래스와 검증 단계 7개를 그대로 실행한다. 분석·관리자 운영 검증기는 위 표의 JSON 경로를 인자로 받는다. 과거 audit 보고서의 수동 검사·미실행 기록은 당시 사실이므로 유지한다.

원격 `ci-contracts` 실행·통과는 로컬 테스트와 별도로 PR Checks에서 확인해야 한다. 로컬 작업만으로 #237의 원격 완료 조건을 체크하지 않는다.

### #237 로컬 검증 결과

- #248 병합 커밋 `9595e8f` 기준, 추가 merge 없이 최신 develop과 일치.
- JDK21 Docker에서 CI와 같은 8개 클래스 `clean test`: 136건 통과, 실패·오류·생략 0 (7분 2초). 로컬 자원 제한을 위해 `--max-workers=2` 사용.
- 생성한 파일을 사용하는 validator 7개 전부 통과. 분석 SSE 결과 5유형 및 관리자 응답 5종 포함.
- Python 3.12 최적화 모드 저장소 테스트 95건 통과. 파일 누락 시 일곱 검증기 모두 FileNotFoundError로 실패하는 회귀 포함.
- actionlint로 변경 워크플로 통과, PR/push × payment/support/admin/conversation 경로 8건 포함 확인, `git diff --check` 통과.
- 최초 Windows JDK 실행은 Gradle loopback 연결 오류로 시작하지 못해 Docker JDK21로 검증했다. Python 임시 폴더 권한 오류도 권한이 허용된 환경에서 재실행하여 통과했다. Kotlin 기존 annotation 경고는 남아 있다.
- GitHub 원격 CI는 아직 실행하지 않았다. 이슈의 워크플로 실행·통과 완료 조건은 푸시 후 확인 필요.
