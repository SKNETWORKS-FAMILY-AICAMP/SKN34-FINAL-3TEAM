# 이슈 #13 DB 마이그레이션 CI

[이슈 #13](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/13)의 검증 자동화 구현이다. 테이블·컬럼·업무 제약은 변경하지 않는다. 설계 기준은 [ERD](../design/erd.md), 기존 검증은 [이슈 #5 보고서](db-schema-validation.md)를 따른다.

## 실행 대상과 순서

`.github/workflows/ci-db-schema.yml`은 PR에서 마이그레이션, ERD, 검증 스크립트·테스트 또는 실행에 필요한 설정이 바뀔 때 실행한다. 문서 보고서만 변경한 PR에서는 실행하지 않는다. PR별 이전 실행은 취소하며, 작업 제한 시간은 3분이다.

1. PostgreSQL 17.11 서비스 컨테이너를 시작한다. 계정·비밀번호는 해당 CI 컨테이너에서만 사용하는 임시 값이며 Secrets를 요구하지 않는다.
2. report-service의 기존 `uv.lock`으로 Python 3.12와 마이그레이션 의존성을 준비한다. 신규 의존성은 추가하지 않는다.
3. `python -O`로 검증기 회귀 테스트를 실행한다.
4. `scripts/check_db_migrations.py`가 core_db·learning_db·report_db를 생성한다. 같은 이름의 DB가 이미 있으면 중단하며 기존 DB를 삭제하거나 초기화하지 않는다.
5. core·learning Flyway와 report Alembic을 적용한다. Flyway 이미지는 `compose.yaml`의 두 서비스에서 읽고 버전 일치도 확인한다. 현재 `flyway/flyway:13.11.1-alpine`이다.
6. ERD·실제 스키마 대조와 합성 데이터 제약 검사를 실행한다.
7. 마이그레이션을 재실행한다. Flyway의 `migrationsExecuted=0`과 세 DB의 마이그레이션 이력 불변을 확인한다.
8. report를 `alembic downgrade base`로 되돌린 뒤 업무 테이블·적용 리비전이 남지 않았는지 확인한다. 다시 `upgrade head`하고 스키마·제약·최종 리비전을 재검증한다.

## 검증 범위

| 항목 | 검사 방식 |
|---|---|
| 테이블·컬럼 | ERD의 이름·타입·varchar 길이·NULL·DEFAULT와 대조 |
| PK·FK·개별 UNIQUE | PK 컬럼 순서, FK 컬럼 집합, UK 표시 컬럼의 개별 UNIQUE 확인 |
| CHECK 허용값 | ERD의 `값1\|값2` 코드 목록과 PostgreSQL의 실제 단일 컬럼 CHECK 허용값 대조. 누락·추가·축소·미검증 제약을 거부 |
| 공통 코드 | ERD에 명시된 answer.input_type, notification_setting.type, correction.target_type의 공유 코드 목록도 검사 |
| ERD 6장 인덱스 | 대상 테이블·키 컬럼 순서·부분 조건·사용 가능한 btree 여부 확인. 이름은 고정하지 않으며 추가 인덱스는 허용 |
| 잘못된 입력 | 기존 합성 데이터 22건의 예상 SQLSTATE 확인, 정상 대조 사례 수용, 전부 ROLLBACK |
| 검증기 자체 | CHECK 누락·허용값 변경·우회 표현, 인덱스 누락·순서·조건·유효성, 빈 명세, `python -O`에서도 실패하는지 회귀 검사 |

일반적인 모든 SQL CHECK 표현을 해석하는 도구는 아니다. 현재 마이그레이션의 `IN (...)`이 PostgreSQL에서 정규화된 `= ANY(ARRAY[...])` 형태를 검사한다. 해석할 수 없는 형식은 성공으로 넘기지 않고 실패한다. 새 코드 목록은 Mermaid 컬럼 주석에, 조회 인덱스는 ERD 6장에 명시한다.

FK 참조 대상 전체·복합 UNIQUE 전체·모든 업무 규칙을 완전히 대조한다는 뜻은 아니다. 이번 추가 범위는 CHECK 허용값과 ERD 6장 인덱스이며, 기존 검증 경계는 유지한다. 검증 데이터는 직접 만든 값이고 AI Hub 원본·가공본·실제 답안을 포함하지 않는다.

## 로컬 실행

기존 Compose 실행 방식은 그대로 지원한다. 반드시 비어 있는 별도 검증 DB를 사용한다. 환경 파일·Compose override 준비는 [기존 재현 방법](db-schema-validation.md#재현-방법)을 따른다.

```powershell
python scripts/verify_db_schema.py --project db-schema-check --db-user YOUR_DB_USER --env-file ../schema-check.env -f compose.yaml -f ../compose.schema-check.yaml
```

직접 접속할 때는 기존 report-service 가상환경의 psycopg를 사용한다. `PGPASSWORD`는 현재 셸에 설정하고 파일이나 커밋에 남기지 않는다. 아래 호스트·포트·사용자명은 검증 DB 값으로 바꾼다.

```powershell
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '55413'
$env:PGUSER = 'schema_ci'
# PGPASSWORD는 해당 검증 DB의 비밀번호를 현재 셸에 설정
uv run --frozen --project backend/report-service python -O scripts/verify_db_schema.py --direct
uv run --frozen --project backend/report-service python -O -m unittest discover -s scripts/tests -v
```

전체 CI 과정을 로컬에서 재현할 때는 업무 DB가 아직 없는 별도 PostgreSQL 서버가 필요하다. Linux에서는 기본 host 네트워크를 사용한다. Windows Docker Desktop에서는 PostgreSQL 컨테이너가 연결된 네트워크와 서비스명을 명시한다.

```powershell
uv run --frozen --project backend/report-service python -O scripts/check_db_migrations.py --docker-network YOUR_TEST_NETWORK --flyway-host postgres
```

Windows의 기본 CP949 설정에서도 Alembic CLI가 설정 파일을 읽도록 `alembic.ini`의 한글 주석 한 줄을 영문으로 바꿨다. 설정값과 마이그레이션 동작은 동일하다.

## 검증 기록

- 별도 PostgreSQL 17.11에서 빈 DB 적용, 재실행, report downgrade/upgrade 및 전체 재검증 통과.
- 58개 테이블·500개 컬럼, 22개 위반 입력, 60개 CHECK 코드 집합, 19개 인덱스 확인.
- 기존 Compose CLI 방식 통과. `python -O`에서도 추가 컬럼·CHECK 허용값 변경·인덱스 누락을 각각 거부했고 검증 DB는 원상 복구했다.
- 검증기 회귀 테스트 10개와 Ruff 검사·포맷 검사 통과.
- 로컬 전체 실행 스크립트 12.1초. GitHub의 정상 워크플로는 초기 준비·정리를 포함해 35초(단일 job 32초), 마이그레이션 스크립트는 13.8초로 3분 기준을 충족했다.

| GitHub PR 검증 | 기대 결과 | 확인 근거 |
|---|---|---|
| 정상 구현 `5efc535` | 통과 | [정상 실행](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/40277008014) |
| 검증용 V6의 SQL 문법 오류 `b1b7277` | 실패 | [Flyway SQLSTATE 42601 감지](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/40277020140) |
| 검증용 V6의 ERD에 없는 컬럼 `60ec06c` | 실패 | [user_account.ci_failure_probe 불일치 감지](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/40277220829) |

오류 사례는 [검증용 Draft PR #16](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/16)에서 확인했다. 검증용 V6는 구현 브랜치에 포함하지 않으며, 검증용 PR은 병합 없이 닫는다.
