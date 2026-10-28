# 이슈 #51 학습 기록 조회·수치 계산 검토

## 목적과 기준

학습 기록을 P06·P08에 따라 집계해 리포트 항목과 원문 근거를 저장한다. 작업 브랜치는 `feature/report-metrics`이며, 검증 완료한 #50 `8ae3caf`와 develop `1208ead`를 반영했다. #27은 PR #105로 병합됐으므로 이전의 “learning 응답 확인 대기”는 해소됐다.

`docs/design/api-spec.md` 4.1.1과 실제 learning 코드·OpenAPI를 대조해 내부 식별자 `studentId`, 학생 작성 칸 기준 수치, nullable `followup`을 반영했다. API 문서 충돌은 #27의 공통 기록 조회 계약을 보존하고 report 수신 규칙을 이어 적는 방식으로 해결했다. 새 테이블·migration·운영 의존성은 없다.

## 해야 할 일·완료 조건 대조

테스트 경로는 `backend/report-service/tests/` 기준이다.

| 구분 | 요구사항 | 구현·검증 근거 | 결과 |
|---|---|---|---|
| 할 일 1 | thinking-types·attempts·changes 호출, HTTP 재시도 없음 | `LearningClient`, `test_learning_client.py`: 101건 전체 페이지·공통 내부 헤더·범위·응답 오류·재시도 없음 | 충족 |
| 할 일 2 | 기간 내 제출 시도 포함, 실패만 있는 시도·삭제 제외, 포함 기준 저장 | `MetricsCalculator._eligible`, `test_failed_only_and_no_submission_are_excluded_but_pending_included`, 실제 DB의 inclusion_rule 저장 | 충족 |
| 할 일 3 | Metric의 분자·분모·계산식·기간·sourceType, 분모 5 미만 value null | `test_sample_boundary_and_ratio`: 0·1·4·5·6건 경계 | 충족 |
| 할 일 4 | 최초 답변 전 도움 열람 기준 비율 | `test_help_is_compared_to_first_submission_not_any_help`, 조회 시작일 이전 도움 포함 | 충족 |
| 할 일 5 | 최초·종료일 이전 마지막 답변의 글자·문장·연결어 수 | `test_text_rules_are_literal_and_include_spaces`, `test_counts_use_written_fields_but_evidence_keeps_full_display_text`: 6종 입력·Unicode·공백·구분자·연결어 | 충족 |
| 할 일 6 | 다섯 생각 유형과 기록 없는 유형 NO_RECORD | `test_all_five_thinking_types_and_unverified_quote_candidates` | 충족 |
| 할 일 7 | 미작성 돌아보기 written:false, 대신 작성 금지 | `test_completed_count_uses_as_of_end_and_reflections_are_not_invented`, null·생략·기간 밖·텍스트 없는 작성 기록 구분 | 충족 |
| 할 일 8 | OK·NO_RECORD·INSUFFICIENT_SAMPLE | 0건·1~4건·5건 이상 경계 및 DB 저장 검사 | 충족 |
| 할 일 9 | 5종 item과 evidence 저장 | `test_fixed_learning_responses_store_all_item_types_and_evidence`, seq·답변 ID/버전·중복 방지 | 충족 |
| 완료 1 | P08 단위 테스트 | 분모 경계·문장 분리·고정 연결어·KST 경계·최초/마지막 답변 검사 | 충족 |
| 완료 2 | 고정 learning 응답의 item·evidence 저장 | MockTransport + 실제 PostgreSQL, FK 오류 시 상태·항목·근거·Outbox 동시 롤백 | 충족 |
| 완료 3 | 기록 없음 COMPLETED + NO_RECORD, LLM 미호출 | `test_no_record_is_completed_with_no_ai_request`: learning GET만 호출됨을 검사 | 충족 |
| 완료 4 | Ruff check·format·pytest | 아래 전체 실행 통과 | 충족 |

## 확정된 계산·입력 규칙

- 연결어는 사용자가 승인한 `왜냐하면`, `때문`, `그래서`, `따라서` 네 개이며 `generation/metrics.py:REASON_CONNECTIVES`에서 관리한다. 각 문자열의 비중첩 등장 횟수를 합한다.
- 표본 상태는 API 1.5·#27 계약에 따라 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`, 5건 이상 `OK`다. 비율 분모 5 미만은 value null, count에 분자를 보존한다.
- KST 날짜 양 끝을 포함한다. 시작일 이전 최초 답변·도움도 전달받고 종료일 뒤 답변·완료·돌아보기는 과거 주 집계에 포함하지 않는다. PENDING/RUNNING을 FAILED로 취급하지 않는다.
- `answers[].text`는 원문 표시·근거용 전체 평문이다. 수치는 `content`의 학생 작성 칸만 세며 풀이·논술 칸 이름과 선택지 이름을 세지 않는다. 서술 text, 풀이 steps 후 finalAnswer, 논술 claim·reasons·rebuttal을 비어 있지 않은 칸 순서대로 LF로 연결한다. 고르기·순서·분류의 작성 글은 빈 문자열이다.
- 글자 수는 공백·줄바꿈을 포함한 Unicode 코드포인트 수다. 문장은 `.`, `?`, `!`, LF로 나눈 비어 있지 않은 덩어리 수로 learning `TextCounts`와 같다. 독립 CR은 구분자로 추가하지 않는다.
- `reflection:null` 또는 생략은 미작성이다. 기간 안에 난이도를 선택하고 텍스트를 쓰지 않은 기록은 written:true, text:null이다. 저장 난이도는 EASY/NORMAL/HARD이며 화면 표시 변환은 #53·#54에서 처리한다.
- #27은 삭제된 attempts 표식을 제공하지 않고 NO_RECORD·빈 목록을 반환한다. 수신부는 이를 처리하며, 선택적 available:false 항목도 집계에서 제외한다. `followup:null`은 질문을 만들어 넣지 않고 보존한다.
- 메모·초안·추가 필드는 정규화 결과에서 제외한다. 잘못된 식별자·버전·기간·페이지·필수 내용은 빈 기록이나 정상 리포트로 바꾸지 않는다.

## 검증 결과 — 2026-10-28

- `uv run --locked ruff check .`: 통과.
- `uv run --locked ruff format --check .`: 54개 파일 통과.
- `uv run --locked pytest -q`: **150 passed**, 실패·생략 없음(53.01초). 실제 PostgreSQL·RabbitMQ를 사용하며 기존 #14·#50 회귀를 포함한다.
- root 계약 검사 54개, 변경 Markdown의 UTF-8·충돌 표식·로컬 링크 검사와 `git diff --check`도 통과했다.
- 기존 Starlette TestClient deprecation warning 1개는 테스트 실패가 아니다.
- #27의 실제 서비스 연동은 앞서 누적 브랜치 `708a242`에서 합성 데이터로 확인한 이력이 있다. 이번 #51 실행은 그중 수신·계산 수정만 이 이슈 브랜치로 옮긴 뒤 수행한 전체 회귀이며, 새 core 스케줄·AI·렌더링 E2E 실행으로 표현하지 않는다.

## 다음 단계

#50 PR #101을 먼저 반영해야 한다. #51은 학습 기록 조회·계산·저장 단계이며 #52 AI 서술과 #53 파일 렌더링을 조립하는 기반이다. 실제 worker 전체 생성기 조립과 core 상품 권한·표시 이름 공급은 후속 연동 범위다. 앞 단계 PR이 수정되면 이 브랜치에도 반영하고 재검증한다.
