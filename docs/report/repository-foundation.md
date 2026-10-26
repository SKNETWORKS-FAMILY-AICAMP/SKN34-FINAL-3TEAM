# 이슈 #14 Repository 공통 기반

[이슈 #14](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/14)의 공통 기반과 예시 구현이다. ERD·기존 마이그레이션은 변경하지 않는다. 기능별 Repository는 해당 기능 담당자가 추가한다.

## Spring: core·learning

두 서비스의 `_common/persistence`에 동일한 타입 변환과 설정을 둔다. 공통 라이브러리를 만들지 않는 기존 아키텍처를 따른다.

| PostgreSQL | Kotlin | 적용 기준 |
|---|---|---|
| `uuid` | `UUID` | 앱에서 생성. `UuidTypeHandler`가 JDBC의 UUID로 전달 |
| `jsonb` | `JsonNode` | Spring의 Jackson `ObjectMapper`를 사용. 중첩 객체·배열·한글을 변환 |
| `timestamptz` | `Instant` | 기본 선택. UTC `OffsetDateTime`을 거쳐 JDBC에 전달 |
| `timestamptz` | `OffsetDateTime` | MyBatis 기본 핸들러 사용. 비교 기준은 `toInstant()` |
| SQL NULL | nullable 값 | SQL NULL과 JSON `null`(`NullNode`)은 별개 |

PostgreSQL은 원래의 UTC 오프셋/시간대 이름을 보존하지 않는다. 시각의 동일성으로 비교하며, 저장 정밀도는 마이크로초다. `LocalDateTime`을 `timestamptz`에 사용하지 않는다. 기간 필드는 기존 설계대로 `LocalDate`/`date`를 사용한다.

`PersistenceConfig`가 타입별 핸들러를 등록하므로 Mapper마다 UUID·시각 변환을 반복하지 않는다. nullable JSON 파라미터는 `#{payload,javaType=com.fasterxml.jackson.databind.JsonNode,jdbcType=OTHER}`처럼 명시한다. 일반 `Any`/`Map`을 전역 JSON 핸들러로 등록하지 않는다.

구조가 고정된 JSON DTO는 `JacksonJsonbTypeHandler<MyPayload>(objectMapper, objectMapper.typeFactory.constructType(MyPayload::class.java))`를 생성해 해당 DTO 타입에만 등록한다. 컬렉션은 `constructCollectionType` 등으로 요소 타입까지 지정한다. JSON 노드/DB 행 변환은 Infrastructure 안에서 처리하고 Domain에 Jackson 의존성을 추가하지 않는다.

### 예시 Repository

core의 `account/domain/UserAccount.kt`, `account/repository/UserAccountRepository.kt`·`UserAccountMapper.kt`, `resources/mybatis/account/UserAccountMapper.xml`이 예시 1개다.

- `insert(account)`, `findById(id)`만 제공한다. 가입·로그인 API나 비밀번호 해싱 정책은 구현하지 않는다.
- XML constructor resultMap으로 불변 Kotlin 객체를 만들고, 모든 SQL 값은 `#{...}`로 바인딩한다.
- Application service의 `@Transactional` 안에서 Repository를 호출한다. Repository는 트랜잭션을 시작하지 않는다.
- 같은 트랜잭션에서 필요한 Repository들을 호출하고, 외부 HTTP·AMQP 호출은 트랜잭션 밖에서 수행한다.
- 고유키 위반은 Spring `DuplicateKeyException`으로 전파되며 기능 서비스가 업무 오류로 변환한다.
- 예시 객체에는 password hash가 있으므로 객체 전체를 로그나 API 응답에 출력하지 않는다.

### Repository 테스트

`src/test/.../_common/persistence/PostgresRepositoryTest`를 상속한다. Testcontainers가 PostgreSQL 17.11을 만들고 **테스트 준비 코드가 직접 Flyway를 실행한 다음** Spring 컨텍스트를 시작한다. 테스트 JVM에서 DB를 공유하며 각 테스트는 Spring 테스트 트랜잭션으로 롤백된다. 컨테이너는 Testcontainers의 Ryuk이 정리한다. Docker가 없으면 테스트를 생략하지 않고 실패한다.

```kotlin
class MyRepositoryTest : PostgresRepositoryTest() {
    // @Autowired Repository 주입 → 저장·조회·제약 검증
}
```

테스트에 `@Commit`/`REQUIRES_NEW`를 추가하면 기본 롤백 경계를 벗어날 수 있다. 커밋 자체를 검증해야 하는 테스트는 별도 컨테이너/DB와 정리 절차를 사용한다. 공통 타입 검사는 test 소스의 `TypeProbeMapper`와 트랜잭션 종료 시 사라지는 임시 테이블만 사용한다. learning의 업무용 Repository를 추가하지 않는다.

## report: SQLAlchemy

`app/database.py`에 `create_db_engine()`, `create_session_factory(engine)`, `transaction(factory)`를 둔다. 엔진은 `DATABASE_URL`을 읽고 프로세스 수명 동안 공유한다. `postgresql://`도 설치된 psycopg 3 드라이버로 연결한다. API lifespan에서 `app.state.session_factory`를 제공하고 종료 시 엔진을 정리한다. worker는 소비자 조립 시 같은 함수를 이용해 factory를 서비스에 주입하고 종료 시 `engine.dispose()`한다.

```python
# Application service: factory는 생성자 등으로 주입한다.
from app.database import transaction

with transaction(factory) as session:
    repository.save(session, record)
    outbox_repository.save(session, event)
# 정상 종료: 함께 commit. 예외: 함께 rollback 후 원래 예외 전파. 항상 Session close.
```

Repository는 전달받은 Session으로 SQL만 실행한다. 자체 commit/rollback이나 새 Session 생성은 하지 않는다. Session은 요청/작업별로 생성하고 다른 스레드·async task와 공유하지 않는다. 현재 엔진은 동기식이므로 async 처리에서는 **트랜잭션 작업 전체를** `asyncio.to_thread` 등 한 작업으로 넘기고 Session은 그 작업 안에서 생성한다. 외부 AI·HTTP·AMQP 대기는 트랜잭션 밖에서 처리한다.

### 테이블 정의와 마이그레이션

- SQLAlchemy Core의 명시적 `Table`·`Column` 정의를 기능의 `repository.py` 등 Infrastructure에 둔다. Domain의 `models.py`에는 프레임워크 의존성을 넣지 않는다.
- `UUID(as_uuid=True)`, `JSONB`, `DateTime(timezone=True)`를 사용한다. datetime은 timezone-aware 값만 전달한다.
- 사용 예시는 `tests/test_database.py`의 기존 `outbox_event` 테이블 조회 정의를 참고한다. 이 정의는 테스트용이며 업무 Repository를 추가한 것은 아니다.
- 전체 스키마의 기준은 ERD와 수동 작성한 Alembic revision이다. `target_metadata = None`을 유지하며 `--autogenerate`를 사용하지 않는다. 기능별로 일부 테이블만 정의한 metadata로 자동 생성하면 미정의 테이블을 삭제 대상으로 잘못 해석할 수 있다.
- `metadata.create_all()`이나 앱 시작 시 reflection/migration을 호출하지 않는다. 스키마 변경은 별도 마이그레이션 PR에서 다룬다.

### pytest fixture

`tests/conftest.py`의 `postgres`가 임시 PostgreSQL을 만들고 `db_engine`이 별도 Alembic CLI로 `upgrade head`를 실행한다. `db_session`은 단순 Repository 검사, `db_session_factory`는 트랜잭션 헬퍼 검사에 사용한다. 외부 트랜잭션 + SAVEPOINT로 서비스의 commit도 테스트 종료 시 롤백한다. 기본적으로 병렬 테스트를 켜지 않는다. 별도 연결에서 실제 commit 가시성을 검사할 때는 독립 DB와 정리 절차를 사용한다.

## 앱 기동과 실행 방법

- core·learning의 기본 설정: `spring.flyway.enabled: false`, `spring.sql.init.mode: never`.
- Flyway는 `testImplementation`에만 추가해 production runtime에 넣지 않는다. 실제 환경에서는 기존 compose 일회성 컨테이너/K8s migration-job이 실행한다.
- Spring의 `StartupWithoutMigrationTest`는 Flyway가 test classpath에 있는 상태에서 빈 PostgreSQL로 앱을 시작하고 테이블 0개·Flyway bean 없음으로 확인한다.
- report도 빈 별도 DB로 API lifespan을 실행해 테이블이 생기지 않고 세션이 동작하는지 확인한다.
- Windows Alembic이 설정 파일을 CP949로 읽는 문제를 피하도록 `alembic.ini`의 한글 주석 한 줄만 영문으로 변경했다. PR #15와 같은 변경이며 설정값은 그대로다.

Docker가 실행 중이어야 한다. Spring은 JDK 21, report는 기존 서비스별 `.venv`를 사용한다.

```powershell
cd backend/core-service
.\gradlew.bat test
cd ../learning-service
.\gradlew.bat test
cd ../report-service
uv sync --frozen
uv run pytest
```

Linux/CI에서는 각 Spring 서비스에서 `./gradlew test`를 실행한다. 기존 서비스 CI가 이 테스트들을 함께 실행하므로 별도 선택 옵션이 필요 없다.

## 추가 의존성

| 범위 | 의존성·버전 | 이유 |
|---|---|---|
| Spring test only | Testcontainers PostgreSQL·JUnit Jupiter **1.21.4** | 기존 Spring Boot 3.5.16 BOM 버전 사용, 실제 DB와 컨테이너 수명 관리 |
| Spring test only | Flyway core·PostgreSQL **13.11.1** | 테스트 DB 초기화, compose migration-job과 동일 버전 |
| report dev only | testcontainers **4.15.0** | pytest용 PostgreSQL fixture. 정확한 전이 의존성은 uv.lock에 고정 |

새 production 의존성은 없다. Jackson·MyBatis·SQLAlchemy·psycopg는 기존 의존성을 재사용한다. 테스트 데이터는 직접 만든 합성 값만 사용한다.

## 구현 검증 기록

- core: JDK 21에서 `./gradlew test bootJar --no-daemon` 통과. 9개 테스트(신규 5개), 실패·생략 0개.
- learning: 동일 환경에서 통과. 7개 테스트(신규 3개), 실패·생략 0개.
- report: `pytest` 12개(신규 7개) 및 Ruff lint/format 통과.
- 세 서비스의 UUID·JSONB·timestamptz 저장/조회와 빈 DB 앱 기동을 실제 PostgreSQL 17.11로 확인. Spring은 SQL NULL/JSON null 구분, report는 정상 commit·고유키 위반/업무 예외 rollback도 확인.
- core·learning 배포 JAR에 Flyway·Testcontainers·테스트 Mapper가 포함되지 않음을 확인.
- 로컬 Spring 검사는 PC의 Java 17 대신 공식 `eclipse-temurin:21-jdk` Docker 이미지에서 실행했다. 초기 Gradle 의존성 준비를 포함한 시간은 core 8분 53초, 캐시를 재사용한 learning 2분 39초다. #14에는 3분 제한이 없으며 #13 DB CI의 제한과 별개다.

## 정책 마이그레이션 반영 전 검증 기록

2026-10-26 `origin/develop`의 `fd4ee9c`를 작업 브랜치에 병합했다. 파일 충돌은 없었다. 이 develop에는 #13의 DB CI와 정책 확정 문서 변경(`fc90e35`)이 함께 들어 있다. 최신 ERD 7장에도 정책 변경이 기존 마이그레이션에는 미반영이라고 명시돼 있다.

병합 후 `--rerun-tasks`로 core 9개·learning 7개 테스트와 bootJar를 다시 실행해 통과했다. report pytest 12개·Ruff와 DB 검증기 자체 회귀 테스트 10개도 통과했다. 아래의 실제 DB-ERD 대조 실패는 남아 있으므로 전체 CI 성공으로 보고하지 않는다.

임시 PostgreSQL에 현재 마이그레이션을 적용한 뒤 최신 ERD와 대조하면 아래 불일치가 발생한다. `scripts/verify_db_schema.py`, ERD, Flyway SQL, Alembic revision은 develop과 동일하므로 #14의 Repository 코드에서 새로 만든 불일치가 아니다.

| 대상 | 최신 ERD | 현재 마이그레이션 |
|---|---|---|
| core `student` | `birth_year` 추가, `user_account_id` 제거 | 이전 컬럼 유지, 출생연도 없음 |
| core `product` | `limits` 추가, `price` NOT NULL, FREE/PREMIUM 기반 코드 | limits 없음, price NULL 허용, BASIC/PLUS CHECK |
| core `error_report.category` | NOT NULL 및 5개 신고 유형 | NULL 허용, 유형 CHECK 없음 |
| core `guardianship.method`·`notification_setting.channel` | REGISTER·IN_APP으로 제한 | LINK·EMAIL·PUSH도 허용 |
| learning `answer` | `speech_transcribed` 제거 | 이전 컬럼 유지 |
| learning `followup` | 질문 은행 테이블·FK 추가, source에서 TEMPLATE 제거 | 은행 테이블·FK 없음, TEMPLATE 허용 |
| report | 테이블·컬럼 변경 없음 | 컬럼·NULL 허용 기준 일치 |

당시 DB CI는 첫 불일치인 `core_db: table/column mismatch`에서 정상적으로 실패했다. 따라서 **#14의 서비스 테스트 통과와 전체 DB 스키마 CI 통과는 구분해야 한다.** 이슈 #14의 제약대로 위 변경은 별도 마이그레이션 PR로 처리하며, 검사를 생략하거나 예전 ERD로 되돌려 통과시키지 않는다.

## 이슈 #19와 결합한 사전 검증 — 3단계

2026-10-26 로컬 `feature/repository-schema-check`의 `7039dab`에서 Repository 구현 `4c7390a`와 #19 스키마·CI 변경 `16dc70f`를 합쳐 검증했다. 병합 충돌은 없었다. 이 검증용 브랜치는 원격에 올리지 않으며, #14 원본 브랜치에는 #19 마이그레이션을 미리 병합하지 않는다.

| 검증 | 결과 |
|---|---|
| core | JDK 21 `test bootJar --no-daemon --rerun-tasks` 통과. 9개 테스트, 실패·오류·생략 0개. 실제 Testcontainers DB에 V1~V7 적용 로그 확인 |
| learning | 같은 명령 통과. 7개 테스트, 실패·오류·생략 0개. 실제 Testcontainers DB에 V1~V5 적용 로그 확인 |
| report | pytest 12개, 실패·오류·생략 0개. CI와 같은 서비스 디렉터리에서 Ruff 검사·포맷 검사 통과 |
| DB CI | 세 DB 전체 적용·59개 테이블/506개 컬럼·41개 위반 입력·61개 코드 CHECK·19개 인덱스 검사, 재실행·report downgrade/upgrade 통과. 실행 스크립트 15.8초 |
| 검증기 | `python -O` 회귀 테스트 18개 통과 |
| 배포 JAR | core·learning 모두 Flyway·Testcontainers 라이브러리와 테스트 전용 Mapper 미포함 |

UUID·JSONB·timestamptz 왕복, SQL NULL/JSON null 구분, Repository 저장/조회·고유키 위반 전파, report commit/rollback·Session 분리, 세 서비스의 빈 DB 기동 시 자동 마이그레이션 미실행을 다시 확인했다. Spring 전체 실행 시간은 core 2분 48초, learning 2분 15초이며 #13 DB CI job의 3분 제한과는 별개다.

확인한 공통 기반과 예시 Repository에는 삭제된 학생 계정 연결·음성 입력 컬럼 참조가 없어 구현 코드를 바꿀 필요가 없었다. 아직 구현하지 않은 기능별 Repository까지 검증했다는 의미는 아니다.

다음 순서는 #19 별도 PR 검토·병합 → 최신 develop을 이 브랜치에 반영 → 충돌·변경 영향 재검증 → #14 새 PR이다. #14 코드와 테스트 의존성은 #19 PR에 포함하지 않는다.

참고: [pgJDBC의 시각 타입](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes), [MyBatis 타입 핸들러](https://mybatis.org/mybatis-3/configuration.html#typeHandlers), [SQLAlchemy 세션·트랜잭션](https://docs.sqlalchemy.org/en/20/orm/session_basics.html), [Testcontainers PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/).
