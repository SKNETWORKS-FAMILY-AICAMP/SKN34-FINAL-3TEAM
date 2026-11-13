# 리텐션 지표 집계 (NFR-OPS-06, #628)

화면 이벤트 없이 DB 집계만으로 P27 리텐션 지표 6개를 낸다. 지표 정의는 [결정 기록 3.6](../../docs/report/retention-expansion.md#36-운영), kind 대조 결과는 같은 문서 15장.

운영자가 psql로 직접 돌리는 읽기 전용 SQL이다. 서비스 코드·스케줄러·저장 테이블은 없고, 두 파일 모두 `BEGIN TRANSACTION READ ONLY`로 감싸 데이터를 바꾸지 않는다.

## 절차

core_db와 learning_db는 서비스별 DB라 직접 조인하지 않는다. 1단계가 core 쪽 대상·값을 JSON 한 줄로 내고, 2단계가 그 JSON을 psql 변수로 받아 learning 행과 맞춘다.

| 단계 | 파일 | 접속 | 하는 일 |
|---|---|---|---|
| 1 | `core.sql` | core_db, core 앱 계정 | 대상 학생 확정(제외 기준 아래), 지금 걸린 액자 슬롯·가구 스킨 해금·추억 검색 사용량 집계 → JSON |
| 2 | `learning.sql` | learning_db, learning 앱 계정 | JSON의 대상 학생으로 `theme_frame`·`attempt`를 집계하고 슬롯과 회차 키로 맞춰 지표 6개 출력 |

```bash
psql -X -At -d core_db -v from=2026-11-09 -v to=2026-11-23 -f scripts/retention_metrics/core.sql > core-result.json
```

```bash
psql -X -d learning_db -v core="$(cat core-result.json)" -f scripts/retention_metrics/learning.sql
```

`core-result.json`에는 대상 학생 ID(UUID)와 슬롯 회차 키가 들어 있다(이름·닉네임·계정·답변 없음). 저장소·로그에 남기지 말고 집계가 끝나면 지운다.

kind에서는 `platform/postgres-0`에 `kubectl exec -i … psql -U <POSTGRES_USER> -d <DB> -f -`로 파일을 표준 입력으로 넘기고, `PGOPTIONS="-c default_transaction_read_only=on"`을 함께 줘 세션 전체를 읽기 전용으로 둔다.

## 변수 (1단계)

| 변수 | 필수 | 뜻 |
|---|---|---|
| `from`, `to` | 예 | KST 날짜 구간 `[from, to)`. 회차 주(`theme_week_start`)·해금 시각(KST)·검색 사용 날짜에 같은 구간을 쓴다. 주 단위로 보려면 월요일로 준다 |
| `as_of` | 아니오 | 기준일(KST). 기본은 실행 시점 KST 오늘. 기준일이 속한 주가 "진행 주"(앨범·추억의 벽에 안 보이는 액자)이고, 다음 주 참여 판정도 이 날을 기준으로 한다 |
| `include_demo` | 아니오 | `1`이면 시연 학생(`student.is_demo = true`)도 포함. 기본 `0`(제외) |
| `exclude_students` | 아니오 | `is_demo` 표식이 없는 시험 학생 ID를 쉼표로 이어 추가 제외 |

2단계는 1단계 JSON의 기간·기준일·대상을 그대로 쓴다. 필수 변수가 없으면 안내를 출력하고 아무 쿼리도 실행하지 않는다.

## 대상 학생

- core `student.status = 'ACTIVE'`(삭제 요청 중·삭제 확정 제외)
- 시연 학생 제외: `student.is_demo = true`(AWS 시연 DB는 #185 `mark-confirmed-demo-data.sql`로 표시). 표식이 없는 시험 계정은 `exclude_students`로 뺀다
- 출력 첫 표에 대상 수와 제외 사유별 수(시연·목록·비활성)를 함께 낸다

## 지표

| # | 지표 | 분자 | 분모 | 출처 |
|---|---|---|---|---|
| 1 | 액자 전시율 | 지금 추억의 벽에 걸린 액자 | 대상 학생의 보유 액자(기간 안 회차, 진행 주 제외) | core `room_frame_slot` + learning `theme_frame` |
| 2 | 액자 확인율 | `seen_at`이 있는 액자 | 보유 액자 중 소급분(`seen_at = awarded_at`) 제외 | learning `theme_frame` |
| 3 | 전시까지 걸린 기간 | `saved_at − awarded_at`(시간) 중앙값·평균·최소·최대 | 걸린 액자 건수(소급분 제외) | core `room_frame_slot` + learning `theme_frame` |
| 4 | 가구 스킨 해금 수 | 원장 `UNLOCK` 중 사건 키가 가구 슬롯(`DESK`·`WALL`·`WARDROBE`) 아이템인 행 | 대상 학생 수(참고) | core `reward_point_ledger`·`look_item` |
| 5 | 추억 검색 이용 수 | 사용량 `SEARCH` 행(장애로 되돌린 요청은 행이 지워져 빠짐), 참고로 `EXPLANATION`도 표시 | 대상 학생 수(참고) | core `memory_daily_usage` |
| 6 | 액자 보유 학생의 다음 주 테마 참여 | 다음 주(`theme_week_start + 7`)에 테마 시도(`THEME_DAY`·`THEME_REVIEW`, 진행 중 포함)가 있는 회차 | 다음 주가 기준일 전에 끝난 액자 회차. 안 끝난 회차는 "보류"로 따로 셈 | learning `theme_frame`·`attempt` |

- 1·3은 "지금" 걸린 슬롯 기준이다. 슬롯 변경 이력이 없어 기간 중 걸었다가 내린 액자는 셀 수 없다. 계속 걸린 액자는 슬롯을 옮겨도 처음 건 시각을 유지하고, 내렸다 다시 걸면 다시 건 시각이 된다(결정 기록 10.3)
- 1의 메모 "걸린 슬롯 중 대상 액자와 맞지 않는 행"은 core 슬롯 중 learning 액자를 찾지 못한 수다. 보통 0이고, 0이 아니면 진행 주 회차가 걸렸거나 두 DB가 어긋난 것이라 원본을 확인한다
- 결과는 기술 통계일 뿐이며 기능의 인과·학습 효과를 주장하지 않는다(NFR-OPS-06)

## 한계

- 대상 학생 ID를 psql 변수로 넘기므로 학생 수만큼 명령줄이 길어진다. 데모 규모(수십 명)를 전제로 하며, 수천 명 단위가 되면 학생 목록을 파일로 넘기는 방식으로 바꾼다
- 2단계 결과를 다시 저장하지 않는다. 결과서에 옮길 때 첫 표(기간·기준일·대상·제외 수)를 함께 적는다
