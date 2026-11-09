# DB 스키마 결정·개발 가이드 (#5·#13·#14·#19·#230)

V6 마이그레이션 주석이 참조하는 구 `db-policy-schema.md` 내용은 이 문서 2장(구 db-schema.md 포함). 설계 원본은 [ERD](../design/erd.md), 현재 버전·수치는 ERD 8장.

## 1. 기술 결정 (#5)

| 결정 | 이유·경계 |
|---|---|
| UUID는 애플리케이션 생성, DB DEFAULT 없음 | API·이벤트 ID를 DB에 그대로 전달. 시간·상태·카운터도 앱이 전달하고 정책값을 DEFAULT로 고정하지 않음 |
| 모든 컬럼의 NULL 허용 여부 명시 | 처리 전 결과·완료 시각, 최초 답변의 이전 답변, 최초 결제의 구독 연결 등 |
| 같은 DB의 `conversation_message.scope_student_id`, `idempotency_record.user_id` FK | 존재 검사. 다른 서비스 DB 식별자는 논리 참조 |
| FK 삭제·갱신 NO ACTION | 삭제 정책을 CASCADE로 대신 결정하지 않음. 순환 참조 3곳만 명시적 트랜잭션에서 지연 검사 |
| 상태·종류 CHECK, 복합·부분 UNIQUE | 응답 전용 NOT_STARTED·SAVED·PROCESSING은 DB 상태로 넣지 않음 |
| 판정 결과는 DONE일 때만, HELD와 사유 동시 존재 | `IS NOT DISTINCT FROM`으로 NULL 우회 방지 |
| `judgment_element.verified`·`satisfied` NOT NULL·CHECK | 검증되지 않은 근거를 충족으로 저장하지 않음 |
| 리포트 `state`는 COMPLETED일 때만 | 실패와 기록 없음·표본 부족 구분 |

같은 미션·시도·기준표 소속 여부 같은 다중 참조 검증은 서비스 계약(단일 FK는 존재만 보장).

## 2. 확정 정책 반영 (#19, core V6~V7·learning V4~V5)

