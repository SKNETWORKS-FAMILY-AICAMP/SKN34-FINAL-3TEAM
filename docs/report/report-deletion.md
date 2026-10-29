# 이슈 #55 학생 삭제 처리

아래는 기존 브랜치의 구현·검증 이력이다. 현재 개인 통합본의 기준과 실행 결과는 마지막 절을 따른다.

`feature/report-deletion`은 develop `47e5ffe`와 최신 #50~#54를 병합했다. 공유 `student.deleted.v1.schema.json`을 재사용하고 source=core-service, type/dataschema, UUID, subject=data.studentId, deletionRequestId·scope·허용 필드를 검사한다. 잘못된 메시지는 삭제 전에 InvalidEvent로 거부해 DLQ로 보내며 재시도하지 않는다.

## 처리 순서와 실패

1. 학생 단위 배타 advisory lock을 얻는다. 생성은 같은 학생 shared lock과 job lock을 사용한다. RUNNING 생성이 실제 수행 중이면 삭제는 오류를 반환해 기존 지연 큐로 이동하며, 생성이 종료된 다음 재시도한다.
2. `report_deletion_guard`를 PENDING으로 커밋한다. 이 상태에서는 새 생성과 리포트 조회를 차단한다.
3. 해당 학생 `reports/{studentId}/` 아래 S3 객체를 삭제한다. 실패하면 DB 리포트 행과 PENDING 장벽을 남기고 재시도한다. 파일 일부가 먼저 삭제되었을 수 있으므로 원자적 S3/DB 트랜잭션이라고 표현하지 않는다.
4. `report_item_evidence → report_item → report_file → weekly_report`와 해당 학생 Outbox를 삭제하고 guard COMPLETED·processed_event를 같은 DB 트랜잭션에 저장한다.
5. 기존 내부 HTTP 클라이언트로 core 완료 API에 `{service:"report"}`를 보낸다. 실패하면 이벤트 재시도에서 물리 삭제를 반복하지 않고 완료 보고를 다시 보낸다.

동일 이벤트 두 번 처리 시 S3/DB 삭제는 한 번이고 완료 보고는 두 번일 수 있다. 다른 학생은 삭제 범위에 들어가지 않는다. 더 오래된 RECORDS 이벤트는 이미 처리한 삭제를 반복하지 않으며 PROFILE은 RECORDS보다 우선한다.

## 최신 core와 맞춘 정책

PROFILE·RECORDS 모두 기존 리포트 내용/파일을 삭제하고 이후 새 생성도 차단한다. core가 RECORDS 완료 뒤 student를 DELETION_REQUESTED로 유지하므로 report 단독 완료만으로 재개하지 않는다. 삭제 시각보다 늦은 명령도 같은 규칙이다. 이전의 RECORDS 새 명령 허용 구현안은 폐기했다. 향후 재개 계약·표식 보존은 별도 검토하며 추가 DDL은 [별도 스키마 보고서](report-deletion-schema.md)를 따른다.

`worker.run(generator=None)`은 기본 진입점부터 확정 v1 codec·생성/삭제 구독·Outbox·S3 삭제·core 완료 보고를 조립한다. 전체 생성기는 닉네임 공급 경로 등이 미연결이므로 기본값은 GENERATOR_NOT_CONFIGURED 실패이며 가짜 완료를 만들지 않는다. 실제 생성기는 별도 주입 가능하다. 종료는 소비 취소 → 진행 중 처리 대기 → 채널 정리 순서이며 SIGTERM 유예·DLQ 복구는 운영 설정이 필요하다.

## 검증

아래 삭제 구현 직후의 누적 전체 실행은 **182 passed, 0 failed, 0 skipped (141.69초)**다. Ruff check/format(78개 파일), root 계약·스키마 unittest 53개(1.985초), 문서 UTF-8/충돌 표식/내부 링크 10문서·11링크, API 4.2 표 구조, `git diff --check`를 통과했다. 3개 DB migration·ERD 대조·반복 no-op·report 롤백/재적용도 16.3초에 통과했다([스키마 상세](report-deletion-schema.md)).

