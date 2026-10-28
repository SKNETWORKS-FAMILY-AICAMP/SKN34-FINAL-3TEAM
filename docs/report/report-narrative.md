# 이슈 #52 서술 요청·검증

작업 브랜치는 `feature/report-narrative`다. develop `47e5ffe`와 #50 공통 v1 메시지 연결(`1a80824`)·기존 #51 계산 구현을 병합했다. API 4.2.1에 report 측 응답 형태를 `{narrative:{text,source,modelExplanation},eveningQuestion,citedQuotes[],versions}`로 명시했다. 실제 ai 서버 구현·연동을 확인한 계약으로 보고하지 않는다.

## 구현

- `clients/ai_client.py`: 기존 내부 HTTP 클라이언트를 이용한 서술 요청. 응답을 검증하며 재시도나 API 장애 시 템플릿 대체를 하지 않는다.
- `clients/learning_client.py`: answer ID·attempt ID·version 대조 및 50건 단위 evidence 조회. 410/명시적 삭제 표식은 이용 불가로 처리하고 원문을 반환하지 않는다. 누락·다른 버전·예상하지 않은 답변은 거부한다.
- `generation/verifier.py`: 계산 결과의 숫자 부분집합, 명시된 인용의 원문 부분문자열·식별/버전 대조. 저녁 질문도 검사하며 근거 없는 따옴표 인용·지원하지 않는 한글 수사·과학적 표기·수치 레벨/등급/사고력 향상 단정을 검증 통과로 간주하지 않는다. 문장의 의미와 수치 간 인과관계까지 증명하는 검증기는 아니다.
- `generation/narrative_generator.py`: 무료/NO_RECORD 시 AI 생략. 알려진 닉네임을 본문에서 가리고 이름·학생 식별 필드를 요청에 넣지 않는다. 이름 가림을 위한 신뢰할 수 있는 표시 이름 조회 경로는 별도 연결해야 한다. 확정된 `report.generate.v1`의 여섯 payload 필드에는 닉네임이 없으며, 공유 메시지에 임의로 추가하지 않는다.
- `GenerationResult`와 Repository: narrative·verification·versions·evening_question을 항목·근거·완료 이벤트와 같은 트랜잭션에 저장한다.

## 확정 기준

2026-10-27 사용자(#52 담당자)가 **AI 시간 초과·5xx는 FAILED, 대조 실패만 템플릿 전환**을 선택했다. 스키마 오류·원문 조회 실패도 정상 결과나 빈 기록으로 바꾸지 않는다. 템플릿은 계산된 제출 시도 건수와 기록 확인 안내만 제공하며 검증 실패한 저녁 질문을 저장하지 않는다.

`verification`은 AI 응답 검사의 `numbersMatched`, `quotesMatched`, `contentAllowed`를 보존한다. 개별 item의 verified는 계산 항목 또는 실제 source와 대조된 인용의 근거 확인 상태다. 삭제 evidence의 인용 후보는 text를 null로 바꾼다.

## 검증 및 남은 작업

2026-10-28 최신 기반 병합 후 report 전체 **141개 통과(34.71초)**, Ruff check/format 통과. 기존 5xx뿐 아니라 AI 시간 초과도 실제 PostgreSQL의 FAILED 상태로 저장되는 회귀 사례를 추가했다. 공유 v1 codec·실제 RabbitMQ worker 회귀도 포함하며, ai와 learning 응답은 계약 대역이다. API 4.2의 `/internal/versions` 행이 서술 응답 절 뒤로 밀려 있던 표 배치도 복구했다.

2026-10-27 `tests/test_narrative.py` **23개 통과(6.12초)**. 정상·숫자/인용/버전 불일치·미신고 인용·금지 표현·무료/NO_RECORD·AI 5xx·닉네임 가림·410·evidence 누락·실제 PostgreSQL narrative 저장/FAILED 처리를 포함한다. Ruff 검사도 통과했다. 다른 이슈 구현 후 전체 회귀 결과는 통합 보고서에 별도로 기록한다.

필요한 외부 작업: #64의 ai 서술 API·prompt/model 버전 연결, #27의 evidence 원문·버전·삭제 표식 응답 연결, core 담당자와 신뢰할 수 있는 표시 이름 조회 경로 확정이다. #42 메시지 규격은 이미 확정·병합되었으므로 재확정 대상이 아니다. 실제 ai/core/learning E2E는 아직 검증하지 않았다.