| 대상 | 적용 | 이유 |
|---|---|---|
| core `student` | `birth_year` NOT NULL, `user_account_id` 제거, 학년 3~6 CHECK(V41에서 3~9로 넓힘, 자동 진급 #432·P26) | P01 보호자 중심 등록, P03 초3~6 |
| core `guardianship.method` | `REGISTER`만 | P02 기존 계정 연결 제외 |
| core `notification_setting.channel` | `IN_APP`만 | P10 |
| core `error_report.category` | NOT NULL, 5유형 CHECK | 신고 유형 확정 |
| core `product` | `limits` NOT NULL, `price` NOT NULL, 고정 코드 CHECK 제거 | P13 데이터 기반 상품·한도 |
| learning `answer` | `speech_transcribed` 제거 | P03 음성 제외 |
| learning `followup_bank_question`·`followup.bank_question_id` | 질문은행 신설, source는 LLM·LLM_RETRY·BANK, BANK일 때만 ID 필수 | P16 재실패 시 질문은행 출처 추적 |

- 상품 코드: ERD의 `FREE|PREMIUM 등`은 닫힌 enum이 아니라 초기 예시. `code` UK 유지, 새 상품 행은 새 고유 코드. 기존 `BASIC/PLUS`를 임의 변환하지 않음
- 무료 상품 선택: `code = FREE` 조회 대신 `PAYMENT_FREE_PRODUCT_ID`로 지정(#48, 2026-10-28 결정, ERD 3.4)
- 자녀 최대 3명, 되묻기 최대 2회, 질문은행 type 일치·활성 여부는 서비스 검증

### 기존 데이터가 있는 DB의 적용 절차

1. 백업 후 쓰기 중지(컬럼 제거·NOT NULL 때문에 이전 앱과 동시 사용 금지)
2. core `-target=6 migrate`, learning `-target=4 migrate`로 준비 버전까지만 적용
3. 아래 사전 점검의 보완 대상 건수 확인. 출생연도는 확인된 등록 정보, 상품 한도·금액은 승인된 조건으로 채움. 확인되지 않으면 중단
4. 삭제 예정 값·폐기 코드는 승인된 전환 방법으로 처리(자동으로 OTHER·LLM 변환이나 가상 출생연도 금지). BANK 이력은 실제 질문에 연결
5. 점검이 모두 0건이면 `migrate`로 core V7·learning V5 적용

V7·V5는 검사부터 DDL까지 한 트랜잭션(변경 테이블 잠금). 실패 시 최종 버전만 롤백되고 준비 버전은 남아 보완 후 재시도 가능. 운영 DB 초기화·이력 수정 금지.

```sql
-- core V6 이후
SELECT 'student.birth_year' AS item, count(*) AS pending FROM student WHERE birth_year IS NULL
UNION ALL SELECT 'student.user_account_id', count(*) FROM student WHERE user_account_id IS NOT NULL
UNION ALL SELECT 'student.grade', count(*) FROM student WHERE grade NOT BETWEEN 3 AND 6
UNION ALL SELECT 'product.price/limits', count(*) FROM product WHERE price IS NULL OR limits IS NULL
UNION ALL SELECT 'guardianship.method', count(*) FROM guardianship WHERE method <> 'REGISTER'
UNION ALL SELECT 'notification_setting.channel', count(*) FROM notification_setting WHERE channel <> 'IN_APP'
UNION ALL SELECT 'error_report.category', count(*) FROM error_report
  WHERE category IS NULL OR category NOT IN ('WRONG_JUDGMENT','ODD_QUESTION','MISMATCH','INAPPROPRIATE','OTHER');
```

```sql
-- learning V4 이후
SELECT 'answer.speech_transcribed' AS item, count(*) AS pending FROM answer WHERE speech_transcribed
UNION ALL SELECT 'followup.TEMPLATE', count(*) FROM followup WHERE source = 'TEMPLATE'
UNION ALL SELECT 'followup.bank_question_id', count(*) FROM followup
  WHERE (source = 'BANK' AND bank_question_id IS NULL) OR (source <> 'BANK' AND bank_question_id IS NOT NULL);
```

업그레이드 검사: [`scripts/check_policy_migrations.py`](../../scripts/check_policy_migrations.py)가 별도 PostgreSQL에 `policy_*` DB 4개를 만들어 적용·데이터 보존·제약을 검사(같은 이름 DB가 있으면 중단, 삭제·초기화하지 않음).

## 3. 데이터 관리

- AI Hub 원본·압축 해제본·전처리 결과·실제 답안 샘플은 GitHub에 올리지 않음. 저장소 밖 또는 무시되는 `local_data/`에 보관(`.gitignore`: 데이터셋 이름, `aihub/`, `ai_hub/`, `local_data/`). 이름을 바꾼 데이터는 자동 판별되지 않으므로 커밋 대상을 직접 확인
- 검증 스크립트의 예제 값은 합성 데이터. 이미 공유 환경에 적용한 마이그레이션은 수정하지 않고 새 버전 추가

## 4. 마이그레이션 CI (`ci-db-schema.yml`)

마이그레이션·ERD·검증 스크립트·`test_verify_db_schema.py`·검증 fixture·관련 설정이 바뀐 PR에서만 실행(보고서만 바꾼 PR 제외). PR별 이전 실행 취소, 제한 3분. 전체 `scripts/tests` 계약 회귀는 별도 `ci-contracts.yml`에서도 실행하며 DB 변경에만 묶이지 않는다(#143).

1. PostgreSQL 17.11 서비스 컨테이너(CI 전용 임시 계정, Secrets 불필요)
2. report-service `uv.lock`으로 Python 3.12·마이그레이션 의존성 준비
3. `python -O -m unittest discover -s scripts/tests -p test_verify_db_schema.py`로 DB 검증기 회귀 테스트
4. `scripts/check_db_migrations.py`가 core_db·learning_db·report_db 생성(같은 이름 DB가 있으면 중단, 삭제·초기화하지 않음)
5. core·learning Flyway(이미지는 `compose.yaml`과 같은 버전인지 확인), report Alembic 적용
6. ERD·실제 스키마 대조, 합성 데이터 제약 위반 검사
7. 재실행 시 Flyway `migrationsExecuted=0`·이력 불변 확인
8. report `downgrade base` → `upgrade head` 왕복 후 재검증
9. 서비스별 계정 6개의 다른 DB 접속 거부, app 계정 DML 보유·DDL 거부·이력 테이블 접근 불가 확인(8절)

| 항목 | 검사 |
|---|---|
| 테이블·컬럼 | ERD의 이름·타입·varchar 길이·NULL·DEFAULT |
| PK·FK·개별 UNIQUE | PK 컬럼 순서, FK 컬럼 집합, UK 표시 컬럼 |
| CHECK 허용값 | ERD 주석의 `값1\|값2`·`CHECK[값]` 표기와 단일 컬럼 CHECK 집합 일치. 누락·추가·축소·`OR true` 우회·`NOT VALID` 거부 |
| ERD 6장 인덱스 | 테이블·키 순서·부분 조건·btree 유효성(이름 고정 안 함, 추가 인덱스 허용) |
| 잘못된 입력 | 합성 데이터의 예상 SQLSTATE 확인, 정상 대조 수용, 전부 ROLLBACK |

- 새 코드 목록은 Mermaid 컬럼 주석, 조회 인덱스는 ERD 6장에 명시. 일반 설명의 영어 단어를 코드값으로 추정하지 않음. 값이 하나면 `CHECK[REGISTER]`처럼 표기, 확장 가능한 `product.code` 예시는 닫힌 집합으로 읽지 않음
- FK 참조 대상 전체·복합 UNIQUE 전체·모든 업무 규칙을 대조하지는 않음

### 로컬 실행

비어 있는 별도 검증 DB만 사용. `PGPASSWORD`는 현재 셸에만 설정.

```powershell
$env:PGHOST = '127.0.0.1'; $env:PGPORT = '55432'; $env:PGUSER = 'schema_ci'
uv run --frozen --project backend/report-service python -O -m unittest discover -s scripts/tests -v
uv run --frozen --project backend/report-service python -O scripts/verify_db_schema.py --direct
uv run --frozen --project backend/report-service python -O scripts/check_db_migrations.py
```

- Windows Docker Desktop에서 Flyway 컨테이너가 DB에 붙어야 하면 `--docker-network YOUR_TEST_NETWORK --flyway-host postgres` 지정
- Compose 방식: `python scripts/verify_db_schema.py --project db-schema-check --db-user USER --env-file ../schema-check.env -f compose.yaml -f ../compose.schema-check.yaml`. override 파일은 `services: postgres: ports: !reset []`로 호스트 포트를 막고, env 파일에는 `POSTGRES_*`·`RABBITMQ_*`·`INTERNAL_TOKEN` 필요
- Windows CP949에서도 Alembic이 설정을 읽도록 `alembic.ini` 주석은 영문 유지

## 5. Spring Repository (core·learning)

`_common/persistence/PersistenceConfig`가 타입 핸들러를 한 번만 등록(core UUID는 `_common/config/UuidTypeHandler` 재사용, learning은 자체 핸들러). 서비스 간 공통 라이브러리는 만들지 않음.

| PostgreSQL | Kotlin | 기준 |
|---|---|---|
| `uuid` | `UUID` | 앱에서 생성 |
| `jsonb` | `JsonNode` | Spring `ObjectMapper` 사용 |
| `timestamptz` | `Instant`(기본)·`OffsetDateTime` | 비교는 `toInstant()`, 정밀도 마이크로초. `LocalDateTime` 금지 |
| SQL NULL | nullable | JSON `null`(`NullNode`)과 구분 |

- nullable JSON 파라미터는 `#{payload,javaType=com.fasterxml.jackson.databind.JsonNode,jdbcType=OTHER}`로 명시. 구조가 고정된 JSON DTO는 해당 타입에만 `JacksonJsonbTypeHandler` 등록(`Any`·`Map` 전역 등록 금지). Jackson 변환은 Infrastructure 안에서만
- 예시: core `account/repository/UserAccountRepository`·`UserAccountMapper.xml`. constructor resultMap으로 불변 객체, 모든 값은 `#{...}` 바인딩
- 트랜잭션은 Application service의 `@Transactional`에서만 시작하고 외부 HTTP·AMQP는 트랜잭션 밖. 고유키 위반은 `DuplicateKeyException`으로 전파해 서비스가 업무 오류로 변환
- 테스트: `PostgresRepositoryTest` 상속(Testcontainers PostgreSQL 17.11, 테스트 준비 코드가 Flyway 직접 실행, 테스트마다 롤백, Docker 없으면 실패). core는 RabbitMQ listener를 끄고 `OutboxRelay`를 대역으로 교체. 메시징까지 필요하면 `IntegrationTestSupport`(별도 DB). `@Commit`·`REQUIRES_NEW`는 롤백 경계를 벗어나므로 별도 DB 사용
- 앱 기동: `spring.flyway.enabled: false`, `spring.sql.init.mode: never`. Flyway는 `testImplementation`에만 두고 실제 환경은 Compose 일회성 컨테이너·K8s migration-job이 실행(`StartupWithoutMigrationTest`로 확인)

## 6. report SQLAlchemy

- `app/database.py`의 `create_db_engine()`·`create_session_factory(engine)`·`transaction(factory)`. 엔진은 프로세스 수명 동안 공유, API lifespan이 `app.state.session_factory` 제공

```python
with transaction(factory) as session:
    repository.save(session, record)
    outbox_repository.save(session, event)
# 정상 종료 시 함께 commit, 예외 시 함께 rollback 후 원래 예외 전파
```

- Repository는 전달받은 Session으로 SQL만 실행(자체 commit·새 Session 금지). Session은 작업별로 만들고 스레드·async task 간 공유 금지. 동기 엔진이므로 async 코드는 트랜잭션 작업 전체를 `asyncio.to_thread` 등 한 작업으로 넘김
- 테이블은 기능 `repository.py`의 SQLAlchemy Core `Table` 정의(`UUID(as_uuid=True)`·`JSONB`·`DateTime(timezone=True)`, timezone-aware 값만). Domain `models.py`에는 프레임워크 의존 없음
- 스키마 기준은 ERD와 수동 Alembic revision. `target_metadata = None` 유지, `--autogenerate` 금지(일부 테이블만 정의한 metadata가 나머지를 삭제 대상으로 오인), `metadata.create_all()`·기동 시 마이그레이션 금지
- pytest: `postgres` fixture가 임시 PostgreSQL, `db_engine`이 Alembic `upgrade head`. `db_session`·`db_session_factory`는 외부 트랜잭션 + SAVEPOINT로 롤백. 병렬 테스트는 기본 비활성

## 7. 테스트 전용 의존성

| 범위 | 의존성 | 이유 |
|---|---|---|
| Spring test | Testcontainers PostgreSQL·JUnit Jupiter(Spring Boot BOM) | 실제 DB와 컨테이너 수명 관리 |
| Spring test | Flyway core·PostgreSQL 13.11.1 | 테스트 DB 초기화, migration-job과 같은 버전 |
| report dev | testcontainers 4.15.0 | pytest PostgreSQL fixture |

새 production 의존성 없음. 테스트 데이터는 합성 값만 사용.

## 8. 서비스별 DB 계정 (#230)

2026-11-05 결정(#230). 아키텍처 1.1 "다른 서비스 DB 직접 접근 금지"를 DB 권한으로 강제.

### 8.1 배경과 결정

- 문제: 로컬 compose·kind의 앱·마이그레이션 전부가 슈퍼유저 `POSTGRES_USER` 1개를 공유 → core 계정으로 `learning_db`·`report_db` 접속·변경 가능
- 운영 RDS는 이미 DB별 migrate·app 계정 6개 사용 중(prod ESO `core-db-credentials`·`core-migrate-credentials` 등), 재현 SQL은 #185의 `rds-bootstrap*.sql`
- 결정
  - 인스턴스 1개 유지, 로컬도 운영과 같은 계정 6개 구성
  - `rds-bootstrap.sql`·`rds-bootstrap-db.sql`을 `infrastructure/aws/`에서 `infrastructure/gitops/charts/platform-data/files/postgres/`로 이동해 로컬 init과 `demo_stack.py rds-bootstrap`이 같은 파일 사용 (Helm `.Files`는 chart 밖 파일을 읽지 못함). 운영 실행 방식은 변화 없음
  - 서비스별 Testcontainers 테스트는 기존 계정 유지, 계정 격리 검증은 `ci-db-schema`에서 수행
- API 계약 변경 없음

### 8.2 계정 구성

| DB | migrate(DDL: Flyway·Alembic) | app(DML: 앱 런타임) |
|---|---|---|
| core_db | `core_migrate` | `core_app` |
| learning_db | `learning_migrate` | `learning_app` |
| report_db | `report_migrate` | `report_app` |

- 각 DB의 PUBLIC `CONNECT`·`TEMPORARY` 회수, 해당 DB의 두 계정만 접속 가능
- `public` schema 생성 권한은 migrate 계정만 보유. migrate 계정이 만든 테이블·sequence는 default privileges로 app 계정에 DML 부여
- migration 후 bootstrap 재실행 시 `flyway_schema_history`·`alembic_version`의 app 권한 회수 (운영 절차와 동일)
- 관리자 계정(`POSTGRES_USER`)은 컨테이너 초기화·관리 작업(e2e seed 포함) 전용, 앱·migration Secret에 미포함

### 8.3 설정 위치

| 대상 | 내용 |
|---|---|
| `files/postgres/init.sql` | `\ir bootstrap/rds-bootstrap.sql`만 실행. bootstrap 파일은 entrypoint가 단독 실행하지 않도록 `/docker-entrypoint-initdb.d/bootstrap/`에 배치 |
| `.env` | 비밀번호 6개 `CORE_MIGRATE_PASSWORD`·`CORE_APP_PASSWORD`·`LEARNING_*`·`REPORT_*`. 계정 이름은 고정이라 미포함. URL에 그대로 들어가므로 영문·숫자·`-`·`_`만 사용 |
| `compose.yaml` | postgres에 계정 env·bootstrap 마운트, core·learning 앱은 app 계정, `*-migrate`는 migrate 계정, report-migrate는 `report_migrate`·report-api/worker는 `report_app` URL |
| platform-data chart | `postgres.serviceRoles`(env 접두사 → 계정 이름), 비밀번호는 `existingSecret`의 `<접두사>_PASSWORD` 키 |
| `create-platform-secret.ps1` | `platform-data-credentials`에 비밀번호 6개 추가 |
| `create-app-secrets.ps1` | `app-service-credentials`에 `CORE_DB_*`·`CORE_MIGRATE_*`·`LEARNING_DB_*`·`LEARNING_MIGRATE_*`, `REPORT_DATABASE_URL`(report_app)·`REPORT_ALEMBIC_DATABASE_URL`(report_migrate). 기존 `DB_USERNAME`·`DB_PASSWORD` 키 제거 |
| `environments/local/*.yaml` | core·learning 앱 `*_DB_*`, Flyway `*_MIGRATE_*` 키 참조 |
| `infrastructure/stubs/e2e.env` | e2e 합성 비밀번호 6개 |

### 8.4 기존 로컬 환경 적용

`init.sql`은 빈 데이터 디렉터리에서 최초 1회만 실행. 기존 볼륨은 테이블이 관리자 소유라 migrate 계정이 이후 migration을 적용할 수 없으므로 **PostgreSQL 볼륨 재생성(로컬 DB 데이터 삭제)** 필요.

- Compose
  1. `.env`에 비밀번호 6개 추가
  2. `docker compose down` 후 `docker volume rm sagomungchi_postgres-data` (RabbitMQ 등 다른 볼륨 유지)
  3. `docker compose up --build`
- kind
  1. `.env`에 비밀번호 6개 추가
  2. 기존 Secret은 키가 달라 스크립트가 중단하므로 `platform/platform-data-credentials`·`app/app-service-credentials` 삭제 후 `create-platform-secret.ps1`·`create-app-secrets.ps1` 재실행
  3. `kubectl -n platform delete pvc data-postgres-0 --wait=false` 후 `kubectl -n platform delete pod postgres-0` → StatefulSet이 새 PVC로 초기화
  4. app namespace의 완료된 migration Job 삭제 후 Argo CD sync로 migration·앱 재기동
- 비밀번호 변경도 기존 계정에 반영되지 않음(bootstrap은 기존 계정 비밀번호 미변경). 같은 절차로 재생성하거나 관리자 계정으로 `ALTER ROLE ... PASSWORD` 수동 실행

### 8.5 운영 RDS

- 같은 계정 구성을 [`demo_stack.py rds-bootstrap`](../../infrastructure/aws/README.md)이 RDS 관리 master 계정으로 Job 실행해 생성 (#185 절차 유지, SQL 경로만 변경)
- ESO Secret 6개·`app/rds-ca` 준비 → bootstrap → migration → bootstrap 재실행 순서. 상세는 [prod README](../../infrastructure/gitops/environments/prod/README.md)
- 이번 작업에서 실제 RDS 실행 없음

### 8.6 검증

- `scripts/check_db_migrations.py`(ci-db-schema): bootstrap → migrate 계정으로 Flyway·Alembic 적용 → bootstrap 재실행 → 재실행·report 왕복 → 6개 계정의 다른 DB 접속 거부, app 계정의 DML 보유·DDL 거부·이력 테이블 접근 불가 확인
