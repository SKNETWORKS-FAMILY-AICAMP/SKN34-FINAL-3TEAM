# #152 관리자 실패 리포트 재처리

## 합의와 작업 경계

2026-10-29 사용자가 전달한 #47 담당자 답변을 기준으로 한다.

- core #47: 관리자 요청 접수·권한·멱등, 원래 실패 작업과 새 재처리 작업 연결, 생성 요청 발행, 결과별 작업 상태·실행·감사 기록.
- report #152: 새 jobId 요청 실행, 중복·동시 전달 방어, 이전 판 보존, 요청 jobId에 맞는 시작·성공·실패 이벤트.
- core는 **새 jobId**를 발행하며 같은 관리자 요청의 재전송에는 그 ID를 유지한다. report 이벤트에 originalJobId를 추가하지 않는다.
- 현재 core 관리자 재처리 HTTP 경로는 여전히 REPORT를 JOB_RETRY_UNAVAILABLE로 차단한다. 이번 report 공급 검증을 관리자 버튼 전체 완료로 표현하지 않는다.

## 기존 코드 재사용 판정

| 요구 | 재사용 코드 | 판단 |
|---|---|---|
| ADMIN_RETRY 수신 | ReportV1Codec, GenerationConsumer | 기존 v1 enum·SYSTEM scope 그대로 사용 |
| 새 작업 실행 | GenerationService.generate | 기존 실제 생성 파이프라인 호출 |
| 이전 실패 단순 재전달 종료 | get_or_create + RUNNING 검사 | 기존 COMPLETED/FAILED는 생성기·이벤트 추가 없이 반환, #50 유지 |
| 같은 요청 동시 전달 | JobLocks의 PG 세션 advisory lock | 한 worker만 실행, 나머지는 기존 consumer 지연 재시도 |
| revision·이전 판 보존 | ReportRepository.get_or_create | 학생/주 PG 트랜잭션 잠금 + 다음 revision, 기존 행 수정 없음 |
| 시작·결과 식별 | ReportV1Codec.encode | 새 jobId·해당 reportId·studentId 반환 |
| 원자성 | GenerationService._start/_finish, OutboxRepository | 시작·종료 변경과 각각의 Outbox가 같은 트랜잭션 |
| 전송 보장 | OutboxRelay, EventConsumer | confirm 후 발행 기록, 재전달 허용, core가 이벤트 중복·종료 전이 방어 |
| 현재 권한 | core의 기존 narrativeEnabled 계산·요청 필드 | report는 요청의 값을 그대로 사용, 새 job에 과거 유료 값을 임의 복사하지 않음 |
| 삭제 | report_deletion_guard + core ACTIVE 프로필 조회 | 기존 장벽 유지, 신규 생성/거짓 완료 없음 |

**제품 실행 코드·DB·HTTP·이벤트 스키마 변경이 필요하지 않았다.** 이번 변경은 기존 경로에 대한 관리자 재처리 검증, 예시 및 설계 문서 정렬이다.

## 테스트 구분

### 실제 PostgreSQL + 합성 생성기

`backend/report-service/tests/test_admin_retry.py`는 실제 Alembic DB·JobLocks·GenerationService·ReportV1Codec를 사용한다. 생성기는 완료/장애/대기를 제어하는 합성 대역이다.

- 실패 작업 A → 새 ADMIN_RETRY B의 성공/재실패, narrativeEnabled true/false 전달.
- 같은 봉투·새 봉투 id의 같은 jobId 중복, 기존 FAILED/COMPLETED 명령 지연 재전달.
- B 실행 중 두 서비스 인스턴스 경합: 하나만 실행, 다른 호출 GenerationBusy. 지연된 A가 B의 상태를 변경하지 않음.
- 이전 완료 내용·파일 행·실패 판 보존, revision 1→2→3.
- started/completed/failed Outbox 삽입 직후 장애를 주입해 전체 트랜잭션 rollback·재전달 복구 확인.
- PENDING/COMPLETED 학생 삭제 장벽 유지, 예시 7개의 v1 스키마 및 실행 식별 일치.

### 실제 Compose 연동

`scripts/verify_report_compose.py --admin-retry`는 기존 #56 환경을 재사용하고 worker를 두 개 실행한다. core·learning·report·PostgreSQL·RabbitMQ·MinIO·HTML/MD/PDF 생성은 실제 코드다. AI 서술 응답만 합성 HTTP 대역이며, AI 503은 이 대역에서 주입한다.

core #47의 미연결 관리자 생산자 대신 **검증 코드가 core report_job을 합성 seed하고 기존 v1 명령을 RabbitMQ에 발행**한다. 실제 core lifecycle 소비자가 job 상태·reportId·job_execution을 반영하는 것까지 검사한다. 관리자 권한/Idempotency-Key/원작업 연결/감사 구현을 검증한 것은 아니다.

