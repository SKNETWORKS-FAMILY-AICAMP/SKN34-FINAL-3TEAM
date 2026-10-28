# 리포트 에픽 #56 이슈별 진행과 완료 가능 범위

2026-10-28 GitHub 이슈 #50~#56·#27·#64와 develop `78bbdc1`의 구현을 대조했다. 이전 인계 문서의 미병합·미확보 기록보다 이 문서의 현재 상태를 우선한다. 이번 작업은 브랜치 통합과 완료 조건 점검이며, 아래 남은 기능을 새로 구현하거나 이슈를 종료한 작업은 아니다.

## 브랜치와 목적

- 사용자 지시에 따라 개인 에픽 브랜치 운영을 중단하고 기존 이슈별 브랜치 방식을 유지한다. #50은 `feature/report-generation`, #51은 `feature/report-metrics`, #52는 `feature/report-narrative`, #53은 `feature/report-rendering`, #54는 `feature/report-query`, #55는 `feature/report-deletion`에서 진행한다.
- 최초 점검 때 만든 `feature/inyoung9629-report`는 삭제 요청이 없어 보존만 한다. 이 브랜치에 반영한 develop `78bbdc1` 병합(`5ef5a8e`)과 점검 결과(`b244668`)는 기존 누적 `feature/report-deletion`에도 fast-forward로 보존했다. 개별 기능 커밋과 #55 추가 migration 커밋은 유지한다.
- PR은 이슈별로 범위를 확인해 `develop`에 제출한다. 후속 브랜치가 앞선 이슈를 포함하는 누적 구조이므로 선행 병합 후 다음 브랜치의 기준을 갱신하고 diff를 확인한다. 이번 방향 변경에서는 PR 생성·병합·이슈 종료를 수행하지 않는다.
- scoring 에픽의 `feature/inyoung9629-scoring` 및 #85의 실제 모델 연동 보류 상태는 유지한다. scoring 변경을 report 브랜치에 섞지 않았다.

## 이슈별 판단

‘단독 검증’은 실제 PostgreSQL·RabbitMQ·MinIO와 고정 learning/AI 응답 등을 사용한 report 측 검사다. core·learning·AI를 모두 실행한 실제 서비스 연동 완료와 구분한다.

| 이슈 | 현재 확보된 것 | 지금 할 수 있는 일 | 완료 판단에 남은 것 |
|---|---|---|---|
| #50 생성·상태·Outbox | 기존 report 기반 구현과 #42의 공유 report v1 스키마·core 생산/소비 코드 | **우선 마무리 가능.** 공유 규격을 읽고 쓰는 production codec 구현, worker 기본 진입점 연결, 계약·멱등·상태/Outbox 검사 | 현재 기본 worker는 codec이 없으면 생성 큐를 구독하지 않는다. 기존 FakeCodec 테스트와 root 계약 검사만으로 실제 연결 완료를 선언하지 않는다. #50은 생성 기반 범위이며 전체 파일 생성은 아래 닉네임·#27 연동에 의존한다. |
| #51 기록·수치 | P08 계산, 고정 응답 기반 item/evidence 저장, 0/1~4/5건 경계 검사 | report 단독 구현·검증 결과 검토 가능 | #27의 실제 attempts/thinking-types/changes/evidence DTO가 아직 없다. 입력 구현안을 공급자와 대조하고 실제 연동을 검증해야 한다. |
| #52 서술·대조 | 무료/NO_RECORD 미호출, 숫자·인용 검증, API 실패 FAILED, 대조 실패 TEMPLATE | **이슈가 허용한 AI 대역 응답 기준으로 완료 검토 가능.** #64 구현을 기다리며 동일 로직을 다시 만들 필요 없다. | 실제 AI 및 learning evidence 연동은 #64/#27 후 검증한다. #64는 OPEN·미배정이고, 서술 API는 #66이 아니다. #51 의존성과 실제 연동 완료 여부는 별도로 표시한다. |
| #53 파일 생성·저장 | HTML/PDF/MD, 한글 PDF, full/free·revision 분리, 실제 MinIO 업로드·서명 다운로드·삭제 검사 | **파일 생성·저장 단독 범위 완료 검토 가능.** 기존 Linux 이미지 검사 이력도 있다. | 실제 명령에서 렌더링까지 연결하려면 신뢰할 수 있는 자녀 닉네임 공급이 필요하다. 운영 AWS 설정은 로컬 MinIO 완료 조건과 구분한다. |
| #54 조회·다운로드 | report 내부 API·범위 검사·판 조회·현재 권한별 응답/파일 선택, #42 공개 프록시 | core→report 목록·상세·무료 다운로드 연동 검사 진행 가능 | core가 현재 상품 권한 헤더를 보내지 않으므로 유료 응답/다운로드 전체 연동은 미완료다. 실제 근거 조회는 #27에 의존한다. |
| #55 삭제 | report 삭제·재시도·생성 경합 방지 구현, #45 실제 이벤트/완료 API | 공유 삭제 스키마 대조·소비 검증 보강과 core 완료 보고 연동을 진행할 수 있다. | RECORDS 이후 재개 정책 차이를 맞추고 추가 guard migration을 검토해야 한다. 늦게 도착한 생성/상태 이벤트 및 양 서비스 완료 순서까지 검증한 뒤 완료 판단한다. |