직전 전체 검사에서는 179개 통과/3개 setup 오류였다. 서로 다른 일회용 MinIO의 자격 증명을 boto3 기본 세션이 재사용한 테스트 격리 문제여서 fixture에서 기본 세션을 분리했다. 위 182개는 수정 후 단일 전체 실행 결과다. Starlette TestClient의 기존 deprecation warning 1개는 남아 있다.

최종 `sagomungchi/report-service:issue55-20261028` 이미지 빌드와 worker import도 통과했다. UID 10001·read-only root·네트워크 차단·`/tmp` tmpfs에서 3종 파일을 생성했고 한글 PDF(191,409바이트)의 논리 텍스트가 #53에서 시각 확인한 출력과 일치했다. 운영 이미지에 pytest가 없음을 확인했다. 실제 core·learning·AI 전체 E2E와 운영 AWS 검증은 포함하지 않는다.

2026-10-28 변경 후 삭제 집중 검사 **18개 통과(18.61초)**. 실제 PostgreSQL에서 중복·다른 학생 보존·완료 보고 재시도·생성/삭제 lock·양 scope의 늦은/새 명령 차단을 확인했다. 계약 위반 7개는 삭제 호출 전에 거부한다. 실제 RabbitMQ의 팀 토폴로지 retry.1 큐 이동과 본문/time 보존, 재전달 두 번에도 물리 삭제 한 번을 확인했다. 최초 저장소 실패는 주입하고 재전달 성공은 실제 MinIO의 학생별 6개 객체·DB 리포트 정리로 확인했다. core 완료 호출은 대역이며 실제 HTTP 요청의 토큰/SYSTEM·scope/본문은 별도 MockTransport 검사다. 재시도 1분 TTL을 실제로 기다린 테스트는 아니며 큐에서 메시지를 꺼내 즉시 재전달했다.

생성 도중 업로드 취소는 작업 스레드 정리까지 기다린 뒤 lock을 반환한다. 다른 프로세스의 비정상 종료로 남은 RUNNING 행은 삭제가 lock을 얻은 후 함께 정리한다. 발행 중이던 Outbox 이벤트, 이미 발급된 URL, S3 이전 버전/캐시는 report DB 삭제만으로 모두 회수할 수 없으므로 인계 문서의 core/인프라 후속 사항이 필요하다.

## #27 사전 보완 병합 후 회귀 (2026-10-28)

#51 돌아보기 입력·#53 공통 난이도 표시·#54 응답/OpenAPI 보완을 순서대로 이 브랜치에 병합했다. 문서 충돌은 기존 MinIO 검증과 새 계약 설명을 모두 보존해 해결했다. 삭제 코드·guard migration은 변경하지 않았다. 누적 전체 **203 passed, 0 failed, 0 skipped (133.01초)**, Ruff 78파일 통과. 기존 TestClient deprecation warning 1개가 있다. 실제 DB·브로커·MinIO 검사는 포함하며 core 완료 호출과 learning/AI 응답의 대역 범위는 유지한다. 상세 변경과 #27 확인 대기는 [인계 문서](report-service-handoff.md)를 따른다. 추가 PR·원격 push는 하지 않았다.

## #54 통합본 기준 재검증 (2026-10-28)

개인 통합 브랜치 `local/issue54-integration`의 #54 완료 커밋 `f1e57f1`에 기존 #55 `090237c`를 병합했다. 확인한 원격 develop은 `b644b56f`다. 별도 작업 폴더나 가상환경을 추가하지 않았다. 충돌한 8개 파일에서 #53 nullable 출력과 #54 응답·검증을 유지하고, nullable 설명이 포함된 OpenAPI와 HTML의 빈 질문 제목 생략을 반영했다.