1. 기존 완료 판·실제 파일 생성.
2. 원작업 A의 AI 실패.
3. 새 작업 B로 재성공, 두 worker에 같은/다른 봉투 ID의 중복 명령 전달.
4. 또 다른 새 작업 C의 재실패.
5. 현재 narrativeEnabled=false로 무료 재처리, AI 호출 생략.
6. 실제 core에 원작업의 늦은 failed/started·완료된 새 작업의 늦은 started 전달, 종료 상태 불변 확인.
7. 실제 retry.1의 지연 재전달까지 확인 후 report 판·Outbox 수 불변 및 기존 S3 파일 바이트 보존.

검증기는 RobustChannel의 passive queue 객체 캐시가 아닌 실제 `queue.declare()` 응답으로 최신 메시지 수를 읽는다. 초기 검증의 큐 대기 초과는 캐시된 카운트를 재사용한 검증기 문제였다. 실제 RabbitMQ 큐는 이미 비어 있었으며 검사 생략 없이 수정 후 전체 재실행을 통과했다.

## 실행

core/learning의 현재 소스로 JDK21 bootJar를 빌드한 뒤 실행한다.

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
# 저장소 루트, report Python 환경에서 실행
python -X utf8 scripts/verify_report_compose.py --admin-retry --output ../tmp/issue152-compose-final-20261029
```

모델·실제 학생 원문·팀 AWS 자격 증명을 사용하지 않는다. Compose 프로젝트는 매번 고유 이름이며 종료 시 해당 프로젝트의 컨테이너·네트워크·볼륨만 정리한다. 결과·로그는 저장소 밖에 보관한다.

## 검증 결과

- 전체 report 테스트: **267 passed**, 85.68초. 신규 #152 검사 12개 포함.
- report Ruff check·format: **82개 파일 통과**.
- 실제 Compose: 위 **8개 시나리오 + 공유 봉투/본문 스키마 검사 통과**. revision 1~5 상태는 COMPLETED → FAILED → COMPLETED → FAILED → COMPLETED, 실제 core job_execution도 각 작업 결과와 일치했다.
- 두 worker 경합으로 지연 큐에 들어간 명령 2개는 기존 60초 TTL 후 다시 전달됐다. 실제 큐 카운트 `[0,2] → [0,0]`, 리포트 5개·Outbox 10개 유지, 기존 완료·실패 행과 첫 판 S3 바이트 보존을 확인했다.
- 실제 core는 원작업의 지연 failed/started와 완료된 새 작업의 지연 started를 받아도 원작업 FAILED·새 작업 COMPLETED를 유지했다.
- 공유 report 계약 검사 4개 통과. JSON 예시 7개 및 실제 연동 요청/이벤트는 v1 스키마와 일치한다.
- 검증 전용 컨테이너·네트워크·볼륨 정리 완료. 결과는 저장소 밖 `../tmp/issue152-compose-final-20261029/results.json`, pytest 결과는 `../tmp/issue152-report-tests.xml`에 보관했다.
- 이번에는 report 공급 경로를 검증했다. core #47 관리자 API 권한·요청 접수·원작업 연결·감사는 미연결 상태로 남아 있다. GitHub PR·이슈 상태·댓글은 변경하지 않았다.

## #152 요청/완료 조건 대조

| 이슈 항목 | 결과 |
|---|---|
| 새 job/revision 재사용 여부 및 흐름 | 기존 코드로 충족, 위 재사용 표·API 5.5.1에 명시 |
| 원작업 연결 및 요청 예시 | core 소유로 합의, report v1 예시 7개 제공 |
| 실제 재처리 실행과 성공/재실패 이벤트 | 실제 파이프라인·브로커·DB에서 확인 |
| 중복·동시 전달 및 기존 판 보존 | PG 동시 대역 테스트 + worker 2개 Compose 지연 재전달·파일 보존 통과 |
| 시작/결과 식별·지연 이벤트 경계 | 새 jobId/reportId 일치, 실제 core 종료 상태 불변 통과 |
| 상태/Outbox 원자성 | 실제 PG에서 started/completed/failed 삽입 장애·rollback·재전달 복구 통과 |
| 기존 종료 job 재전달 정책 | 완료·실패 원작업 재전달 모두 생성/이벤트 추가 없음, #50 유지 |
| 문서·예시·이벤트 계약 | 기존 스키마 유지, 설계 문서·검토 기록·스키마 검사 반영 |
| pytest·Ruff | 267개·82파일 검사 통과 |

**판정: report #152의 합의된 공급 범위는 완료. core #47의 관리자 접수 연결 후 사용자 버튼 경로의 전체 검증이 별도로 필요하다.**

## #47에 제공할 계약

[요청·결과 JSON 7개와 설명](../../contracts/examples/report-admin-retry/)을 사용한다. 성공/재실패는 서로 다른 jobId의 예시다. 각 실행은 started와 completed 또는 failed 하나로 종료한다.

원작업 연결 및 감사 저장 형식은 core #47이 결정한다. 현재 report는 새 jobId의 생산자가 적법한 재처리를 발행했다고 신뢰하며 원작업을 core DB에서 직접 조회하지 않는다. 삭제와 경쟁한 core queued job의 취소·정리도 core 범위다. 기존 삭제 장벽은 #152에서 해제하지 않는다.