## 이미 확보되어 다시 요청할 필요 없는 것

- #42와 #45는 [PR #98](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/98)로 develop에 병합됐다. `contracts/events/report.*.v1.schema.json`, `student.deleted.v1.schema.json`과 `report-messages.md`를 재사용한다.
- core의 학생 접근 검사와 내부 토큰·사용자·단일 학생 scope 전달은 구현되어 있다. 다만 scope 전달과 상품 권한 전달은 서로 다른 조건이다.
- 삭제 완료 경로와 `{service:"report"}` 요청, `SYSTEM` 역할·학생 scope 검사, 중복 완료 처리, learning/report 모두 완료한 뒤 완료 처리하는 core 코드를 확인했다.
- `OutboxWriter`는 최초 `EventEnvelope.time`을 payload에 저장한다. 이 값의 존재 여부를 다시 질문할 필요는 없으며 재전달·삭제 경합에서 실제 대조한다.
- 까닭 연결어 네 개와 AI 장애 FAILED/대조 실패 TEMPLATE는 이미 사용자 확정값이다. 로컬 MinIO 주소·버킷과 PDF 라이브러리·파일 키도 기존 구현에 있다.

## 실제로 남은 연결과 정합성

### 1. #50의 메시지 연결은 우리 작업

`app/worker.py`의 기본 `run()`은 `report_codec=None`으로 실행되어 생성 구독을 생략한다. `app/generation/ports.py`는 Protocol만 제공한다. #42 공유 스키마가 들어왔으므로 우리 codec과 worker 연결을 작성하면 된다. 메시지 봉투의 필수값·source/type/dataschema, subject와 data.studentId 일치, 날짜/trigger 등을 검증하고 lifecycle 이벤트를 같은 공유 규격으로 발행해야 한다.

### 2. #27 기록 API와 #64 서술 API

