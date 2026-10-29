# DB 스키마 결정 (#5·#19)

통합 원본: db-schema-validation, db-policy-schema(V6 마이그레이션 주석이 참조하는 구 `db-policy-schema.md` 내용 포함), erd-change-targets-step1(#19로 대체된 변경 대상 분류표, 커밋 이력 참고)

설계 원본은 [ERD](../design/erd.md), 현재 버전·수치는 ERD 8장.

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
| core `student` | `birth_year` NOT NULL, `user_account_id` 제거, 학년 3~6 CHECK | P01 보호자 중심 등록, P03 초3~6 |
| core `guardianship.method` | `REGISTER`만 | P02 기존 계정 연결 제외 |
| core `notification_setting.channel` | `IN_APP`만 | P10 |
| core `error_report.category` | NOT NULL, 5유형 CHECK | 신고 유형 확정 |
| core `product` | `limits` NOT NULL, `price` NOT NULL, 고정 코드 CHECK 제거 | P13 데이터 기반 상품·한도 |
| learning `answer` | `speech_transcribed` 제거 | P03 음성 제외 |
| learning `followup_bank_question`·`followup.bank_question_id` | 질문은행 신설, source는 LLM·LLM_RETRY·BANK, BANK일 때만 ID 필수 | P16 재실패 시 질문은행 출처 추적 |

- 상품 코드: ERD의 `FREE|PREMIUM 등`은 닫힌 enum이 아니라 초기 예시. `code` UK 유지, 새 상품 행은 새 고유 코드. 기존 `BASIC/PLUS`를 임의 변환하지 않음
- 미정: 무료 상품을 새 버전으로 교체할 때 `code = FREE` 조회로는 선택 불가. 상품 기능 구현 전에 버전·상품군 선택 방식 확정 필요
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
