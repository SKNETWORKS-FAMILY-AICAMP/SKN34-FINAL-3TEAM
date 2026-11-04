# 판정 평가 자료 (#199, NFR-AIQ-01)

LLM 판정(서술·논술)이 사람과 얼마나 같은지 재는 고정 평가 자료. 러너는 [`evaluation/runners/judgment_eval.py`](../../runners/judgment_eval.py).

- 규모(기능명세 P11·3.5): 유형별 대표 미션 5개 × 미션당 예시 답안 20개 = 100개, 평가자 2명이 **서로 보지 않고** 요소별 충족 여부 표시
- 자체 작성 답안만 사용. **AI Hub 원문 미포함**(외부 LLM 전송 금지, NFR-AIQ-02)
- 학생 실명·ID 넣지 않음
- 자료를 바꾸면 `--dataset-version`을 올리고 이전 결과와 섞지 않음

## 파일

| 파일 | 내용 |
|---|---|
| `cases.example.jsonl` | 형식 예시 4건(자체 작성, 테스트용). 실제 평가에 쓰지 않음 |
| `cases.jsonl` | 실제 평가 자료 (준비 중, 담당·일정 확인 필요) |

## 한 줄 형식 (JSON Lines, 답안 1개 = 1줄)

```json
{
  "caseId": "m-1-a01",
  "missionId": "m-1",
  "rubricVersion": "r-1@1",
  "inputType": "ESSAY",
  "grade": 5,
  "answerText": "학생 답안",
  "rubric": {"elements": [
    {"elementId": "e1", "label": "주장", "description": "자기 주장", "points": 1, "judgeVerified": false},
    {"elementId": "e2", "label": "경험 연결", "points": 1, "judgeVerified": false, "goodThought": true}
  ]},
  "raters": {"r1": {"e1": true, "e2": false}, "r2": {"e1": true, "e2": true}}
}
```

- `inputType`·`grade`·`rubric`은 `/internal/judgments` 요청과 같은 형식(api-spec 4.2, `app/judgment/models.py`)
- `raters.r1`·`raters.r2`: 기준표의 **모든** 요소에 true/false. 빠지거나 남는 요소가 있으면 러너가 거부
- 사람 판정 결과(CORRECT·PARTIAL·RETHINK)는 표시한 요소에 서비스와 같은 규칙(`judgment/service.py` `_result`)을 적용해 계산