[#27](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/27)은 OPEN이며 담당은 `Overlay1010`이다. develop의 record 구현은 exists만 있고 report가 요구하는 상세 기록 API는 없다. 이번에 병합된 #26은 마무리·돌아보기 저장 기능으로 #27을 대신하지 않는다. 돌아보기 난이도 코드 `EASY/NORMAL/HARD`와 report 표시 문구도 실제 DTO가 제공되면 대조한다.

[#64](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/64)는 OPEN·미배정이다. #52 본문은 명세 기반 가짜 응답 검증을 명시적으로 허용하므로 실제 AI 서비스 미구현을 #52 자체 검사 전체의 차단 조건으로 해석하지 않는다.

### 3. 닉네임 공급과 현재 상품 권한 — core #42/상품 담당 연결

- `report.generate.v1`은 6개 data 필드만 허용하며 학생 이름을 메시지에 넣지 않는 계약이다. 닉네임을 임의로 메시지에 추가하면 안 된다. report의 `RenderingGenerator`는 신뢰할 수 있는 display_name을 요구하므로 별도 승인된 내부 공급 경로가 필요하다.
- core `ReportEntitlementService`는 현재 `503 REPORT_ENTITLEMENT_UNAVAILABLE`를 반환한다. 따라서 정기/재생성에서 job·Outbox 생성까지 가지 못한다. 직접 합성 명령 발행으로 report 기반을 검증하는 것은 가능하지만 실제 스케줄 성공으로 보고하면 안 된다.
- report는 `X-Report-Narrative-Enabled`로 현재 권한을 받아 상세·파일을 선택한다. core `ReportClient`와 공통 HTTP 팩터리는 이 헤더를 아직 설정하지 않는다. 누락 시 report가 false로 처리하므로 현재는 유료 이용자도 무료 범위로 응답한다. 기존 저장된 유료 내용을 무조건 노출하도록 우회하지 않는다.

### 4. #55 삭제 정책과 소비 검증

- 최신 core는 RECORDS 삭제 완료 후에도 student를 `DELETION_REQUESTED`로 유지하며 재개를 자동 허용하지 않는다(`issue-45-account-management.md`, `ChildManagementService`). 반면 report 기본안은 자체 삭제 완료 이후의 새 명령을 허용한다(`app/deletion/state.py`). report 단독 완료가 learning까지 완료했다는 뜻은 아니므로 이 상태에서 전체 재개 가능하다고 보고하지 않는다. 우선 병합된 core 동작과 맞추고, 재개가 필요하면 별도 확정 계약을 연결한다.
- 공유 삭제 data에는 `studentId`가 필수다. 현재 report 소비자는 subject와 deletionRequestId/scope를 읽지만 data.studentId·source 및 원래 봉투의 필수값을 엄격하게 대조하지 않는다. #45의 정상 발행과 맞는 것만으로 계약 검증이 끝난 것은 아니며 잘못된 이벤트 거부 검사가 필요하다.
- core `ReportLifecycleService`는 job 식별자·상태 전이는 검사하지만 삭제 표식 검사까지 구현한 것은 아니다. `ChildManagementService`에도 기존 report_job 취소 처리는 없다. 삭제 직전 발행된 이벤트가 뒤늦게 도착할 때의 처리와 queued job 정리를 core 담당과 대조한다.
- 추가 `20261027_02_report_deletion_guard.py`는 기존 기능 커밋과 분리되어 보존되었다. 정책과 함께 검토하고 기존 migration을 덮어쓰지 않는다.

## 이번 검사 결과와 한계

- `uv sync --locked`, Ruff check·format check(72개 파일), `git diff --check` 통과.
- report 전체 첫 실행: **144 passed / 1 failed / 2 errors**, 75.10초. PDF용 Chromium 실행 파일 미설치로 렌더링 2개가 setup 오류, 이를 사용하는 MinIO 생성 1개가 FAILED였다.
- 필요한 Chromium headless shell을 설치한 뒤 해당 **3개만 재실행하여 모두 통과**, 18.15초. 합계 147개 항목을 확인했지만 이를 설치 후 단일 전체 실행 147 passed로 표현하지 않는다. 앱 기능 코드·테스트 기대값은 변경하지 않았다.
- root 계약·스키마 검증 unittest **53개 통과**, 1.803초. 첫 시도는 report .venv에 jsonschema가 없어 2개 모듈 import 오류였다. CI와 같은 `jsonschema==4.26.0`을 `uv run --with` 임시 환경에서 사용해 재검증했으며 production 의존성/lock은 바꾸지 않았다.
- 사용한 외부 자원은 테스트용 일회용 PostgreSQL·RabbitMQ·MinIO, moto 및 고정 HTTP 응답이다. core·learning·AI 전체 E2E, 새 Linux 이미지 빌드, 세 DB 전체 migration cycle, 원격 CI는 이번에 실행하지 않았다. Starlette TestClient의 기존 deprecation warning은 남는다.
- 병합 충돌 없음과 서비스 계약 정합성은 다른 결과다. 위 연결 차이는 남아 있으므로 현재 브랜치를 전체 서비스 통합 완료본으로 표시하지 않는다.

## 다음 순서

1. #50 production codec·worker 연결을 완료하고 공유 계약으로 검증한다.
2. #52·#53은 이미 수행한 단독 완료 조건을 검토에 제출할 수 있게 정리한다. #51은 #27 실제 입력 대조를 남긴다.
3. #55 소비 검증·core 완료 보고를 연결하되 삭제 후 재개와 늦은 이벤트 정책을 먼저 맞춘다.
4. 닉네임·현재 상품 권한·#27이 확보되면 #54와 실제 생성→파일→조회 흐름을 검증한다. #64 실제 AI 연동은 별도로 확인한다.
5. 각 이슈의 남은 조건을 충족한 뒤 이슈별 PR을 develop으로 제출한다. 하위 이슈가 모두 완료되면 #56 에픽의 전체 완료 조건을 확인한다. 이번 점검은 자동 완료 처리의 근거가 아니다.
