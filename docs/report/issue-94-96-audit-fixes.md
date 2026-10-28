# #94·#95·#96 감사 후속 코드 정리

근거: `docs/report/docs-consistency-audit.md` 3.2~3.4 (PR #92)

## 1. #94 LLM 사용량 비용 null 처리

- `LlmUsageService.cost()`가 토큰 null을 0으로 계산하던 것을 수정했다. 단가 미등록 모델과 같이 입력·출력 토큰 중 하나라도 null이면 `cost_usd`를 null로 저장한다.
- 한쪽 토큰만 기록된 경우도 null로 본다. 부분 계산값은 DB에서 완전한 비용과 구분되지 않기 때문이다 (사용자 결정).
- api-spec 4.6의 기존 규칙(null 비용 → 합계 null, `unpricedCalls` 공개)과 같아 API 계약 변경은 없다. 저장 기준만 바뀌며 과거 행은 변경하지 않는다.

## 2. #95 SPEECH 호출 종류 제거

음성 시범 미구현(P03)에 따라 `SPEECH`를 제거했다.

| 위치 | 변경 |
|---|---|
| `contracts/events/llm.usage.recorded.v1.schema.json` | `callType` enum에서 제거 |
| `backend/ai-service/app/messaging/publisher.py` | `CallType`에서 제거 |
| `backend/ai-service/app/speech/` | 빈 패키지 삭제 |
| core `usage/domain/UsageSummary.kt` | `CallType` enum에서 제거 |
| `contracts/openapi/core-service.yaml` | `CallType` enum에서 제거 |
| `docs/design/api-spec.md` 4.6 | 7개 → 6개 호출 종류 |

### API 변경

- `GET /api/v1/admin/ai-usage?callType=SPEECH`는 이제 다른 미지원 값과 같이 400 `VALIDATION_FAILED`다.
- `llm.usage.recorded.v1` 이벤트의 `callType` enum이 6개로 줄었다. `SPEECH`를 발행하는 서비스는 없었다.
- 프론트 관리자 callType 선택지에는 원래 `SPEECH`가 없어 변경하지 않았다.

### 남은 작업 (#99)

- core `V5` `ck_llm_usage_call_type` CHECK와 `docs/design/erd.md` `llm_usage.call_type` 목록에는 `SPEECH`가 남아 있다. DB가 더 넓게 허용하는 상태라 동작 문제는 없다.
- 기존 행 확인과 마이그레이션 버전 순서(`feature/core-account-management`의 V9) 조정이 필요해 #99로 분리했다.

## 3. #96 P12 주석 정리

- P12·architecture 1.3에서 정한 내부 HTTP 응답 시간은 learning→ai 35초, core→learning 일반 30초·피드백 80초, core→ai 분석 대화 20초·120초다.
- 주석을 정리한 4곳은 서비스 공통 내부 호출 기본값이다. P12 목록에 없고 정해진 값과도 충돌하지 않는다.
  - core `app.internal.read-timeout`: `InternalRestClientFactory` 기본값이다. learning 호출은 `app.learning.read-timeout`(30초)·피드백 80초를 별도로 지정한다.
  - ai·report·scoring `http_read_timeout`: `app/clients/base.py` `internal_client` 기본값이며 현재 호출처가 없다.
- 따라서 값은 30초로 유지하고 `[P12] 확정 전 임시값` 주석만 `내부 호출 기본값 (P12 목록 밖)`으로 바꿨다.

## 4. 검증

| 대상 | 결과 |
|---|---|
| core | `eclipse-temurin:21-jdk` Docker + Testcontainers에서 `bash gradlew test --no-daemon --max-workers=2`: 25개 클래스 125개 통과, 실패·오류·생략 0, BUILD SUCCESSFUL |
| ai | `uv run ruff check .`·`ruff format --check .`·`pytest`: 133 통과 |
| report | ruff·`pytest`: 17 통과 |
| scoring | ruff·`pytest`: 5 통과 |
| `scripts/tests` | `python -O -m unittest discover -s scripts/tests`: 46 통과 (OpenAPI `CallType` = 이벤트 스키마 enum 검사 포함) |
| `git grep SPEECH` | core V5·ERD·감사 리포트에만 남음 (#99 범위) |
