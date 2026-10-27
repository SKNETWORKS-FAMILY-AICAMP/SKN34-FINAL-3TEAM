# 이슈 #4 M2 학습 결과와 API 명세 정렬

작성일: 2026-10-26. 기준: `develop`의 `9f02365`(PR #31 병합), [PR #31 검토 코멘트](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/31#issuecomment-6415307735), [API 명세 4.3](../design/api-spec.md), [M2 README](../../ml/m2/README.md).

PR #31의 M2 학습 코드와 `POST /internal/m2/scores` 명세 사이 불일치 3건(학년 입력, 점수 범위, 모델 버전)을 명세에 반영했다. 학습 코드는 바꾸지 않으므로 재학습은 필요 없다.

## 변경 대상과 이유

| 대상 | 적용 내용 | 이유 |
|---|---|---|
| `api-spec.md` 4.3 `grade` | `grade`(정수 3~6)를 scoring이 `초{grade}`로 바꿔 모델 입력에 사용. 학습 데이터 학년(초5·6) 밖은 활성 범위 밖 | 모델은 `[학년] 초5` 문자열로 학습됨. 데이터에 중1~3도 있어 정수 3~6으로 학습 입력을 바꿀 수 없으므로 서빙에서 변환. 변환을 빠뜨리면 오류 없이 성능만 떨어짐 |
| `api-spec.md` 4.3 응답 | "항목별 1~5점" → 총점 1~4점·8개 항목 1~5점 | 두 데이터 모두 총점은 1~4점만 있고(5점 0건), 모델도 총점을 1~4로 자름 |
| `ml/m2/README.md` 모델 입력·출력 | "API `{prompt, text, grade}`와 같음" → `grade` 변환 규칙 명시 | 기존 문구가 사실과 다름 |

## 모델 버전 규칙

서술형·논술형을 따로 학습해 모델이 2개이지만, 명세의 모델 버전 예시는 `m2-klue@1.0` 하나였다. 기존 설계에서 아래가 정해져 있어 이를 따라 규칙을 정했다.

| 근거 | 내용 | 결론 |
|---|---|---|
| core `V5__operations_and_events.sql` `uq_model_version_active` | `(kind, name) WHERE status = 'ACTIVE'` 유일 | 같은 `name`이면 두 모델을 동시에 활성화할 수 없음 → `name` 분리 |
| `erd.md` `model_version` | 행마다 `name`, `version`, `artifact_uri` | 모델마다 행 1개, 가중치 경로도 행마다 보관 |
| `api-spec.md` 버전 표기 | `name@version` (예: `judge@4`) | 표기 형식 유지 |
| `api-spec.md` `/internal/judgments` 요청 | `inputType` 포함 (`NARRATIVE` 서술, `ESSAY` 논술) | 글 종류는 `inputType`으로 구분 |
| `erd.md` `judgment.model_version` | 단일 varchar | 판정 1건에 모델 1개라 저장 구조 변경 불필요 |

| 항목 | 규칙 |
|---|---|
| name | 서술형 `m2-klue-narrative`, 논술형 `m2-klue-essay` (`inputType`과 1:1) |
| version | `X.Y`. 입력·출력 형식이 바뀌면 X, 같은 형식으로 다시 학습하면 Y 증가 |
| artifact_uri | `s3://<버킷>/models/{name}/{version}/` |
| 활성화 | 두 모델을 따로 활성화·롤백 |

반영: `api-spec.md` 4.3 요청에 `inputType` 추가·버전 예시, `class-diagram.md` scoring `M2Service`·`ModelRegistry`(name 기준)와 ai `ScoringClient`, `erd.md` `model_version.name` 예시, `ml/m2/README.md` 가중치 보관. DB 마이그레이션 변경 없음.

## 추가 확인 필요

- 논술 답변은 `essay{claim, reasons[], rebuttal}` 구조(`api-spec.md` 3.1)이고 학습 데이터는 한 덩어리 글이다. ai-service가 scoring에 넘길 `text`로 합치는 규칙을 scoring 연동 구현 전에 정해야 한다.
