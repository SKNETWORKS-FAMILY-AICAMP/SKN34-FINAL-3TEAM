# 분석 대화 에이전트 (ai-service, LangGraph)

작업 브랜치는 `feature/ai-langgraph`(develop `1208ead`까지 반영, #105 learning 기록 조회 포함)다. `POST /internal/analysis/stream`(API 3.3·4.2)을 LangGraph 그래프로 구현했다.

## 구조

```
START → classify ─(범위 불명확·충돌)→ END [clarification]
              └→ retrieve ─(조회 실패)→ END [error]
                        └→ compute ─(기록 부족)→ insufficient → END
                                   ├(수학 점검·기록 밖 질문)→ unsupported → END
                                   ├(LLM 장애)→ fallback → END
                                   └→ answer ─(LLM 장애)→ fallback → END
                                             └→ check ─(대조 실패)→ fallback → END
                                                      └(통과)→ END [result: LLM]
```

| 파일 | 역할 |
|---|---|
| `analysis_agent/graph.py` | 노드·조건 분기 조립 (`build_graph`) |
| `analysis_agent/state.py` | 그래프 상태, 실행 컨텍스트(LLM·기록 도구·마감) |
| `analysis_agent/nodes/` | understand(분류·범위 확인), retrieve(기록 조회·계산), respond(답변·대조·템플릿) |
| `analysis_agent/records.py` | learning `/internal/records/...` 도구(요약·유형·최근 시도·전후 변화·생각 활동). 호출마다 권한 재확인, 학생·기간·상태 대조, 질문 하나에 연결 하나 |
| `analysis_agent/metrics.py` | 질문 유형별 수치·원문 고르기. learning이 계산한 값을 그대로 씀 |
| `analysis_agent/verification.py` | 답변 숫자·인용·금지 표현 대조 |
| `analysis_agent/templates.py` | 규칙 응답·기록 부족·미제공 질문 안내 문장 |
| `analysis_agent/prompts.py` | 분류·답변 프롬프트 `analysis@1`, LLM 출력 형식 |
| `analysis_agent/router.py` | SSE 변환 (`astream(stream_mode=["custom","values"])`) |

## 결정

- **LLM 호출은 기존 `LlmClient`를 그대로 사용한다.** 재시도·사용량 이벤트(`callType: ANALYSIS`)·Anthropic 대체 모델·sLLM JSON 모드가 이미 여기에 있다. LangChain 채팅 모델 래퍼로 바꾸면 이 처리들이 빠지므로 바꾸지 않았다. LangGraph는 흐름(분기·상태·스트리밍)만 맡는다.
- **도구 선택은 질문 유형 → 도구 표로 정한다.** 유형이 6가지로 정해져 있어 LLM 도구 선택보다 싸고 예측 가능하다. 도구는 학생·기간을 LLM에게 받지 않고 core가 확인한 `scope`만 쓴다.

  | 질문 유형 | 조회 |
  |---|---|
  | 모든 유형 | `summary` (집계 대상 시도 수 `학습한 활동` 포함) |
  | 유형별 활동 | + `thinking-types` |
  | 아이가 쓴 생각 | + `attempts` 첫 페이지 8건(최근 답변 순) |
  | 전후 변화 | + `changes` 전체 페이지(비율 분모), `thinking-activities`(근거의 미션 제목) |
  | 돌아보기 | + `thinking-activities` (기간 안 돌아보기) |
- **수치를 다시 계산하지 않는다.** 집계 대상·기간·건수·비율은 learning이 P08로 계산한 값(`summary`, `changes.counts`)을 그대로 쓴다. 대시보드·리포트와 숫자가 어긋나지 않게 하기 위해서다. 특히 전후 변화 글자 수는 learning이 학생이 쓴 칸만 센다. ai가 하는 계산은 learning 값을 세는 것뿐이고(유형별 시도 수, 글자 수·문장 수·까닭을 잇는 말이 늘어난 시도, 난이도별 돌아보기), 규칙은 learning `Metric.count`·`Metric.ratio`와 같다.
- **권한(FN-AGT-02):** 질문마다 스트림 시작 전에 확인(403)하고, 도구 실행마다 다시 확인한다. 권한 밖이면 learning을 호출하지 않는다.
- **범위(FN-AGT-03):** 다른 자녀·다른 기간·불명확이면 기록을 조회하지 않고 `clarification`으로 끝낸다.
- **수치(FN-AGT-05):** 분모가 5 미만이면 비율은 null이다. LLM은 계산 결과를 문장으로만 옮기고, 건수 지표에는 분자·분모를 넘기지 않는다("3개 중 3개" 방지).
- **대조(FN-AGT-06):** 다음 중 하나라도 어긋나면 LLM 문장을 버리고 규칙 응답(`source: TEMPLATE`, `fallback.reason: VERIFICATION_FAILED`)으로 보낸다.
  - 답변의 숫자가 계산값·기록 수·기간 날짜에 없음
  - "세 번"처럼 한글로 쓴 수가 있음
  - 따옴표 인용이 원문과 다름
  - 레벨·등급·점수·사고력 같은 표현이 있음
- **LLM 장애:** 분류 단계든 답변 단계든 규칙 응답(`AI_UNAVAILABLE`)으로 보낸다. 분류 전에 실패하면 기본 수치(COUNT)만 계산한다.
- **기록 부족(FN-AGT-09):** 조회 기간과 기록 수만 안내한다. 대체 응답이 아니라서 `fallback`은 null이다.
- **조회 실패(FN-AGT-10):** `error` 이벤트로 끝내고 빈 기록으로 바꾸지 않는다.
- **`delta` 미전송:** 답변은 대조를 통과한 뒤에만 보여 주므로 임시 텍스트를 흘리지 않는다. 진행 상황은 `status`로 보낸다.
- **체크포인터 없음:** ai는 대화를 저장하지 않는다. 이전 대화는 core가 `history`로 넘기고, 맥락 파악에만 쓴다(FN-AGT-08).
- **전체 마감:** `ANALYSIS_DEADLINE` 110초. P12의 전체 120초 안에서 LLM을 호출한다.

## 계약 확인 필요 (ai 구현안)

- `result`의 `messageId`·`scope.changed`는 core가 붙인다. ai는 `source`·`fallback`·`versions{model,prompt}`과 `verification.contentAllowed`를 추가로 보낸다.
- `clarification` 데이터: `{reason: OTHER_CHILD|DIFFERENT_PERIOD|UNCLEAR, message, current{childId,from,to}}`.
- `error` 데이터: `{code, message, retryable}`. code는 `RECORDS_UNAVAILABLE`·`RECORDS_NOT_READY`·`RECORDS_INVALID`·`FORBIDDEN`·`INTERNAL_ERROR`.
- 돌아보기 인용 근거는 답변 ID가 없어 `answerId`·`answerVersion`이 null이다.
- learning 기록 조회(#105)의 `contracts/openapi/learning-service.yaml`에 맞췄다. 최상위 학생 필드 `studentId`, 집계 대상 수 지표 이름 `학습한 활동`에 의존한다. 이 지표가 없으면 `RECORDS_INVALID`로 처리한다.
- 전후 변화 근거(`changes`)는 답변 버전을 주지 않아 `answerVersion`이 null이다.

## 검증

- ai-service 전체 테스트 **167개 통과**(기존 133개 + 분석 34개). Ruff check/format 통과. `scripts/tests` 54개 통과.
- 분석 테스트 경로:
  - 정상 LLM 답변
  - 범위 확인(조회 없음)
  - 대조 실패 → 템플릿
  - 분류·답변 LLM 장애 → 템플릿
  - 기록 없음 안내
  - 수학 점검 안내
  - 조회 실패 → error
  - 권한 밖 → 403
  - 기간 역순 → 400
  - learning 클라이언트: 연결 하나 공유, 첫 페이지만 읽기, 전후 변화는 전체 페이지, 학생·기간 불일치, 처리 중, 형식 오류, 집계 대상 수 지표 없음, 연결 오류, 도구 호출마다 권한 확인
- **실제 LLM 호출과 실제 learning 연동은 확인하지 않았다.** 로컬 `.env`에 LLM 키가 없어서다. 가짜 LLM과, learning 계약 형태로 만든 가짜 응답으로만 검증했다.

## 남은 작업

1. 실제 LLM 키로 프롬프트 품질과 대조 통과율을 확인한다. 한글 수 표현 때문에 템플릿 전환이 잦으면 프롬프트를 조정한다.
2. compose로 learning을 띄워 실제 기록 조회와 연동해서 확인한다.
3. core 대화 저장, `messageId`·`scope.changed` 연결, 오류 신고 연결.
4. 리포트 서술(`/internal/report-narratives`): report 측(#52)에서 정한 계약에 맞춘다. 대조 실패만 report가 템플릿으로 바꾸고, AI 장애는 FAILED로 처리한다.
