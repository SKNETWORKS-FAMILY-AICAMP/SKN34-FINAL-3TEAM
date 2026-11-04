# scoring 모델 서비스·M1 학습 코드 (#85~#88·#140·#263)

계약은 [API 명세 4.3](../design/api-spec.md#43-scoring-service-호출-ai)과 [scoring OpenAPI](../../contracts/openapi/scoring-service.yaml). 서술 3.0·논술 3.1 모델 호환과 content_3 보정은 [ai](ai.md) 4장.

| 이슈 | 구현 |
|---|---|
| #85 | core 활성 조회, S3/MinIO 다운로드·로딩, 실제 로딩 버전 조회, 승인 범위·readiness·재시도 |
| #86 | 모델 활성 이벤트, revision 순서, 교체 실패 시 기존 모델 유지, 재다운로드 롤백·재연결 |
| #87 | M2 서술형·논술형 채점, 컷 변환·소수 원점수·모델 식별정보, 사용량 발행 |
| #88 | M1 입력 계약, 인증·입력 검증, 미학습 상태 `active:false` |
| #140 | 브로커 연결 복구·readiness·종료, 이벤트 봉투 스키마, 내부 헤더·학생 scope·trace 전파, 설정 로딩 테스트 보강 |

## 1. 모델 레지스트리·S3 로딩 (#85)

- 사용자 결정(10/28): 활성 모델이 없으면 준비 완료, 최초 로딩 실패는 준비 안 됨 상태로 재시도, 교체 실패는 기존 모델 유지
- 모델 이름·버전은 core snapshot 그대로. 임의의 활성 모델·승인 범위를 만들지 않음. `/internal/versions`는 `{items:[{name,version,revision}]}`이며 실제 로딩된 버전만 표시. scope는 정확 일치, 최신 승인 범위가 줄면 교체 실패 시에도 범위를 확장하지 않음

| 파일 | 역할 |
|---|---|
| `app/clients/core_client.py` | 기존 internal_client로 core snapshot 조회, 호출 자체의 중복 재시도 없음 |
| `app/model_versions.py` | scoring 대상 필터·revision·scope 계약 검사 |
| `app/model_registry.py` | 정확한 scope 검사, 낮은 revision 무시, 로딩 완료 후 교체, 실패 시 이전 모델 유지. 보고 revision은 실제 로딩 모델 기준 |
| `app/clients/model_artifacts.py`, `app/model_loader.py` | 설정된 모델 버킷의 S3 디렉터리만 읽고 경로 이탈 차단. `save_pretrained` 모델·토크나이저와 `train_info.json` 로딩, 누락 가중치로 임의 초기화된 모델 거부 |
| `app/model_startup.py`, `app/bootstrap.py` | 기동 조회·로딩의 백그라운드 재시도, models readiness, 종료 시 태스크 정리. health 요청이 core/S3를 직접 호출하지 않음 |

- 설정: `S3_ENDPOINT_URL`(생략 시 AWS SDK 기본 endpoint·자격 증명 체인), `S3_BUCKET`, `S3_REGION`, `MODEL_CACHE_DIR`, `MODEL_RETRY_INTERVAL`. MinIO overlay가 endpoint·로컬 자격 증명 주입
- `MODEL_CACHE_DIR`은 일시 다운로드 경로이며 롤백 캐시가 아님. 로컬 `local_data/scoring-models`(gitignore), 컨테이너 `/tmp/scoring-models`. readOnlyRootFilesystem 배포 시 쓰기 가능한 임시 볼륨 필요
- boto3 S3 클라이언트는 `with client`를 지원하지 않아 `contextlib.closing(client)`으로 정리. 이미지의 uv 다운로드 캐시(약 987MiB)는 BuildKit cache mount로 분리
- 모델 파일 형식: `models/<name>/<version>/`에 `config.json`, `model.safetensors`, `tokenizer_config.json`, `tokenizer.json`, `train_info.json`, `score_cuts.json`. 2.0 기준 각 가중치 약 442MB, 9개 출력 RoBERTa 회귀, `max_length=512`, 서술형 `with_keyword=True`·논술형 `False`
- 실제 2.0 모델 검증(10/29, 로컬 Compose): 빈 snapshot 준비 완료 → 파일 누락 시 readiness 503·liveness 200 → MinIO 업로드 후 재시작 없이 복구 → core snapshot과 `/internal/versions` 일치. 두 모델 로딩 합계 약 23초, 로딩 후 컨테이너 메모리 단일 표본 약 553MiB(별도 probe 최대 RSS 약 1.1GiB). 이 값으로 Kubernetes 자원 제한을 확정하지 않음

재현(모델 tar와 결과 폴더는 Git checkout 밖이어야 실행됨, 결과 폴더의 Compose 설정에 일회용 자격 증명 포함):

```powershell
docker build -t local/scoring-models:<tag> backend/scoring-service
python -X utf8 scripts/verify_scoring_models.py --archive <m2_models.tar> --core-root <최신 develop checkout> --output <저장소 밖 경로>
```

## 2. 활성 버전 이벤트·롤백 (#86)

core에서 모델 버전을 활성화하거나 롤백하면 모든 scoring 레플리카가 해당 버전을 로딩. 이전 버전도 S3/MinIO에서 재다운로드하고 메모리 로딩 후 임시 파일 정리(로컬 영구 캐시 없음).

| 요구사항 | 구현 |
|---|---|
| Pod별 브로드캐스트 | `ModelVersionConsumer`가 서버 생성 이름의 exclusive·auto-delete 큐를 `events.topic`의 `model.version.*`에 바인딩 |
| 큐 연결 후 초기 조회 | consume 등록까지 마친 다음 `ModelStartup` 시작. 조회 중 수신 메시지는 메모리에 보존 |
| 순서 역전·중복 | 이름별 최신 이벤트 보존, `ModelRegistry`에서 revision 비교 |
| scoring 모델만 적용 | kind MODEL이며 `m2-`·`m1-` 이름인 항목만 전달 |
| 로딩 실패 | 기존 모델 유지·재시도. scope는 기존 모델과 최신 승인 범위의 교집합. 한 모델 실패가 다른 이름의 업데이트를 막지 않음 |
| 형식 오류 | 봉투·data 검증 실패 시 본문 없는 경고 후 ACK, 재시도 없음 |
| 재연결 | 이전 session 정리 → 새 큐 바인딩 → snapshot 재조회 |
| readiness | 최초 준비·재연결 조정 전 false. 빈 활성 목록은 준비 완료. 정상 기동 이후 교체 실패는 기존 모델 제공 유지 |
| 로그 | 모델명·revision·큐명·예외 유형만. 메시지 본문·artifact URI·자격 증명 미기록 |

검증: `scripts/verify_scoring_events.py`가 격리된 core·RabbitMQ·MinIO·scoring 2개로 두 exclusive 큐·활성화·롤백 재다운로드·파일 누락 시 기존 버전 유지·브로커 중단 중 활성화 후 재연결 복구·임시 파일 정리를 확인(`2.1-check`는 같은 2.0 artifact를 가리키는 교체 검증용 메타데이터).

## 3. M2 채점 API (#87)

- 담당자 답변(10/29): 관리자 입력 → `rubric_version.keywords` → learning `question/keywords` → AI → scoring `prompt/text/grade/inputType/keywords`. 핵심어는 서술형만, 없으면 비활성. 실제 장애는 503·판정 처리 실패. `score_cuts.json`으로 컷 변환하고 소수 원점수도 보존, 서술형 content_3도 모델 점수 사용. 컷이 없거나 손상된 모델을 반올림으로 대체하지 않음
- `M2Service`는 기존 `ModelRegistry`·`LoadedModel` 재사용. 승인 scope는 `judgment/grade-5/narrative` 같은 정확 일치 값(문항 단위 승인은 요청에 문항 ID가 없어 범위 밖)
- 초5·6만 지원. 모델/승인 범위 밖·핵심어 없는 서술형은 `active:false`
- 학습 메타데이터의 `max_length=512`, 회귀 head, dataset, 핵심어 설정 검사. 첫 문장에 학년·지시문·서술형 핵심어, 글은 두 번째 문장으로 토큰화(`only_second`)
- `bisect_right(cuts, raw)+1`은 학습 `numpy.digitize(raw, cuts)+1`과 같은 경계 처리. hol 1~4, 8항목 1~5. rawScores는 유한 원점수 그대로. 두 유형의 content_1~3 의미가 다르므로 inputType을 함께 반환하고 합산하지 않음
- CPU 작업은 `run_in_threadpool`, 서비스 단위 1개 동시 추론, 대기 최대 1초 이후 503. 추론 중 모델 교체 시 현재 요청은 캡처한 모델, 다음 요청은 새 버전
- 사용량 발행은 제한된 백그라운드 태스크(최대 128, 1초 제한), 실패해도 채점 응답은 성공. 원문·학생 정보 없이 service=scoring, callType=M2, 토큰 null, 지연·성공 여부. 브로커 중단 중에도 이미 로딩된 모델의 채점은 200
- 비활성은 `{"active":false}`만. 서비스는 점수를 DB에 저장하지 않음(`judgment.model_scores` 저장은 learning, ai 4장)

응답 예시(형식 설명용 합성 값):

```json
{
  "active": true,
  "inputType": "NARRATIVE",
  "scores": {"hol": 3,"task_1": 3,"content_1": 3,"content_2": 3,"content_3": 3,"organization_1": 3,"organization_2": 3,"expression_1": 3,"expression_2": 3},
  "rawScores": {"hol": 3.0,"task_1": 3.3,"content_1": 3.4,"content_2": 3.0,"content_3": 3.0,"organization_1": 3.3,"organization_2": 3.4,"expression_1": 3.5,"expression_2": 3.5},
  "model": {"name": "m2-klue-narrative","version": "2.0","revision": 1}
}
```

지연 측정(2.0, CPU x86_64·PyTorch 2.14.1+cpu·OMP/MKL 4스레드, 워밍업 3회 제외 30회, HTTP 포함, ms):

| 유형 | 글자 수 | 중앙값 | p95 | 최대 |
|---|---:|---:|---:|---:|
| NARRATIVE | 200 | 154 | 247 | 316 |
| NARRATIVE | 650 | 456 | 692 | 1139 |
| NARRATIVE | 1200 | 666 | 832 | 1683 |
| ESSAY | 200 | 153 | 227 | 308 |
| ESSAY | 650 | 407 | 505 | 726 |
| ESSAY | 1200 | 653 | 755 | 789 |

첫 서술형 준비 요청은 약 8.4초. AI LLM·learning 왕복을 더한 전체 35초 E2E는 별도이며 배포 CPU·동시성에 따라 재측정 필요. 재현은 `scripts/verify_scoring_m2.py`(인자는 1장 재현과 같음). 레플리카 두 개의 실제 M2 응답이 활성화·롤백 후 버전을 따라 바뀌는 것도 확인(#86 이관 항목).

## 4. M1 수학 검사 비활성 계약 (#88)

`POST /internal/m1/checks`, `X-Internal-Token` 필수.

```json
{
  "problem": "2 더하기 3은?",
  "answerKey": "5",
  "solution": {"steps": ["2에 3을 더합니다."], "finalAnswer": "5"}
}
```

- problem = 미션 문제, answerKey = 정답 키 finalAnswer, solution = 학생 풀이. 문자열 타입·필수 항목·공백 입력·steps 배열·알 수 없는 항목 검증. 단계 순서·빈 슬롯은 보존하되 내용 있는 단계가 하나 이상 필요
- 유효 요청 200 `{active:false}`, 인증 누락·불일치 401, 입력 오류 400 RFC 9457
- 승인된 M1 추론기가 없으므로 모든 입력이 비활성. M2로 대체하거나 정답 문자열만 비교하지 않음. core 메타데이터 등록만으로 활성화하지 않음. 실제 추론이 없으므로 M1 사용량도 발행하지 않음
- 후속 활성화: 학습 모델·사용법·승인 scope·활성 응답 필드와 단계 번호 기준 확정 후. 신뢰도 0.8 미만이면 scoring이 실수 위치를 숨기고 AI가 보류 결정. 실제 장애는 503으로 전달하고 `active:false`로 바꾸지 않음

## 5. M1 학습·평가 코드 `ml/m1` (#263)

저장소 밖 로컬 MVP 폴더에만 있던 M1 학습·평가 코드를 architecture 5장("모델 학습 코드는 `ml/`")과 NFR-AIQ-04("실험 실행 기록")에 맞춰 `ml/m1`로 이관. 목적은 코드 보존·재현이며 M1 본 학습은 범위 밖(국어(M2) 우선, [planning-decisions](planning-decisions.md)).

| 항목 | 결정 | 근거 |
|---|---|---|
| 범위 | 코드 이관만. M1 라벨 확인·전체 학습은 하지 않음 | #213 |
| 평가용 함수 | `build_model`과 함께 `available`·`meta`·`predict_many`(+`_load`)도 이관. 앱 전용 1건 예측 `predict()`와 `judge_route` 전환만 제외 | `evaluate.py`가 사용. 학습·평가는 `ml/`, 서비스 추론만 scoring |
| EDA 리포트 출력 | 기본 출력을 커밋하지 않는 `work/reports/`로. `results/`에는 예시 절을 뺀 정리본만 | `eda.py`가 AI Hub 풀이 원문 예시 절을 만듦(NFR-DAT-03) |
| CI | `ci-ml-m1.yml`(`ci-ml-m2.yml`과 같은 방식) | PR마다 자동 검사 |
| `ml/m2`와 공유 코드 | 없음 | — |

- 구성: `scripts/`(`common.py`·`eda.py`·`prepare.py`·`evaluate.py`·`train.py`·`mathtext.py`·`model.py`), `tests/test_m1.py`, `results/`(`eval_m1.md`, 예시 절 제외 `eda_71716.md`), `pyproject.toml`·`uv.lock`(torch 2.14.1, transformers 5.20.2, tokenizers 0.23.3, python-dotenv 1.2.4). 데이터 경로는 `data/71716`(`AIHUB_71716_DIR`), 가공본 `work/`, 가중치 `models/`
- 넣지 않은 것: AI Hub 71716 원본 zip, 가공본 `records.csv`, EDA 예시 절, 가중치 `models/m1/`(코드 확인용 실행이라 학습된 모델 아님, 승인 가중치는 S3)
- 검증: 실제 라벨링 zip 16개로 `eda.py` → `prepare.py` → `evaluate.py` 재실행 결과가 로컬 MVP 결과와 바이트 단위로 같음(177,796건, 그룹 단위 분할 train 142,710 / val 18,173 / test 16,913, test 균형정확도 다수 클래스 0.500·규칙 0.642·0.703)

알려진 한계:

- 학습된 M1 모델 없음, 허용 기준도 미정
- 풀이 과정 라벨 뜻이 불분명("필수 과정 실수 있음" 83%로 정답 비율 72%보다 높음, 계산 정확도에 0.5 값 없음) → 본 학습 전 AI Hub 문서 확인 필요
- scoring에서 M1을 구현하면 `build_model`·`model_input` 구조가 두 곳에 생김. `meta.json`의 `input_format`(`mathtext.model_input-v1`)으로 맞춤
- `results/eda_71716.md`는 수동 정리본이라 EDA 재실행 시 자동 갱신되지 않음
- 학습 데이터는 손글씨 OCR 텍스트, 앱 입력은 직접 입력이라 분포가 다름
