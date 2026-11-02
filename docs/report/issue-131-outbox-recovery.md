# #131 report Outbox 실패 격리와 학생별 발행 순서

## 승인된 정책

사용자가 전달한 팀 승인 기준을 적용한다.

- subject(학생 UUID)별 발행 순서 유지. 실패한 학생만 대기하고 다른 학생은 계속 처리.
- 최초 실패 후 1·5·15분으로 재시도 3회. 총 4번 실패하면 격리.
- 격리된 선두를 포함한 그 학생의 뒤 이벤트는 건너뛰지 않는다. 운영자가 원인을 고친 뒤 선두를 수동 재처리하면 뒤 이벤트도 순서대로 진행한다.
- 원래 이벤트 id·payload를 보존한다. 발행 후 DB 기록 전 장애 등은 동일 id 재전달이며 core 멱등 처리와 종료 상태 방어를 유지한다.

## 구현

기존 OutboxRepository·OutboxRelay와 worker relay_loop를 사용한다. 새 공통 라이브러리·HTTP API·큐·이벤트 스키마는 추가하지 않는다.

- `published_at IS NULL`인 학생별 가장 앞 행(created_at, id)만 선점한다. 앞 행이 백오프/격리 상태여도 뒤 행을 선택하지 않는다. 100개 조회 제한은 적격 학생별 선두에 적용해 동일 학생의 다량 대기가 다른 학생을 숨기지 않는다.
- PG publish 세션 advisory lock을 학생별로 유지한다. 여러 relay가 같은 학생의 뒤 이벤트를 먼저 보내거나 같은 행을 동시에 보내지 않는다. AMQP를 기다리는 동안 DB 트랜잭션을 열어 두지 않는다.
- enqueue는 별도 키의 짧은 PG 트랜잭션 잠금으로 생산자끼리 순서를 정한다. 미커밋 선두가 뒤 커밋에 추월되지 않으며 생성 DB 트랜잭션은 network publish 잠금을 기다리지 않는다.
- 발행 예외/timeout만 짧은 트랜잭션으로 실패 횟수·다음 시각을 저장한다. confirm 이후 mark_published 저장 실패는 발행 실패 횟수로 오분류하지 않고 원래 id를 재발행한다.
- CancelledError는 시도 횟수를 소모하지 않고 선점을 해제한다. 학생 삭제로 이미 없어진 Outbox는 되살리지 않는다.
- `BROKER_UNAVAILABLE|PUBLISH_TIMEOUT|PUBLISH_FAILED`만 저장한다. 원문 예외·학생 내용·자격 증명은 DB/운영 로그에 넣지 않는다. 격리는 ERROR 로그로 알리고 CLI에서 조회한다.

## DB 적용과 롤백

새 Alembic `20261030_04`, 직전 `20261029_03`(#132 job guard) 유지. 기존 행의 두 카운터만 0으로 초기화하며 id/payload/created_at/published_at은 수정하지 않는다. 영구 SQL DEFAULT를 두지 않고 앱이 초기 카운터를 전달한다.

기존 worker를 멈춘 뒤 `alembic upgrade head` → 새 worker를 기동한다. 이전 worker는 새 NOT NULL 카운터를 쓰지 않으므로 구버전과의 혼합 실행은 지원하지 않는다. 공개 조회 API의 DB 사용은 바뀌지 않는다.

다운그레이드는 worker 중지 후 수행한다. 이벤트 본문·발행 상태는 보존되지만 실패/격리/수동 재처리 메타데이터는 사라지므로 먼저 운영 상태를 확인·보관한다. 구버전은 모든 미발행 행을 다시 즉시 시도하는 기존 동작으로 돌아간다.

## 수동 운영 (HTTP 권한 우회 API가 아님)

신뢰된 report 운영 환경에서 기존 DATABASE_URL 등의 설정과 DB 접근 권한으로 실행한다.

```powershell
uv run python -m app.outbox.manage list --limit 100
uv run python -m app.outbox.manage requeue <event-uuid>
```

list는 payload·학생 식별자 없이 이벤트 id/type·실패 코드/횟수·격리 시각·수동 이력만 보여 준다. 재처리는 격리된 미발행 행만 1회 조건부 갱신하며, 경쟁 중/삭제됨/이미 발행됨은 NOT_REQUEUED(종료 코드 2)다. 기존 id·내용·원래 순서 위치는 바꾸지 않는다. 실패 카운터와 백오프는 초기화하고 manual_retry_count·last_requeued_at은 기록한다. 원인 수정 없이 재시도하면 다시 같은 정책으로 격리된다.

core #47의 관리자 작업 재생성(#152)은 새로운 jobId를 만드는 기능이다. 이 CLI는 이미 만들어진 **결과 이벤트 전달**을 다시 시도하는 별개 기능이며 리포트를 재생성하지 않는다.

## 검증

- 기준 develop `5f32ee6`(#172 전수 점검·#161 포함), 2026-10-30 재검증. #130 문서 브랜치와 독립적으로 develop에 적용 가능하다.
- report 전체 pytest **287 passed**, 91.33초. Ruff check·format **90개 파일 통과**. 기존 Starlette/httpx 사용 중단 예정 경고 1건은 남아 있다.
- 실제 PostgreSQL·RabbitMQ에서 mandatory 반환을 일으켜 4회 실패/격리·다른 학생 정상 발행·바인딩 복구 후 동일 id/payload 재처리·같은 학생 started→completed 순서를 확인했다. 여러 relay·미커밋 생산자·105개 대기 행·삭제 경합·CLI 1회 재처리도 검사했다.
- 테스트 시계 주입으로 1·5·15분 직전/정각을 확인했다. 운영 대기값을 줄이지 않았으며 실제 21분을 기다렸다고 표현하지 않는다.
- 임시 PostgreSQL에서 세 서비스 마이그레이션·반복 적용(no-op)·report base까지 롤백 후 재적용 통과. ERD **69테이블/613컬럼**, 63개 음성 제약 사례·74개 CHECK 값 집합·24개 인덱스 일치. 기존 v3 미발행/발행 이벤트를 넣고 v4 업그레이드→v3 다운그레이드→v4 재적용 시 원본 보존도 별도 검사했다.
- DB CI 검증기 unittest **83개 통과**. 기존 DB 트랜잭션 테스트의 직접 INSERT에도 새 필수 카운터를 명시했다. 기존 실패 4건을 보완한 뒤 전체 287개를 다시 실행한 결과다.
- report Docker 운영 이미지 빌드 통과(`sagomungchi/report-service:issue131-local`).
- GitHub Actions는 feature push만으로 실행되지 않으므로 위 결과는 로컬 CI 상당 검사다. PR 생성 후 GitHub CI 결과를 별도로 확인한다.

## 이슈 항목 대조

- [x] 순서 단위·격리·알림·수동 재처리 정책 확정: 학생별 순서, ERROR 로그와 운영 CLI.
- [x] 시도 횟수·백오프·격리 구현 및 새 Alembic revision.
- [x] 영구 실패가 있어도 다른 subject가 발행되는 실제 브로커 테스트.
- [x] report pytest 통과.

구현·검증을 위한 문서이며 GitHub 이슈 체크박스·PR은 자동 변경하지 않았다.
