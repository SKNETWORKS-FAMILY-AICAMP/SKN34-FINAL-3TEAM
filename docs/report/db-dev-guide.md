# DB 개발 가이드 (#13·#14)

통합 원본: db-schema-ci, repository-foundation

스키마 결정은 [DB 스키마](db-schema.md), 설계 원본은 [ERD](../design/erd.md).

## 1. 마이그레이션 CI (`ci-db-schema.yml`)

마이그레이션·ERD·검증 스크립트·`scripts/tests`·관련 설정이 바뀐 PR에서만 실행(보고서만 바꾼 PR 제외). PR별 이전 실행 취소, 제한 3분.

1. PostgreSQL 17.11 서비스 컨테이너(CI 전용 임시 계정, Secrets 불필요)
2. report-service `uv.lock`으로 Python 3.12·마이그레이션 의존성 준비
3. `python -O`로 검증기 회귀 테스트
4. `scripts/check_db_migrations.py`가 core_db·learning_db·report_db 생성(같은 이름 DB가 있으면 중단, 삭제·초기화하지 않음)
5. core·learning Flyway(이미지는 `compose.yaml`과 같은 버전인지 확인), report Alembic 적용
6. ERD·실제 스키마 대조, 합성 데이터 제약 위반 검사
7. 재실행 시 Flyway `migrationsExecuted=0`·이력 불변 확인
8. report `downgrade base` → `upgrade head` 왕복 후 재검증

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

## 2. Spring Repository (core·learning)

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

## 3. report SQLAlchemy

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

## 4. 테스트 전용 의존성

| 범위 | 의존성 | 이유 |
|---|---|---|
| Spring test | Testcontainers PostgreSQL·JUnit Jupiter(Spring Boot BOM) | 실제 DB와 컨테이너 수명 관리 |
| Spring test | Flyway core·PostgreSQL 13.11.1 | 테스트 DB 초기화, migration-job과 같은 버전 |
| report dev | testcontainers 4.15.0 | pytest PostgreSQL fixture |

새 production 의존성 없음. 테스트 데이터는 합성 값만 사용.
