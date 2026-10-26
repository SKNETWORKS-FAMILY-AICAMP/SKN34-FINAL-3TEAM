# 이슈 #6 ai-service 판정·되묻기 API 설계 변경

작성일: 2026-10-26. 기준: `develop`의 `66f6052` 및 [이슈 #6](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/6), [API 명세 4.2](../design/api-spec.md), [기능 명세 P01~P16](../design/functional-spec.md), [상태 다이어그램 3장](../design/state-diagram.md). PR [#30](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/30).

ai-service의 `POST /internal/judgments`, `POST /internal/followups`, `GET /internal/versions`와 LLM 래퍼를 구현하면서 바꾼 API 계약, 설계 문서와 다르게 구현한 부분, 문서에 기준이 없어 정한 값을 기록한다. 데이터베이스 스키마는 바꾸지 않았다.

## API 계약 변경

[API 명세 4.2](../design/api-spec.md)의 followups 행과 [시퀀스 다이어그램](../design/sequence-diagram.md) 피드백 흐름의 followups 요청·응답을 갱신했다.

| 대상 | 변경 | 이유 |
|---|---|---|
| followups 요청 | `grade`(3~6) 추가 | 학년군(초3~4·초5~6)에 맞는 말투로 질문을 만들기 위함. 판정 요청과 같은 값을 보낸다 |
| followups 응답 | `versions{model, prompt}` 추가 | `followup` 테이블의 `model_version`·`prompt_version`을 learning이 저장할 값이 응답에 없었음 (NFR-DAT-02) |

하위 호환: 응답의 `versions`는 필드 추가다. 요청의 `grade`는 필수라 learning이 보내지 않으면 400이 난다. 선택값으로 두면 빠뜨려도 드러나지 않고 학년에 맞지 않는 말투로 질문하게 되므로 필수로 정했다.

```jsonc
// POST /internal/followups 요청
{
  "timeline": [{"kind": "ANSWER", "text": "..."}, {"kind": "FOLLOWUP", "text": "..."}],
  "judgment": {"result": "PARTIAL", "heldReason": null, "elements": [{"elementId": "e1", "satisfied": true}]},
  "rubric": {"elements": [{"elementId": "e1", "label": "주장", "description": "...", "goodThought": false}],
             "answerKey": null, "forbiddenTerms": ["..."], "exampleAnswer": "..."},
  "mission": {"title": "...", "question": "...", "thinkingType": "EVALUATE"},
  "grade": 5
}
// 응답. 재생성까지 유출이면 question: null, leakCheck.passed: false → learning이 질문 은행 선택 (P16)
{"type": "TELL_MORE", "question": "...", "source": "LLM", "leakCheck": {"passed": true},
 "versions": {"model": "claude-sonnet-5-5", "prompt": "followup@4"}}
```

## 설계 문서와 다르게 구현한 부분

결과 결정 위치, 미검증 요소 보류, `versions.model` 의미, 함수 이름, 파일 구성은 설계 문서를 구현에 맞춰 갱신했다: [API 명세](../design/api-spec.md) 1.6·3.2, [클래스 다이어그램](../design/class-diagram.md) 4.2·5.1, [시퀀스 다이어그램](../design/sequence-diagram.md) 피드백, [상태 다이어그램](../design/state-diagram.md) 3, [ERD](../design/erd.md) 기준표 규칙, [아키텍처](../design/architecture.md) ai-service 디렉토리 구조.

| 항목 | 문서 | 구현 | 근거 |
|---|---|---|---|
| 미검증 요소 보류 | `judge_verified = false`면 `HELD(UNVERIFIED_SCOPE)` (state-diagram 3, erd) | 기본 꺼짐, `JUDGE_REQUIRE_VERIFIED=true`로 켬 | 사람 검증(P11)이 아직 없어 켜면 모든 서술 판정이 보류됨 |
| 보류 시 요소 결과 | 정하지 않음 | `HELD`면 `elements` 빈 배열 | 보류가 낮은 수준으로 기록되지 않게 함 (FN-JDG-04) |
| 결과 결정 위치 | `QuoteVerifier.decide` (class-diagram) | `judgment/service.py` | 업무 판단은 service (architecture 2.1). `verifier.py`는 원문 대조만 |
| `versions.model` 의미 | 예시가 M2 버전(`m2-klue@1.0`), LLM 판정은 `null` (api-spec 1.6·3.2) | LLM 모델 ID (예: `claude-sonnet-5-5`) | 제공자를 바꿔도 판정·되묻기를 만든 모델을 남김. 되묻기에는 M2가 없어 같은 의미로 맞춤 |
| 함수 이름 | `LeakGuard.check`, `FollowupService.generate`, `LlmClient.complete` | `find_leaks`, `create`, `generate` | 동작은 같음. class-diagram을 코드에 맞춤 |
| 사용량 이벤트 `traceparent` | 봉투에 포함 (architecture 1.6) | null | PR #28 공통 `UsagePublisher`가 받지 않음. 공통 기반 수정은 범위 밖 |
| LLM 제공자 | Claude API (architecture 6장) | Claude + OpenAI·OpenAI 호환 sLLM, `LLM_PROVIDER`로 교체 | architecture의 "`llm/` 래퍼로 교체 가능" 범위 안. Claude 전용 기능(추론 강도·대체 모델·스키마 강제)을 지키려고 제공자별 클래스를 둠 |

## 문서에 기준이 없어 정한 값

이슈 #6의 "확인 필요" 항목은 담당자가 정했다. P12 목록에 없는 수치는 `backend/ai-service/app/config.py`에 두고 환경 변수로 바꿀 수 있다.

| 항목 | 정한 값 | 이유 |
|---|---|---|
| 판정 결과 변환 | 필수 요소(`goodThought=false`) 모두 충족 → `CORRECT`, 충족 배점 0 → `RETHINK`, 그 외 → `PARTIAL` | state-diagram 3의 "모든 필수 요소", "배점 기준"을 따름. 들어가면 좋은 생각만 충족한 답은 `PARTIAL` |
| 보류 판단 순서 | `TOO_SHORT` → `UNVERIFIED_SCOPE` → `INSUFFICIENT_EVIDENCE` → `QUOTE_MISMATCH` | 앞의 둘은 LLM 호출 전에 걸러 비용을 쓰지 않음 |
| `TOO_SHORT` 기준 | 공백 제외 10자 미만 | "몰라요" 같은 답을 LLM 호출 없이 보류 |
| 원문 대조 허용 범위 | 유니코드 NFC, 연속 공백 하나로, 앞뒤 공백 제거 | 띄어쓰기 차이만 허용하고 글자가 다르면 불일치 |
| 되묻기 유형 | `CORRECT`→`ONE_STEP_MORE`, `PARTIAL`·`HELD`→`TELL_MORE`, `RETHINK`→`LOOK_AGAIN` | 보류는 학생이 생각을 더 말하도록 유도 |
| 예시 답 처리 | LLM에 보내지 않고 코드 유출 검사에만 사용. 12자 이상 겹치면 유출, 학생이 이미 쓴 말은 제외 | 보지 않은 내용은 베낄 수 없음. 학생 말을 되받는 질문을 유출로 오판하던 문제를 실제 호출에서 확인해 수정 |
| 되묻기 전체 마감 | 33초 | 첫 생성 + 재생성 최악 62초가 learning→ai 35초(P12)를 넘음. 재생성은 남은 시간 안에서만 하고, 못 하면 질문 은행으로 넘김 |
| `GET /internal/versions` 응답 | `{"prompts": {"judgment": "judge@2", "followup": "followup@4"}}` | 이슈 #6의 "활성 프롬프트 버전"만 반환 |

## learning 연동 시 반영할 점

- 되묻기 요청에 `grade`(판정 요청과 같은 값)를 보낸다.
- 판정·되묻기 응답의 `versions`를 `judgment`·`followup`의 `model_version`·`prompt_version`에 저장한다.
- 되묻기 `question`이 null이고 `leakCheck.passed`가 false면 `followup_bank_question`에서 같은 `type` 질문을 골라 `source = BANK`로 저장한다 (P16).
- `elementId`는 `rubric_element.id`(UUID)로 보낸다. `judgment_element.rubric_element_id`에 그대로 저장할 수 있다.
- ai 판정은 최악 31초, 되묻기는 33초 안에 끝나므로 learning→ai 타임아웃 35초(P12)와 맞는다.

## 후속 할 일

확인·합의가 필요한 것:

- M2 연동 시 M2 버전은 `judgment.model_scores`에 담는 방안을 이슈 #4 담당과 정한다.
- 사용량 이벤트 `traceparent`를 공통 `UsagePublisher`에 추가할지 정한다.
- OpenAI 키를 받으면 `gpt-6-luna` 모델 ID와 판정·되묻기 결과를 실제 호출로 확인한다.
