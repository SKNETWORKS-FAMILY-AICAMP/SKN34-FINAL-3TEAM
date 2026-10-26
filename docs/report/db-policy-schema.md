# 이슈 #19 확정 정책에 따른 DB 스키마 수정

작성일: 2026-10-26. 기준: `develop`의 `fd4ee9c` 및 [이슈 #19](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/19), [기능 명세 P01~P16](../design/functional-spec.md), [ERD](../design/erd.md).

확정된 설계에 맞춘 **마이그레이션 추가·Docker 검증(1단계)**, **#13 CI 검증기 수정·로컬 전체 실행(2단계)**, **#14 Repository와 결합한 재검증(3단계)**을 완료했다. 기존 이슈 #5 마이그레이션의 내용은 유지한다. #19 스키마·CI 변경부터 별도 PR로 검토받고, 병합 후 #14 작업을 최신 develop에 반영한다. PR 검토·병합 전에는 이슈 전체를 완료 처리하지 않는다.

## 변경 대상과 이유

| DB·대상 | 적용 내용 | 이유·유지하는 내용 |
|---|---|---|
| core `student` | `birth_year integer NOT NULL` 추가, `user_account_id` 제거, `grade BETWEEN 3 AND 6` CHECK | P01의 보호자 중심 자녀 등록과 P03의 초3~6 범위 반영. 학생 ID와 학습 기록의 논리 참조는 유지 |
| core `guardianship.method` | `REGISTER`만 허용 | P02에서 기존 계정 연결 방식 제외. 보호자·학생 FK와 활성 연결의 중복 방지는 유지 |
| core `notification_setting.channel` | `IN_APP`만 허용 | P10의 서비스 내 알림 정책 반영. 알림 종류와 사용자별 설정 구조는 유지 |
| core `error_report.category` | NOT NULL 및 `WRONG_JUDGMENT`, `ODD_QUESTION`, `MISMATCH`, `INAPPROPRIATE`, `OTHER` CHECK | 확정된 신고 유형 다섯 가지를 저장 단계에서 보장 |
| core `product` | `limits jsonb NOT NULL` 추가, `price` NOT NULL, 기존 `BASIC/PLUS` 고정 코드 CHECK 제거 | P13의 데이터 기반 상품·한도 관리와 추가 요금제 지원. `code` UK, 기존 상품 ID·코드·금액 및 구독 참조 유지 |
| learning `answer` | `speech_transcribed` 제거 | P03에서 음성 입력 제외. 답변 내용·버전·보호자 대필 여부는 유지 |
| learning `followup_bank_question` | `id`, `type`, `question`, `active`, `created_at` 신설 | P16의 되묻기 생성 재실패 시 질문은행 선택 근거 저장. 질문 내용은 마이그레이션에 넣지 않음 |
| learning `followup` | `bank_question_id` FK 추가, `source`를 `LLM/LLM_RETRY/BANK`로 제한. BANK일 때만 질문은행 ID 필수 | 실제 질문은행 출처를 추적하고 TEMPLATE 출처 제외. 생성 당시 `question` 원문은 유지 |
| report | DDL 변경 없음 | 최신 ERD와 기존 Alembic 구조가 일치하므로 불필요한 revision을 추가하지 않음 |

이슈 #5의 기존 FK 삭제 동작은 NO ACTION을 유지한다. 자녀 최대 3명, 되묻기 최대 2회, 질문은행의 type 일치·활성 여부, 학생 메모 노출 제한 등은 서비스 검증 대상이다. 이번에 새 트리거나 서비스 간 FK를 추가하지 않는다.

## 상품 코드 해석과 남은 설계 확인

P13은 요금제 추가 및 가격·한도 변경 시 새 상품 행을 요구한다. 따라서 ERD의 `FREE|PREMIUM 등`은 닫힌 enum이 아니라 초기 상품 코드 예시로 해석하고, ERD 주석에도 이를 명시했다. `code`의 UNIQUE는 유지하므로 새 행은 새 고유 코드를 사용한다. `FREE`, `PREMIUM`, `PREMIUM_V2` 저장과 중복 코드 거부를 검증했다.

기존 `BASIC/PLUS` 상품을 `FREE/PREMIUM`으로 임의 변환하거나 금액을 변경하지 않는다. 신규 상품의 가격·한도·활성 상태와 질문은행 내용은 별도 데이터 관리 대상이며 이번 SQL은 시드를 설치하지 않는다.

**무료 상품을 새 버전으로 교체할 때의 조회 계약은 확인이 필요하다.** ERD 3.4의 `product(code = FREE)` 조회만으로는 새 고유 코드의 무료 상품을 선택할 수 없다. 무료 상품 버전 선택 또는 상품군 구분 방식은 상품 기능 구현 전에 확정해야 한다. 이번에는 미정인 상품군·버전 컬럼을 임의로 추가하지 않았다.

## 마이그레이션 적용 방식

| 서비스 | 준비 버전 | 확정 버전 |
|---|---|---|
| core | V6: 출생연도·상품 한도 nullable 추가, 고정 상품 코드 CHECK 제거 | V7: 기존 값 검사 후 NOT NULL·CHECK 적용, 학생 계정 연결 컬럼 제거 |
| learning | V4: 질문은행과 nullable FK 추가 | V5: 기존 값 검사 후 출처 CHECK·조건부 FK 필수 규칙 적용, 음성 여부 컬럼 제거 |
| report | 기존 `20261026_01` 유지 | 신규 revision 없음 |

빈 DB에는 모든 버전을 순서대로 적용하면 된다. 기존 데이터가 있는 DB에는 아래 순서를 사용한다.

1. 기존 DB를 백업하고 기존 서비스의 쓰기를 중지한다. 컬럼 제거와 새 NOT NULL 조건 때문에 이전 애플리케이션과 동시에 사용하는 배포 방식은 피한다.
2. core는 Flyway `-target=6 migrate`, learning은 `-target=4 migrate`로 준비 버전까지만 적용한다. 각 명령의 접속 대상·자격 증명·migration 경로는 해당 DB에 맞춰 설정한다.
3. 아래 사전 점검으로 보완 대상 건수를 확인한다. 출생연도는 확인된 등록 정보, 상품 한도·금액은 승인된 상품 조건으로 채운다. 값이 확인되지 않으면 적용을 멈추고 확인한다.
4. 삭제 예정인 계정 연결·음성 이력과 폐기되는 코드 값은 보존 필요성을 검토하고 승인된 전환 방법을 정한다. BANK 이력은 실제 출처 질문을 확인해 연결한다. 자동으로 OTHER나 LLM으로 바꾸거나 가상의 출생연도를 넣지 않는다.
5. 점검 결과가 모두 0건이면 `-target`을 제거한 `migrate`로 core V7·learning V5까지 적용한다. 호환되는 애플리케이션을 배포하고 서비스 검증을 수행한다.

V7/V5는 검사부터 DDL까지 같은 트랜잭션에서 실행하며, 변경 테이블에 잠금을 잡아 검사와 변경 사이의 쓰기를 막는다. 검사 실패 시 해당 최종 버전은 롤백되고 앞서 성공한 준비 버전은 남는다. 이 단계에서는 새 필드가 nullable이고 이전 컬럼이 남아 있으므로 필요한 보완 후 재시도할 수 있다. 중단을 피하려고 운영 DB를 초기화하거나 마이그레이션 이력을 임의 수정하지 않는다. Flyway의 마이그레이션별 트랜잭션 동작은 [공식 문서](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/migration-transaction-handling)를 따른다.

이번 검증에서 실제 서비스 DB에 접속하거나 적용하지 않았다. 아래 조회는 **준비 버전 적용 후** 해당 DB에서 실행한다.

```sql
-- core V6 이후: 행 내용 대신 보완 대상 건수만 조회
SELECT 'student.birth_year' AS item, count(*) AS pending
FROM student WHERE birth_year IS NULL
UNION ALL
SELECT 'student.user_account_id', count(*) FROM student WHERE user_account_id IS NOT NULL
UNION ALL
SELECT 'student.grade', count(*) FROM student WHERE grade NOT BETWEEN 3 AND 6
UNION ALL
SELECT 'product.price/limits', count(*) FROM product WHERE price IS NULL OR limits IS NULL
UNION ALL
SELECT 'guardianship.method', count(*) FROM guardianship WHERE method <> 'REGISTER'
UNION ALL
SELECT 'notification_setting.channel', count(*) FROM notification_setting WHERE channel <> 'IN_APP'
UNION ALL
SELECT 'error_report.category', count(*) FROM error_report
WHERE category IS NULL OR category NOT IN
    ('WRONG_JUDGMENT', 'ODD_QUESTION', 'MISMATCH', 'INAPPROPRIATE', 'OTHER');
```

```sql
-- learning V4 이후
SELECT 'answer.speech_transcribed' AS item, count(*) AS pending
FROM answer WHERE speech_transcribed
UNION ALL
SELECT 'followup.TEMPLATE', count(*) FROM followup WHERE source = 'TEMPLATE'
UNION ALL
SELECT 'followup.bank_question_id', count(*) FROM followup
WHERE (source = 'BANK' AND bank_question_id IS NULL)
   OR (source <> 'BANK' AND bank_question_id IS NOT NULL);
```

## 1단계 스키마 검증 결과

PostgreSQL `17.11-alpine`, Flyway `13.11.1-alpine`을 사용하는 별도 임시 컨테이너에서 확인했다. 테스트 값은 직접 만든 합성 데이터이며 AI Hub 자료·실제 학생 답변을 포함하지 않는다.

| 확인 항목 | 결과 |
|---|---|
| 빈 DB 전체 적용 | core V1~V7, learning V1~V5 통과. 모든 업무 테이블이 비어 있어 시드 없음 확인 |
| 재실행 | 신규 설치·기존 DB 업그레이드 후 모두 `migrationsExecuted=0`, 적용 이력 불변 |
| 기존 데이터 사전 검사 | core 9건, learning 4건의 부적합 상황에서 적용 거부. 검사 전후 데이터·마이그레이션 이력 동일 |
| 값 보완 후 업그레이드 | 학생 ID·프로필, 기존 상품 값, 답변 내용·제출 시각, 되묻기 내용·연결 보존 확인 |
| 새 제약 | 위반 입력 18건 거부. 학년 경계 3·6, 신고 5유형, 되묻기 3출처, 정상 BANK FK, 추가 상품 코드 수용 |
| ERD 메타데이터 대조 | 59개 테이블·506개 컬럼의 이름·타입·NULL·DEFAULT, PK·FK 컬럼·개별 UK, 61개 코드 CHECK, 19개 명시 인덱스 확인. 새 BANK FK의 참조 대상과 NO ACTION 확인 |
| report | 기존 Alembic 적용 후 6개 테이블·44개 컬럼의 ERD 일치 확인. 이번 단계에서 report downgrade/upgrade 전체 CI 사이클은 실행하지 않음 |

최종 테이블/컬럼 수는 core **34/306**, learning **19/156**, report **6/44**이다. 모든 업무 규칙이나 모든 FK 참조 대상을 자동으로 대조했다는 뜻은 아니다.

### 업그레이드 검사 재현

[`scripts/check_policy_migrations.py`](../../scripts/check_policy_migrations.py)는 별도 PostgreSQL 서버에 `policy_empty_core`, `policy_empty_learning`, `policy_upgrade_core`, `policy_upgrade_learning` 네 DB를 생성한다. 같은 이름의 DB가 하나라도 있으면 중단하고 삭제·초기화하지 않는다. 이 스크립트는 새 마이그레이션의 적용·데이터 보존·제약을 검사하며, 위의 전체 ERD 메타데이터 대조나 기존 CI 전체 실행을 대신하지 않는다.

기존 [별도 검증 환경 구성 방법](db-schema-validation.md#재현-방법)을 참고하되, 업무 DB와 분리된 새 PostgreSQL 컨테이너를 준비한다. Windows에서는 Docker CLI를 PATH에 두고, PostgreSQL 컨테이너가 연결된 네트워크와 호스트명을 전달한다. 네트워크 내부 PostgreSQL 포트는 5432를 사용한다.

```powershell
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '55413'  # 테스트 컨테이너의 호스트 바인딩 포트
$env:PGUSER = 'schema_ci'
# PGPASSWORD는 해당 임시 검증 DB의 값으로 현재 셸에 설정한다.
uv run --frozen --project backend/report-service python -O scripts/check_policy_migrations.py --docker-network YOUR_TEST_NETWORK --flyway-host postgres
```

검사가 끝나면 해당 검증용 Compose 프로젝트/컨테이너만 정리한다. 기존 업무 DB나 다른 프로젝트의 컨테이너를 삭제하지 않는다.

## 3단계 Repository 영향 검증

로컬 `feature/repository-schema-check`의 `7039dab`에서 #14 구현 `4c7390a`와 #19 스키마·CI 변경 `16dc70f`를 결합했다. 충돌 없이 병합됐으며, 이 검증용 브랜치의 Repository 구현과 의존성은 #19 PR에 포함하지 않는다.

| 검증 대상 | 결과 |
|---|---|
| core | JDK 21에서 `test bootJar --no-daemon --rerun-tasks`, 9개 테스트 통과. 실제 Testcontainers DB에 V1~V7 적용 확인 |
| learning | 같은 명령, 7개 테스트 통과. 실제 Testcontainers DB에 V1~V5 적용 확인 |
| report | pytest 12개 통과. 서비스 디렉터리에서 Ruff 검사·포맷 검사 통과 |
| DB CI | 결합 상태에서 전체 적용·ERD 대조·41개 위반 입력·재실행·report 왕복 통과, 실행 스크립트 15.8초. 검증기 회귀 18개도 통과 |
| 배포 JAR | core·learning에 Flyway·Testcontainers와 테스트 Mapper가 포함되지 않음 |

세 서비스 총 28개 테스트 모두 실패·오류·생략 0개다. UUID·JSONB·시각 값 왕복, Repository 저장/조회·예외 전파, report 트랜잭션, 빈 DB 앱 기동 시 자동 마이그레이션 미실행을 확인했다. Spring 실행은 core 2분 48초, learning 2분 15초이며 DB CI job 제한과 별개다.

공통 기반과 예시 Repository에는 삭제된 컬럼 참조가 없어 기능 코드 수정은 필요하지 않았다. 아직 구현되지 않은 학생·상품·되묻기 기능별 Repository까지 검증했다는 뜻은 아니다. #14의 상세 가이드에는 동일 검증 결과를 로컬로 기록했으며, #19 병합 후 다시 최신 develop을 반영한다.

## 검토 및 후속 순서

1. **#13 CI — 2단계 로컬 완료**: 학생·답변 fixture를 최신 구조로 바꾸고, 단일 허용값 CHECK를 ERD의 `CHECK[REGISTER]`·`CHECK[IN_APP]` 표기와 대조하도록 보강했다. 검증기 회귀 18개, 제약 위반 41건, 코드 CHECK 61개, 인덱스 19개 및 마이그레이션 재실행·report 왕복 검증을 통과했다. 전체 실행 스크립트 12.4초. 일부러 넣은 오류 8건을 거부하고 복구 후 Compose 방식도 통과했다. [CI 보고서](db-schema-ci.md)에 범위와 근거를 정리했다.
2. **#14 Repository — 3단계 사전 검증 완료**: 위 결합 브랜치에서 28개 서비스 테스트와 전체 DB CI를 통과했다. #14 원본에는 스키마를 미리 병합하지 않고 검증 결과 문서만 로컬에 기록했다.
3. **#19 PR 검토 우선**: `feature/db-policy-schema` → `develop` PR에 스키마·CI 변경과 이 보고서를 올리고, GitHub Actions 결과와 상품 코드 해석·기존 데이터 전환 절차를 검토받는다. #19 병합 후 #14 브랜치에 최신 develop을 반영·재검증하고 별도 PR을 준비한다.
