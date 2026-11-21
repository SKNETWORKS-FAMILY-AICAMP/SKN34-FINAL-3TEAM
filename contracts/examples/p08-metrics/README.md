# #836 P08 수치 규칙 공통 픽스처

P08(functional-spec 1.4) 수치 규칙은 세 서비스가 각자 계산한다(architecture 1.1 허용한 중복). `cases.json`은 같은 입력 → 같은 출력 기준이며, 세 서비스 테스트가 이 파일을 함께 읽어 한 곳만 바뀌면 실패한다.

| 항목 | learning | report | ai |
|---|---|---|---|
| `reasonConnectives`, `textCounts` | `TextCounts.of(content.only(inputType))` | `text_counts(AnswerInput.written_text())` | 셈하지 않음(learning 값 사용) |
| `minSample`, `sampleState`, `ratio` | `Metric.ratio`·`QueryState.of` | `sample_state` | `ratio_metric`·`count_metric` |

- 테스트: learning `record/P08SharedFixtureTest.kt`, report `tests/test_p08_shared_fixture.py`, ai `tests/analysis_agent/test_p08_shared_fixture.py`
- `content`는 learning 기록 API의 답변 `content` 모양 그대로다. 글자 수는 유니코드 코드포인트 기준(이모지 1글자)
- 규칙을 바꿀 때는 P08 문서 → 이 파일 → 세 구현 순서로 함께 고친다