### 해야 할 일·완료 조건

- [x] 기존 EventConsumer로 `report.student.deleted` 소비, `processed_event` 멱등 처리
- [x] PROFILE·RECORDS 대상 학생의 weekly_report·report_item·report_item_evidence·report_file 및 S3 prefix 삭제
- [x] 기존 내부 HTTP 클라이언트로 core 완료 API에 `{service:"report"}` 보고
- [x] 같은 이벤트 두 번 소비 시 물리 삭제 한 번, 다른 학생 행·객체 보존
- [x] S3 실패 시 실제 RabbitMQ retry.1 이동, 재전달 후 실제 MinIO 객체·DB 행 삭제
- [x] Ruff check·format 및 전체 pytest 통과

PROFILE 삭제가 이미 완료된 뒤 더 늦은 PROFILE/RECORDS 이벤트를 받으면 첫 전달은 처리된 것으로 기록하면서도 완료 보고 재시도에서는 cutoff 시각 검사로 거부하는 오류를 수정했다. 최초 처리와 재전달에 동일한 PROFILE 우선 규칙을 적용한다. 무료·유료 조회나 삭제 범위를 바꾸는 수정은 아니다. 두 scope의 회귀 테스트는 수정 전 실패했고, 수정 후 전체 검사에서 통과했다.

### 정책 근거와 경계

현재 core `ChildManagementService.confirm`은 두 scope 모두 학생을 차단하며, `complete`는 PROFILE일 때만 프로필을 제거한다. RECORDS 완료 시 활성 상태로 복구하는 코드는 없다. report는 두 scope 모두 리포트를 제거하고 자동 재생성을 허용하지 않는 기존 구현을 유지한다. `state-diagram.md` 2.2와 `sequence-diagram.md` 10.1의 RECORDS 상태 설명에는 이 core 구현과 차이가 남아 있다. 서비스 재개 정책은 core 담당 확인 없이 report에서 새로 정하지 않는다.

실행 중인 생성은 학생 shared lock, 삭제는 exclusive lock으로 직렬화한다. lock을 얻지 못한 삭제는 기존 메시지 재시도를 사용한다. 삭제 PENDING에서는 조회·새 생성을 차단하고, 비정상 종료로 남은 RUNNING 행도 lock 획득 후 삭제한다. core 완료 보고 실패 시 DB/S3를 다시 지우지 않고 완료 보고를 재시도한다.

### 현재 실행 결과

- 로컬 `backend/report-service/.venv`에서 전체 **239 passed, 128.73초**, 실패·건너뜀 없음. PostgreSQL·RabbitMQ·MinIO는 일회용 Docker 컨테이너를 사용했다.
- Ruff check 통과, format 검사 78개 파일 통과. 기존 Starlette/httpx 폐기 예정 경고 1개는 남아 있다.
- 공통 계약·스키마 unittest **58개 통과**.
- 팀 CI 마이그레이션 검사: 3개 DB 적용·ERD 대조·반복 no-op·report downgrade/upgrade **34.9초 통과**. core 40/351, learning 19/158, report 7/50(테이블/컬럼), 제약 음성 사례 60개.
- 운영 이미지 `local/issue55-report:20261028` 빌드 성공.
- 기존 #55 브랜치의 nullable 질문 표시 변경을 포함한 웹 린트·TypeScript/Vite 빌드 통과(Node 22, 팀 CI 명령). 번들 크기 경고는 남아 있다.

core 완료 응답은 대역이며 실제 내부 헤더·경로·본문은 MockTransport로 검사했다. 실제 core/learning/AWS 전체 E2E 완료를 뜻하지 않는다. migration은 일회용 DB에서만 실행했으며 운영 적용은 하지 않았다. JUnit 결과는 저장소 밖 기존 context 폴더의 `issue55-pytest.xml`에 보관한다.
