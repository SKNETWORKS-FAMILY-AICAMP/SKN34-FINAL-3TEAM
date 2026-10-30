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
| 계약 CI의 실제 응답 검사 | JDK21에서 기존 core `ReportMessagingTest`, `ReportHttpTest`, `NotificationIntegrationTest` 실행 후 두 validator 실행 |
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

- 최신 develop `0e16ef0` 반영 후 웹 lint·단위 125개·운영 빌드 통과. 로컬 Node는 24.18.1이며 CI의 Node22 검증과 구분한다. 기존 번들 500kB 초과 경고는 남아 있다.
- 별도 Python 3.12.10 환경에 CI와 같은 PyYAML·jsonschema만 설치하고 최적화 모드의 저장소 테스트 83개 통과. DB CI가 유지하는 검증기 테스트 18개도 통과.
- JDK21 컨테이너에서 `clean test`로 core 통합 테스트 26개 통과(실패·오류·skip 0): 리포트 메시징 8개, HTTP 11개, 알림 7개. 실제 PostgreSQL·RabbitMQ·Redis 사용.
- 그 실행에서 새로 생성한 리포트 이벤트 4종·상세 HTTP 응답, 알림 목록·설정 HTTP 응답을 두 validator로 검사해 통과.
- 수정한 워크플로 4개는 actionlint 문법·shellcheck 통과. 저장소 전체 검사에서는 수정하지 않은 `_python.yml`의 기존 SC2046 경고가 있어 전체 무경고로 표현하지 않는다.
- 대표 입력 경로 12개 × PR/push 경로 필터, 보고서만 변경할 때 제외, report OpenAPI 경로 포함을 대조했다. GitHub 원격 이벤트 실행을 대체하는 검사는 아니다.
- `git diff --check` 통과. 위 결과에는 PR Checks가 포함되지 않으며 원격 결과는 PR에서 별도 확인한다.
