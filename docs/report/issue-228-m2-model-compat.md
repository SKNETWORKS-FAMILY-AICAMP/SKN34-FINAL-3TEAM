# #228 서술 3.0·논술 3.1 서비스 호환 검토·검증

## 목적과 기준

기존 scoring은 두 입력 유형을 모두 9출력으로 해석해 논술 3.1의 14출력을 로딩하지 못했다. 새 모델의 학습 입력 형식, 출력 순서, 점수 경계를 실제 서비스와 맞춘다.

- 최초 구현·검증 기준 develop: `e9ce4a1` (PR #261 학습 산출물 보완 포함). 2026-11-03 작업 브랜치에 최신 develop `90cdec6`을 반영했으며, 아래 2026-11-02 검증 결과는 당시 기준의 기록이다.
- 작업 브랜치: `feature/228-m2-model-compat`.
- 사용자 전달 담당자 답변: 서술 3.0·논술 3.1, 논술 14개 중 앞 3개만 사용, 소수와 변환 정수를 함께 전달. 2026-11-03 전달된 후속 답변에서도 논술 3.1 유지가 확정됐다.
- `train_545.py`의 train_info·score_cuts 저장은 수빈님 PR #261로 이미 반영됐다. 동일 로직을 중복 구현하지 않는다.

### 담당자 후속 확인 (2026-11-03 사용자 전달)

근거는 사용자가 이 대화에 전달한 담당자 메시지와 [PR #261](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/261)이다.

- 실험 결과 논술은 **3.1을 그대로 사용**한다. 버전 선택은 더 이상 미정 항목으로 취급하지 않는다.
- 기존에 전달받은 **score_cuts.json을 그대로 사용**한다. 경계는 여전히 임시이며, 담당자가 변경 파일을 전달하면 교체·재검증한다. 이번 확인만으로 기존 경계를 새로 계산하거나 교체하지 않는다.
- 담당자가 실제 학습에서 `train_545.py`의 **score_cuts.json·train_info.json 자동 저장까지 확인했다**고 보고했다. PR 본문의 "GPU에서 학습 끝까지 돌려 확인하지 못함"은 PR 작성 당시 상태이며, 이번 후속 답변으로 담당자 측 확인이 완료됐다.
- PR 병합 상태와 현재 코드의 두 파일 저장 로직은 직접 대조했다. 실제 학습 실행 확인은 담당자의 보고에 근거하며, 이 기록 갱신 과정에서 학습을 재실행한 것은 아니다.

## API 변경

기준 계약은 [API 4.3](../design/api-spec.md#43-scoring-service-호출-ai)과 [scoring OpenAPI](../../contracts/openapi/scoring-service.yaml)다. API 명세를 먼저 수정한 뒤 코드를 반영했다.

| 항목 | 서술 3.0 | 논술 3.1 |
|---|---|---|
| 이름 | m2-klue-narrative | m2-klue-essay |
| 모델 출력 | 9 | 14 (앞 3개만 사용) |
| 첫 문장 | `[학년] 초N [핵심어] ` + 쉼표·공백으로 연결한 핵심어 | `[학년] 초N [글 종류] {essayType}` |
| 두 번째 문장 | 학생 text | 학생 text |
| 활성 학년 | 5·6 | 4·5·6 |
| 응답 키 | 기존 hol·task_1·content_1~3·organization_1~2·expression_1~2 | org·cont·exp (구성·내용·표현) |
| scores | 경계 bisect_right + 1; hol 1~4, 나머지 1~5 | 경계 bisect_right; 0~3, +1 없음 |
| rawScores | 유한 소수 원점수 그대로 | 유한 소수 원점수 그대로; 임의 반올림·범위 자르기 없음 |

ESSAY 요청에는 essayType(설명글·글짓기·주장·찬성반대·대안제시)이 필수이며 누락·잘못된 값은 400이다. prompt는 기존 필드로 유지하되 새 모델 입력에서 제외한다. 논술 학습 목표 범위는 0~3이지만 회귀 예측이 범위를 벗어나도 원점수를 자르지 않는다. 화면 표시 방식과 #69 판정 소비는 이 변경의 완료 범위가 아니다.

이전 2.0 모델의 메타데이터는 기존 지시문 입력·9항목 반환 경로로 처리한다. 이전 논술 모델은 4학년을 승인했더라도 비활성이다. 새 ESSAY 요청의 essayType 필수 조건은 공통 적용되므로 소비 측도 새 요청 계약을 따라야 한다.

## 산출물과 임시 경계

`m2_models_1102.tar`의 버전별 디렉터리에서 6개 파일을 사용한다: config.json, model.safetensors, tokenizer.json, tokenizer_config.json, train_info.json, score_cuts.json. 원본 tar의 논술 score_cuts 누락은 담당자가 별도로 준 아래 값으로 보완한다. 학습 메타데이터나 경계를 임의로 추정하지 않았다.

```json
{"org":[0.5,2.15,2.55],"cont":[0.5,2.15,2.5],"exp":[0.5,2.1,2.55]}
```

이 경계는 학습한 주제 검증 글로 정한 **임시 기준**이다. 새 주제 실험 후 바뀔 수 있다. score_cuts.json이 변환 기준이며 기존 tar의 train_info 안에 있는 `score_cuts:null`·과거 미정 설명으로 덮어쓰지 않는다. 변경 파일을 받으면 해당 산출물·경계 해시를 남기고 다시 로딩·점수 변환을 검증해야 한다. 현재 결과를 모델 품질 승인이나 최종 정수 경계로 해석하지 않는다.

가중치·AI Hub 데이터는 Git에 넣지 않는다. 검증은 원본 tar를 풀어 저장소에 복사하지 않고 허용된 일반 파일만 로컬 MinIO로 스트리밍한다. 원본 tar의 `./` 접두사도 지원한다. 운영 S3 업로드·활성화는 하지 않는다.

## 구현

- 기존 ModelLoader·S3ModelArtifacts·M2Service·ModelRegistry를 재사용한다.
- 공통 메타데이터 검사는 로딩·추론에서 동일하게 사용한다. 모델 이름·데이터셋·입력 플래그·출력 순서·출력 수·최대 길이·경계 키/개수/유한성/정렬을 검사한다.
- 잘못된 체크포인트는 활성 snapshot에 넣지 않는다. 최초 로딩 실패 시 재시도, 교체 실패 시 기존 모델 유지 정책은 기존 레지스트리를 따른다.
- 지원하지 않는 학년·미승인 scope·서술 핵심어 없음은 비활성, 추론 장애는 503으로 구분한다. 비활성에서 추론·사용량 이벤트를 만들지 않는다.

## 최초 검증 (2026-11-02)

| 검사 | 결과 |
|---|---|
| scoring Ruff check·format | 통과 |
| scoring 전체 pytest | 167개 통과 |
| 공통 계약 unittest | 95개 통과 |
| 최신 core bootJar | Linux Docker 빌드 통과 (Windows loopback 오류 우회) |
| scoring Docker 이미지 | 빌드 통과 |
| 실제 MinIO·core·scoring | 두 모델 총 12개 파일 업로드, 실제 등록·활성화·로딩·버전 조회·readiness 200 및 지원 학년 5개 조합 active:true 통과 |

단위 검증에는 새 입력·경계와 같은 값·범위 밖 원점수 보존·14개 중 3개 노출·4학년 허용·잘못된 출력/경계/메타데이터 거부·기존 2.0 호환·인증/비활성/장애·실제 FastAPI/OpenAPI 대조가 포함된다. 품질 평가용 AI Hub 글 대신 합성 글을 사용한다.

재현 명령(저장소 루트 기준, 모델 경로와 결과 경로는 저장소 밖):

```powershell
docker build -t local/scoring228:20261102 backend/scoring-service
cd backend/scoring-service
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
uv run --frozen python ../../scripts/verify_scoring_m2.py --archive <m2_models_1102.tar> --core-root <최신-core-저장소> --output <외부-결과폴더> --image local/scoring228:20261102 --new-models --essay-cuts <담당자-score_cuts.json>
```

검증 스크립트는 격리된 Compose 프로젝트와 임시 관리자·DB·MinIO를 만들며 기존 로컬 서비스 데이터는 변경하지 않는다. 종료 시 해당 프로젝트를 정리한다. 임시 core의 모델 승인은 전송·로딩 검증용이며 운영 배포·품질 승인이 아니다.


### 실제 연동 결과 (2026-11-02)

최종 이미지 `local/scoring228:20261102`, 별도 Compose 프로젝트 `issue85-973afdccd5`에서 실제 최신 core JAR·PostgreSQL·RabbitMQ·Redis·MinIO·scoring을 사용했다. 빈 snapshot 준비 완료, 미인증 401, core 등록·활성화 후 파일 누락 시 readiness 503/liveness 200, 업로드 후 같은 scoring 프로세스에서 readiness 200 복구를 확인했다.

`/internal/versions` 응답:

```json
{"items":[{"name":"m2-klue-essay","version":"3.1","revision":1},{"name":"m2-klue-narrative","version":"3.0","revision":1}]}
```

지원 학년별 실제 HTTP 응답:

| 입력 | 학년 | 결과 |
|---|---|---|
| NARRATIVE | 5·6 | active:true, 9항목 정수·원점수, 모델 3.0 |
| ESSAY | 4·5·6 | active:true, org·cont·exp 정수·원점수만, 모델 3.1 |
| NARRATIVE | 3·4 | active:false |
| ESSAY | 3 | active:false |
| NARRATIVE | 5, 핵심어 없음 | active:false |
| ESSAY | essayType 누락 | 400 |
| 인증 없음 | 내부 API 요청 | 401 |

논술 5학년 실제 응답 예시(합성 글, 평가 품질 지표 아님):

```json
{
  "active": true,
  "inputType": "ESSAY",
  "scores": {"org": 1, "cont": 1, "exp": 2},
  "rawScores": {"org": 1.5554603338241577, "cont": 1.6391863822937012, "exp": 2.158329963684082},
  "model": {"name": "m2-klue-essay", "version": "3.1", "revision": 1}
}
```

모든 지원 학년 응답을 실제 OpenAPI 스키마와 대조하고, 응답 rawScores에 파일 경계를 적용한 값이 scores와 정확히 같은지 검사했다. 5개 단발 요청의 지연은 약 159~3,126ms였으나 워밍업·부하 조건을 통제한 성능 평가가 아니므로 p95나 성능 보장으로 사용하지 않는다.

로컬 증거는 저장소 밖 `../tmp/issue228-real-models-final/results.json`(파일별 SHA-256·버전·readiness·실제 점수 응답), `services.log`, `cleanup.log`에 있다. 로그와 Compose 설정은 검증 자격 증명을 포함할 수 있어 Git에 넣지 않는다. 최종 검증 종료 후 전용 컨테이너·MinIO 데이터는 정리됐으며 기존 `sagomungchi` 프로젝트 컨테이너는 그대로 실행 중이다. 기존 로컬 앱에서 새 모델을 상시 사용하도록 전환한 작업은 아니다.

### 이슈 요구사항 대조 (로컬 완료 근거)

- [x] 서술 3.0 디렉터리 6개 파일 확보·로컬 업로드 검증.
- [x] 논술 B(3.1·14출력) 선택, PR #261 학습 산출물 보완 확인, 로더·응답·API 수정.
- [x] MinIO 업로드 → 실제 core 등록·활성화. 서술 grade-5/6, 논술 grade-4/5/6 승인 scope.
- [x] `/internal/versions` 두 새 버전 및 readiness HTTP 200.
- [x] `/internal/m2/scores` 두 유형 active:true, 정수 변환·소수 보존 확인.
- [x] Ruff check·format, 전체 pytest, docs/report API 변경 기록.

위 체크는 로컬 검증 근거이며 원격 이슈 상태를 수정하지 않았다. 운영 품질 승인·AWS 업로드·#69 실제 판정 연결·화면 점수 선택·새 주제 기준 경계 확정은 완료로 포함하지 않는다.

## 최신 develop 통합 검증 (2026-11-03)

develop `90cdec6`을 반영한 작업 브랜치에서 다음 검증을 완료했다. 논술 3.1과 기존 담당자 제공 score_cuts.json을 유지했으며 학습을 다시 실행하거나 경계를 재계산하지 않았다.

| 검사 | 결과 |
|---|---|
| scoring Ruff check·format | 통과. 서비스 44개 파일과 실제 모델 검증 스크립트 2개 검사 |
| scoring 전체 pytest | **167개 통과**, 27.85초 |
| 공통 계약 unittest | **99개 통과**, 55.39초 |
| 최신 core bootJar | 현재 소스로 Docker 빌드 통과 |
| scoring 이미지 | `local/scoring228:20261103` 빌드 통과 |
| 실제 MinIO·core·scoring | 두 모델의 총 12개 파일 업로드·등록·활성화·로딩·HTTP 점수 응답 통과 |
| 변경 파일 | `git diff --check` 통과 |

실제 `/internal/versions`는 서술 `m2-klue-narrative@3.0`과 논술 `m2-klue-essay@3.1`(각 revision 1)을 반환했고 readiness는 HTTP 200, models·rabbitmq 모두 UP이었다. 서술 5·6학년과 논술 4·5·6학년의 5개 조합 모두 `active:true`였으며 OpenAPI, 원점수 보존, 파일 경계에 따른 정수 변환, 논술의 org·cont·exp 3개 키를 대조했다. 미지원 학년·핵심어 누락의 비활성, essayType 누락 400, 내부 인증 누락 401도 확인했다. 파일 누락 상태의 readiness 503/liveness 200에서 업로드 후 같은 scoring 프로세스로 정상 복구됐다.

공통 테스트의 첫 실행은 Windows 샌드박스 임시 디렉터리 권한으로 실패했고, 저장소 밖 작업 폴더의 TEMP·TMP로 재실행해 통과했다. scoring은 같은 잠금 의존성으로 `uv run --frozen --offline python -X utf8 -m pytest`를 실행했다. 테스트 통과를 위해 제품 코드나 검증 조건을 완화하지 않았다.

실제 모델 검증 증거는 저장소 밖 `../tmp/issue228-real-models-20261103/results.json`과 로그에, pytest 결과는 `../tmp/issue228-pytest-20261103.xml`에 보관한다. 격리된 검증용 Compose 자원은 종료 후 정리했다. 기존 로컬 앱의 상시 활성 모델이나 운영 환경을 전환한 결과는 아니며, 가중치·원본 데이터·로컬 자격 증명·로그는 커밋에 포함하지 않는다.

## 후속: 서술 content_3 선택 보정 (2026-11-03)

서술 적절성 점수에 핵심어 포함 비율을 결합하는 후보 규칙을 추가한다. 기본값은 꺼짐이며 기존 #228 결과를 유지한다. API 4.3.1과 OpenAPI에 선택 보정의 예외를 먼저 명시한 후 구현했다. 기준 develop은 `b78cf78`, 작업 브랜치는 `feature/m2-content3-rule`이다.

### 기준 자료와 적용 범위

- 황수빈(M2) 제공 `content3_rule_1103.json`·`content3_rule_1103.py`, 모두 2026-11-03 v1.0.0. JSON SHA-256: `e0b3704940aa29848c468cc1103d5d1bd641c4384320955fbbc47ab468165fe4`, Python SHA-256: `b076deacd403a60dfe210b43686559982ca07fd35df3577bc4adfac4b175f70e`.
- 계수는 `(w0, w_model, w_ratio) = (0.9724, 0.197, 2.8891)`이며 코드에 고정한다. 이후 계수·규칙을 바꾸면 규칙 버전도 올리고 재검증한다. 이 JSON은 기존 모델의 train_info.json·score_cuts.json을 대체하는 파일이 아니다.
- `M2_CONTENT3_RULE_ENABLED=true`이면서 활성 모델이 정확히 `m2-klue-narrative@3.0`이고 NARRATIVE 초5·6의 승인 scope일 때만 적용한다. 설정 미입력·false이면 보정 함수를 호출하지 않는다. 다른 서술 모델 버전과 모든 논술은 기존 계산을 유지한다.
- 핵심어 없는 서술·미승인 범위·미활성 모델은 기존처럼 비활성이다. 메타데이터·score_cuts·모델 출력 검증, 내부 인증, 사용량 발행, 추론 장애 503 처리를 유지한다. 모델 추론은 요청당 한 번이며 DB·모델 파일·레지스트리 계약은 변경하지 않는다.

### 계산과 입력 형식

```text
mixed = clip(0.9724 + 0.197 * 모델 content_3 원점수 + 2.8891 * 핵심어 포함 비율, 1, 5)
rawScores.content_3 = round(mixed, 4)
scores.content_3 = floor(mixed + 0.5)
```

정수는 표시용 소수 4자리 반올림 전에 계산한다. 예를 들어 mixed가 2.49996이면 rawScores는 2.5, scores는 2다. 보정된 content_3에 기존 score_cuts 경계를 적용하거나 Python round로 정수를 구하지 않는다. 나머지 서술 8개 항목과 model.name/version/revision은 그대로 반환한다.

핵심어는 `['한글(훈민정음, 정음)', '환경(자연/생태)']`처럼 배열 원소 하나당 묶음 하나를 보낸다. 참고 구현은 배열을 연결한 뒤 괄호 밖 쉼표로 묶음을 구분하므로 `['환경, 보호']`도 두 묶음으로 계산한다. 이 동작은 두 첨부 파일에 공통으로 명시되어 있어 그대로 따른다. 메시지 설명의 별도 수정 시각은 확인되지 않았으며 더 최신 규칙으로 간주하지 않았다.

각 묶음은 본래 핵심어·괄호 안 대체어 중 하나라도 text에 있으면 1이며 여러 대체어가 맞아도 한 번만 센다. 비교할 때만 공백을 무시하고 부분 문자열을 찾는다. 괄호 안 쉼표·슬래시는 대체어 구분자다. tokenizer 입력 text·keywords는 이 계산으로 바꾸지 않는다. 실제 AI→scoring의 묶음 보존 및 채점 소비 연동은 #69에서 확인해야 한다.

### 설정과 원복

- Settings, `.env.example`, Compose의 기본값은 모두 false다. 환경 변수가 없는 GitOps 배포도 Settings의 false를 사용한다. 실제 로컬 `.env`와 실행 중인 서비스 설정은 변경하지 않았다.
- 허용 기준 확정·품질 승인 후에만 배포 환경의 `M2_CONTENT3_RULE_ENABLED=true`를 지정하고 scoring 프로세스를 재시작한다. Compose의 환경 변수 변경은 컨테이너 재생성이 필요하다. 모델 승인은 별도로 기존 레지스트리 절차를 따른다.
- 원복은 같은 설정을 false로 바꾸고 프로세스를 재시작한다. 이후 채점은 기존 변환을 사용한다. 이미 저장된 채점 결과를 소급 변경하거나 재채점하지 않는다.
- 응답의 model 버전은 실제 모델 버전을 유지한다. 배포 이미지·환경 설정 변경 이력을 함께 보관하고 `app.bootstrap` INFO 로그를 수집하면 `enabled`와 `rule_version=1.0.0`을 확인할 수 있다. 학생 글·핵심어는 로그에 넣지 않는다.

### 검증과 한계

- scoring Ruff check·format 통과, 전체 pytest **199개 통과**. 추가된 32개 사례는 기본값·환경 변수→lifespan→HTTP 연결, 대상 제한, 비활성·장애 보존, 다른 항목·모델 보존, 대체어·공백·묶음 계산, clip·x.5 올림·소수 표시 반올림 경계, ON→OFF 원복을 확인한다.
- 공통 계약 unittest **99개 통과**, Docker 이미지 `local/scoring-content3:20261103` 빌드 통과. 실행 중인 컨테이너를 교체하거나 운영 환경에 배포하지 않았다.
- 별도 합성 입력 **1,000건**에서 변경 전 develop `b78cf78`의 infer와 비교하여 기본값·false의 전체 응답이 정확히 같음을 확인했다. true에서도 대상 content_3 외 응답은 같으며 담당자 Python 참고 구현의 묶음·비율·점수 계산과 일치했다. AI Hub 실제 3,000편 대조와는 별개인 로컬 합성 검사다.
- Windows 샌드박스에서 asyncio 자체의 로컬 소켓 생성이 멈춰 제한 밖에서 동일 테스트를 실행했다. 제품 로직이나 검증 조건은 완화하지 않았다.
- 담당자 보고의 QWK 0.897→0.945와 실제 3,000편 결과 일치는 이번 작업에서 재평가하지 않았다. 계수는 B안의 처음 보는 주제 예측으로 맞춘 값이며 서비스 3.0 자체 예측으로 맞춘 값은 아니다. 핵심어를 다른 말로 풀어 쓴 답의 점수가 낮아질 수 있다는 원본 한계를 유지한다.
- 이번 구현은 기본 꺼짐 후보 기능이다. 11/22 허용 기준 확정·품질 승인, 실제 모델을 사용한 품질 평가, #69 전체 판정 연동 및 운영 활성화를 완료한 것으로 간주하지 않는다.

서비스 검증 재현 명령(`backend/scoring-service`에서):

```text
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
```
