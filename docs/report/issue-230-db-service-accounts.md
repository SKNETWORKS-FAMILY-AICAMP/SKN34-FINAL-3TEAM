# 서비스별 PostgreSQL 계정 분리 (#230)

기준: 2026-11-05. 아키텍처 1.1 "다른 서비스 DB 직접 접근 금지"를 DB 권한으로 강제.

## 1. 배경과 결정

- 문제: 로컬 compose·kind의 앱·마이그레이션 전부가 슈퍼유저 `POSTGRES_USER` 1개를 공유 → core 계정으로 `learning_db`·`report_db` 접속·변경 가능
- 운영 RDS는 이미 DB별 migrate·app 계정 6개 사용 중(prod ESO `core-db-credentials`·`core-migrate-credentials` 등), 재현 SQL은 #185의 `rds-bootstrap*.sql`
- 결정
  - 인스턴스 1개 유지, 로컬도 운영과 같은 계정 6개 구성
  - `rds-bootstrap.sql`·`rds-bootstrap-db.sql`을 `infrastructure/aws/`에서 `infrastructure/gitops/charts/platform-data/files/postgres/`로 이동해 로컬 init과 `demo_stack.py rds-bootstrap`이 같은 파일 사용 (Helm `.Files`는 chart 밖 파일을 읽지 못함). 운영 실행 방식은 변화 없음
  - 서비스별 Testcontainers 테스트는 기존 계정 유지, 계정 격리 검증은 `ci-db-schema`에서 수행
- API 계약 변경 없음

## 2. 계정 구성

| DB | migrate(DDL: Flyway·Alembic) | app(DML: 앱 런타임) |
|---|---|---|
| core_db | `core_migrate` | `core_app` |
| learning_db | `learning_migrate` | `learning_app` |
| report_db | `report_migrate` | `report_app` |

- 각 DB의 PUBLIC `CONNECT`·`TEMPORARY` 회수, 해당 DB의 두 계정만 접속 가능
- `public` schema 생성 권한은 migrate 계정만 보유. migrate 계정이 만든 테이블·sequence는 default privileges로 app 계정에 DML 부여
- migration 후 bootstrap 재실행 시 `flyway_schema_history`·`alembic_version`의 app 권한 회수 (운영 절차와 동일)
- 관리자 계정(`POSTGRES_USER`)은 컨테이너 초기화·관리 작업(e2e seed 포함) 전용, 앱·migration Secret에 미포함

## 3. 설정 위치

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

## 4. 기존 로컬 환경 적용

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

## 5. 운영 RDS

- 같은 계정 구성을 [`demo_stack.py rds-bootstrap`](../../infrastructure/aws/README.md)이 RDS 관리 master 계정으로 Job 실행해 생성 (#185 절차 유지, SQL 경로만 변경)
- ESO Secret 6개·`app/rds-ca` 준비 → bootstrap → migration → bootstrap 재실행 순서. 상세는 [prod README](../../infrastructure/gitops/environments/prod/README.md)
- 이번 작업에서 실제 RDS 실행 없음

## 6. 검증

- `scripts/check_db_migrations.py`(ci-db-schema): bootstrap → migrate 계정으로 Flyway·Alembic 적용 → bootstrap 재실행 → 재실행·report 왕복 → 6개 계정의 다른 DB 접속 거부, app 계정의 DML 보유·DDL 거부·이력 테이블 접근 불가 확인
