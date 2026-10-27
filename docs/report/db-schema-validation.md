# 이슈 #5 DB 스키마 구현·검증

기준: develop `5fbdebf25e53fdaefaae3f3d2ae26b1a5b3c22ad`, [이슈 #5](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/5), 2026-10-26.
구현 브랜치: `feature/db-schema`. 설계 원본은 [erd.md](../design/erd.md)다.

작업 중 추가된 develop `5fc1ab092defc97c85b2ddd98674961f8dfe9302`도 반영했다. 아키텍처 폴더 구조·클래스 문서 정리이며 ERD·API·DDL 계약의 변경은 없다.

## 구현 결과

| DB | 업무 테이블 / 컬럼 | 마이그레이션 | 범위 |
|---|---|---|---|
| core_db | 34 / 305 | Flyway V1-V5 | 계정·학생·동의, 대화·리포트 작업, 알림·지원, 결제·구독, 운영·이벤트 |
| learning_db | 18 / 151 | Flyway V1-V3 | 미션·기준표 버전, 학습·답변·판정, 이벤트 소비·삭제 표식 |
| report_db | 6 / 44 | Alembic 20261026_01 | 리포트·항목·근거·파일, 이벤트 발행·소비 |

합계 58개 테이블·500개 컬럼이며 Flyway/Alembic 이력 테이블은 제외한다. ORM 모델·Repository·Mapper·서비스 로직·시드 데이터는 추가하지 않았다. 기존 Compose의 일회성 마이그레이션 서비스와 report의 `target_metadata = None`을 유지한다.

## ERD에 반영한 기술 결정과 이유

| 변경 | 이유·적용 경계 |
|---|---|
| UUID는 애플리케이션 생성, DB DEFAULT 없음 | API·이벤트에 사용한 ID를 DB에도 그대로 전달한다. 시간·상태·카운터 역시 앱에서 전달하며 임의 정책값을 DEFAULT로 고정하지 않는다. |
| 모든 컬럼의 NULL 허용 여부 명시 | 처리 전 결과·완료 시각, 최초 답변의 이전 답변, 최초 결제의 구독 연결 등을 빈 값으로 저장할 수 있어야 한다. 기존 문서의 생략을 해소했다. |
| 같은 DB의 `conversation_message.scope_student_id`, `idempotency_record.user_id` FK 명시 | 각각 student, user_account의 존재를 검사한다. 다른 서비스 DB의 식별자는 논리 참조로 유지한다. |
| FK 삭제·갱신 NO ACTION | 미확정 P09를 CASCADE로 대신 결정하지 않는다. 순환 참조 세 곳만 명시적 트랜잭션에서 지연 검사할 수 있다. |
| 상태·종류 CHECK와 기존 복합/부분 UNIQUE 구현 | API·ERD의 허용 값 및 중복 방지 규칙을 DB에서 검사한다. 응답 전용 NOT_STARTED·SAVED·PROCESSING을 새 DB 상태로 넣지 않는다. |
| 판정 결과는 DONE일 때만 존재, HELD와 사유 동시 존재 | 상태 다이어그램의 처리 상태와 판정 결과를 구분한다. `IS NOT DISTINCT FROM`으로 NULL일 때 CHECK가 우회되지 않게 한다. |
| `judgment_element`의 verified·satisfied NOT NULL 및 CHECK | 검증되지 않은 근거를 충족으로 저장하는 것을 막고 NULL 우회도 방지한다. |
| 리포트 state는 COMPLETED일 때만 존재 | 실패와 기록 없음·표본 부족을 구분한다. 기록 없음도 정상 완료 결과다. |
| report 미발행 outbox 인덱스 추가 | 기존 리포트 이벤트 릴레이의 미발행 조회에 대응한다. 소비자·릴레이 실행 코드는 별도다. |
| 버전 보존·삭제 설명 정정 | 처리 중 상태 갱신은 허용한다. 근거 ID만 보관해도 대화 본문·리포트 파일에 남는 파생 내용의 삭제가 자동 보장되지는 않는다. |

같은 미션·학습 시도·기준표에 속하는지의 다중 참조 검증은 현재 서비스 계약으로 남긴다. 단일 FK는 대상의 존재만 보장한다. 추가 복합 FK, 승인 범위, 메모 저장, 파생 데이터 삭제 등은 [변경 대상 검토표](erd-change-targets-step1.md)의 확인·후속 항목이다.

## 검증 결과

최종 수정본은 별도 Compose 프로젝트 `sg-issue5-final-check`의 신규 볼륨에서 검증했다. 호스트 DB 포트를 노출하지 않았고, 기존 개발 DB는 사용하지 않았다.

| 검증 | 결과 |
|---|---|
| 빈 DB 적용 | core V1-V5, learning V1-V3, report 20261026_01 성공 |
| 실제 스키마와 ERD 대조 | 58개 테이블·500개 컬럼의 이름·타입·NULL·DEFAULT, PK·FK 컬럼·개별 UNIQUE 일치 |
| 제약 위반 입력 | core 7건, learning 10건, report 5건, 합계 22건을 예상 SQLSTATE로 거부 |
| 정상 입력 | 각 검증의 정상 값 및 이력 중복 허용 사례 수용. 서비스 간 논리 ID에 물리 FK를 만들지 않은 점 확인 |
| 검증 데이터 | 직접 만든 합성 값만 트랜잭션에 삽입하고 전부 ROLLBACK. 업무 테이블이 비어 있지 않으면 검증 스크립트 중단 |
| 마이그레이션 재실행 | core·learning 추가 적용 없음, report head 유지 |
| report 코드 검사 | `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .` 통과 |

제약 검증은 잘못된 상태·필수 값 누락·FK 고아 참조·중복 키·부분 UNIQUE·판정 결과/사유·미검증 충족 금지·리포트 완료 상태를 다룬다. 서비스 전체 기능 테스트나 모든 업무 규칙의 구현을 뜻하지 않는다.

## 재현 방법

저장소 루트에서 `.env.example`을 참고해 로컬 전용 환경 파일을 준비한다. 비밀번호나 토큰을 커밋하지 않는다. Compose 프로젝트 이름과 볼륨은 기존 개발 환경과 분리한다.

호스트 포트 충돌을 피하려면 저장소 밖에 아래 내용의 `compose.schema-check.yaml`을 만든다. `!reset`을 지원하는 Docker Compose가 필요하다(검증 환경 v5.5.1).

```yaml
services:
  postgres:
    ports: !reset []
```

PowerShell 예시다. 두 경로와 DB 사용자명은 준비한 로컬 값으로 바꾼다. `schema-check.env`는 기본 `compose.yaml`이 요구하는 `POSTGRES_USER`·`POSTGRES_PASSWORD`·`RABBITMQ_USER`·`RABBITMQ_PASSWORD`·`INTERNAL_TOKEN`을 채워야 한다. MinIO 선택 파일을 사용하지 않으므로 MinIO 계정은 필요하지 않다.

```powershell
$checkEnv = '../schema-check.env'
$checkOverride = '../compose.schema-check.yaml'
$composeArgs = @('--env-file', $checkEnv, '-f', 'compose.yaml', '-f', $checkOverride, '-p', 'db-schema-check')
docker compose @composeArgs up -d postgres
docker compose @composeArgs run --rm core-migrate
docker compose @composeArgs run --rm learning-migrate
docker compose @composeArgs run --rm --build report-migrate
python scripts/verify_db_schema.py --project db-schema-check --db-user YOUR_DB_USER --env-file $checkEnv -f compose.yaml -f $checkOverride
```

동일한 `run --rm ...-migrate` 세 명령을 다시 실행하면 추가 적용 없이 종료되어야 한다. report 작업 디렉터리에서 프로젝트의 `uv run ruff check .`와 `uv run ruff format --check .`도 실행한다. 이미 공유 환경에 적용한 마이그레이션은 수정하지 말고 새 버전을 추가한다.

## 데이터 관리

AI Hub 원본 ZIP, 압축 해제본, 전처리 결과와 실제 답안 샘플은 GitHub에 올리지 않는다. 저장소 밖이나 무시되는 `local_data/`에 보관한다. `.gitignore`는 받은 데이터셋 이름 및 `aihub/`, `ai_hub/`, `local_data/`를 제외한다. 이름을 바꾼 데이터까지 자동 판별하는 규칙은 아니므로 커밋 대상 파일을 명시적으로 확인한다. 검증 스크립트의 예제 값은 AI Hub에서 가져온 데이터가 아니다.
