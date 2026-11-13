# scoring 모델 서비스·M1 학습 코드·모델 업로드

계약은 [API 명세 4.3](../design/api-spec.md#43-scoring-service-호출-ai)과 [scoring OpenAPI](../../contracts/openapi/scoring-service.yaml). 서술 3.0·논술 3.1 모델 호환과 content_3 보정은 [ai](ai.md) 4장.

| 이슈 | 구현 |
|---|---|
| #85 | core 활성 조회, S3/MinIO 다운로드·로딩, 실제 로딩 버전 조회, 승인 범위·readiness·재시도 |
| #86 | 모델 활성 이벤트, revision 순서, 교체 실패 시 기존 모델 유지, 재다운로드 롤백·재연결 |
| #87 | M2 서술형·논술형 채점, 컷 변환·소수 원점수·모델 식별정보, 사용량 발행 |
| #88 | M1 입력 계약, 인증·입력 검증, 미학습 상태 `active:false` |
| #140 | 브로커 연결 복구·readiness·종료, 이벤트 봉투 스키마, 내부 헤더·학생 scope·trace 전파, 설정 로딩 테스트 보강 |
| #228 | 서술 3.0(9출력)·논술 3.1(14출력 중 앞 3개) 호환, 논술 4~6학년([ai 4.1](ai.md#41-서술-30논술-31-서비스-호환-228)) |
| #263 | M1 학습·평가 코드를 `ml/m1`로 이관 |
| #493 | 모델 산출물 전체 SHA-256 업로드 절차, 기존 12개 객체 보완 |

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
| `app/model_sync.py` | 구독 세션마다 `ModelStartup`을 새로 만들고 scoring 대상 이벤트만 전달(#632, 소비자에서 분리) |

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
| 큐 연결 후 초기 조회 | consume 등록 전 `ModelSync.reset`으로 새 `ModelStartup`을 만들고, consume 등록까지 마친 다음 시작. 조회 중 수신 메시지는 메모리에 보존 |
| 순서 역전·중복 | 이름별 최신 이벤트 보존, `ModelRegistry`에서 revision 비교 |
| scoring 모델만 적용 | kind MODEL이며 `m2-`·`m1-` 이름인 항목만 전달 |
| 로딩 실패 | 기존 모델 유지·재시도. scope는 기존 모델과 최신 승인 범위의 교집합. 한 모델 실패가 다른 이름의 업데이트를 막지 않음 |
| 형식 오류 | 봉투·data 검증 실패 시 본문 없는 경고 후 ACK, 재시도 없음 |
| 재연결 | 이전 session 정리 → 새 큐 바인딩 → snapshot 재조회 |
| readiness | 최초 준비·재연결 조정 전 false. 빈 활성 목록은 준비 완료. 정상 기동 이후 교체 실패는 기존 모델 제공 유지 |
| 로그 | 모델명·revision·큐명·예외 유형만. 메시지 본문·artifact URI·자격 증명 미기록 |

### 소비자 계층 분리 (#632)

ai #254(`PromptSync`)와 같은 구조로, 소비자에 있던 세션별 `ModelStartup` 생성과 `scoring_versions` 필터·`offer` 전달을 `app/model_sync.py`의 `ModelSync`로 옮겼다. `messaging/consumer.py`는 구독·재연결, 봉투 검증, `ModelSync.offer`, ACK만 맡는다. 세션 순서(소비 등록 전 `reset` → 바인딩·소비 등록 → `start` → 종료 시 `stop`)와 readiness·이벤트 계약·로그는 그대로다. snapshot 조회·revision 조정 본체는 기존 `ModelStartup`에 남는다.

검증: `scripts/verify_scoring_events.py`가 격리된 core·RabbitMQ·MinIO·scoring 2개로 두 exclusive 큐·활성화·롤백 재다운로드·파일 누락 시 기존 버전 유지·브로커 중단 중 활성화 후 재연결 복구·임시 파일 정리를 확인(`2.1-check`는 같은 2.0 artifact를 가리키는 교체 검증용 메타데이터).

## 3. M2 채점 API (#87)

- 담당자 답변(10/29): 관리자 입력 → `rubric_version.keywords` → learning `question/keywords` → AI → scoring `prompt/text/grade/inputType/keywords`. 핵심어는 서술형만, 없으면 비활성. 실제 장애는 503·판정 처리 실패. `score_cuts.json`으로 컷 변환하고 소수 원점수도 보존, 서술형 content_3도 모델 점수 사용. 컷이 없거나 손상된 모델을 반올림으로 대체하지 않음
- `M2Service`는 기존 `ModelRegistry`·`LoadedModel` 재사용. 승인 scope는 `judgment/grade-5/narrative` 같은 정확 일치 값(문항 단위 승인은 요청에 문항 ID가 없어 범위 밖)
- 현재 활성 학년은 서술 초5·6, 논술 초4~6(#228). 모델/승인 범위 밖·핵심어 없는 서술형은 `active:false`
- 학습 메타데이터의 `max_length=512`, 회귀 head, dataset, 핵심어 설정 검사. 첫 문장에 학년·서술형 핵심어(논술은 글 종류), 글은 두 번째 문장으로 토큰화(`only_second`). 2.0 모델의 지시문 입력은 #228에서 제외
- `bisect_right(cuts, raw)+1`은 학습 `numpy.digitize(raw, cuts)+1`과 같은 경계 처리. 서술 hol 1~4·8항목 1~5, 논술 3.1은 org·cont·exp 0~3(+1 없음, ai 4.1). rawScores는 유한 원점수 그대로. 두 유형의 content_1~3 의미가 다르므로 inputType을 함께 반환하고 합산하지 않음
- CPU 작업은 `run_in_threadpool`, 서비스 단위 1개 동시 추론, 대기 최대 1초 이후 503. 추론 중 모델 교체 시 현재 요청은 캡처한 모델, 다음 요청은 새 버전
- 사용량 발행은 제한된 백그라운드 태스크(최대 128, 1초 제한), 실패해도 채점 응답은 성공. 원문·학생 정보 없이 service=scoring, callType=M2, 토큰 null, 지연·성공 여부. 브로커 중단 중에도 이미 로딩된 모델의 채점은 200
- 비활성은 `{"active":false}`만. 서비스는 점수를 DB에 저장하지 않음(`judgment.model_scores` 저장은 learning, ai 4장)

응답 예시(형식 설명용 합성 값, 2.0 서술 모델 기준. 3.0·3.1 응답 키는 ai 4.1):

```json
{
  "active": true,
  "inputType": "NARRATIVE",
  "scores": {"hol": 3,"task_1": 3,"content_1": 3,"content_2": 3,"content_3": 3,"organization_1": 3,"organization_2": 3,"expression_1": 3,"expression_2": 3},
  "rawScores": {"hol": 3.0,"task_1": 3.3,"content_1": 3.4,"content_2": 3.0,"content_3": 3.0,"organization_1": 3.3,"organization_2": 3.4,"expression_1": 3.5,"expression_2": 3.5},
  "model": {"name": "m2-klue-narrative","version": "2.0","revision": 1}
}
```

지연 측정(이전 2.0 모델 기록, CPU x86_64·PyTorch 2.14.1+cpu·OMP/MKL 4스레드, 워밍업 3회 제외 30회, HTTP 포함, ms):

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

저장소 밖 로컬 MVP 폴더에만 있던 M1 학습·평가 코드를 architecture 5장("모델 학습 코드는 `ml/`")과 NFR-AIQ-04("실험 실행 기록")에 맞춰 `ml/m1`로 이관. 목적은 코드 보존·재현이며 M1 본 학습은 범위 밖(국어(M2) 우선, [planning 2절](planning.md#2-국어m2-우선과-생각-유형-매핑-213)).

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

## 6. 모델 산출물 SHA-256 업로드 절차 (#493)

사전 검사([ai 12절](ai.md#12-모델-사전-검사-368))는 S3 전체 파일 SHA-256이 없으면 실패한다. 그 값을 남기는 업로드 방식을 2026-11-10에 정했다.

### 6.1 결정

| 항목 | 결정 |
| --- | --- |
| 업로드 | 파일마다 `aws s3api put-object` 한 번. 전체 원본 SHA-256을 `--checksum-sha256`으로 명시 |
| 체크섬 표현 | manifest는 소문자 16진수 64자리, S3 요청은 **32바이트 해시의 Base64**(16진수 문자열을 Base64로 바꾸지 않음) |
| 자동 multipart 금지 | `aws s3 cp/sync`, SDK 고수준 `upload_file`을 쓰지 않음. multipart SHA-256은 COMPOSITE라 검사 계약을 만족하지 못함 |
| 인정하지 않는 근거 | ETag·사용자 metadata·CRC 계열·COMPOSITE. `ChecksumType=FULL_OBJECT`만 있고 `ChecksumSHA256`이 없어도 불충분. 가중치 다운로드로 우회하지 않음 |
| 크기 한도 | 단일 PUT 5GB. 준비 도구는 5,000,000,000바이트까지만 허용, 넘으면 중단하고 별도 결정(현재 가중치 약 443MB) |
| 권한 | 업로드는 업로드 담당 자격 증명, scoring은 읽기 전용 유지. 사전 검사 PASS가 품질 승인·활성화를 뜻하지 않음 |

근거: [S3 체크섬 유형](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html), [업로드 크기 제한](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html), [PutObject CLI](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html).

### 6.2 로컬 준비 (AWS 접속 없음)

모델별로 [ModelPreflightRequest](../../contracts/openapi/scoring-service.yaml) 형식 JSON(`name`·`version`·`artifactUri`·manifest의 6개 `{file, bytes, sha256}`)을 준비한다. 해시를 현재 파일에서 새로 만들어 manifest를 덮어쓰면 원본 대조가 아니므로 하지 않는다. 필수 파일은 `config.json`, `tokenizer.json`, `tokenizer_config.json`, `train_info.json`, `score_cuts.json`, `model.safetensors`.

```powershell
$modelDir = (Resolve-Path '<모델 원본 폴더>').Path
$requestFile = (Resolve-Path '<사전 검사 요청 JSON>').Path
$modelBucket = 'sagomungchi-demo-347161580747-models'
$planFile = Join-Path $env:TEMP ('model-upload-' + [guid]::NewGuid() + '.json')

python scripts/prepare_model_upload.py --request $requestFile --model-dir $modelDir --expected-bucket $modelBucket --output $planFile
if ($LASTEXITCODE -ne 0) { throw '원본 대조 실패. 업로드하지 않음.' }
$uploadPlan = Get-Content -LiteralPath $planFile -Raw -Encoding UTF8 | ConvertFrom-Json
```

도구는 파일명 중복·누락, 대상 버킷·경로, 크기, 원본 SHA-256을 확인한 뒤 계획 JSON을 만든다. 네트워크 기능이 없고 기존 출력 파일을 덮어쓰지 않는다. 계획 파일에는 로컬 경로가 있어 커밋하지 않는다.

### 6.3 신규 키 업로드

`--if-none-match '*'`를 지원하는 AWS CLI v2 필요. **존재하지 않는 신규 키에만** 쓴다(기존 키에는 412로 중단되는 것이 정상). `--body`는 일반 파일 경로이며 `fileb://`를 붙이지 않는다.

```powershell
$uploadProfile = '<업로드 담당 AWS 프로필>'
$modelRegion = 'ap-northeast-2'
$bucketOwner = '347161580747'
$receiptDir = Join-Path $env:TEMP ('model-upload-receipts-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $receiptDir | Out-Null

foreach ($artifact in $uploadPlan.files) {
    $contentType = if ($artifact.file.EndsWith('.json')) { 'application/json' } else { 'application/octet-stream' }
    $putArgs = @(
        's3api', 'put-object', '--bucket', $uploadPlan.bucket,
        '--key', $artifact.key, '--body', $artifact.path,
        '--checksum-algorithm', 'SHA256', '--checksum-sha256', $artifact.checksumSHA256,
        '--if-none-match', '*', '--content-type', $contentType,
        '--expected-bucket-owner', $bucketOwner, '--region', $modelRegion,
        '--profile', $uploadProfile, '--output', 'json', '--no-cli-pager'
    )
    $putJson = & aws @putArgs
    if ($LASTEXITCODE -ne 0) { throw "PUT 실패: $($artifact.file). 후속 파일 중단." }
    $put = ($putJson -join "`n") | ConvertFrom-Json

    $headJson = & aws s3api head-object --bucket $uploadPlan.bucket --key $artifact.key --checksum-mode ENABLED --expected-bucket-owner $bucketOwner --region $modelRegion --profile $uploadProfile --output json --no-cli-pager
    if ($LASTEXITCODE -ne 0) { throw "HEAD 실패: $($artifact.file). 성공 처리하지 않음." }
    $head = ($headJson -join "`n") | ConvertFrom-Json
    $receipt = @{ file = $artifact.file; key = $artifact.key; put = $put; head = $head }
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $receiptDir ($artifact.file + '.receipt.json')) -Encoding UTF8
    if ($head.ContentLength -ne $artifact.bytes -or
        $head.ChecksumType -cne 'FULL_OBJECT' -or
        $head.ChecksumSHA256 -cne $artifact.checksumSHA256 -or
        $put.ChecksumSHA256 -cne $artifact.checksumSHA256) {
        throw "전체 SHA-256 확인 실패: $($artifact.file). 등록·활성화하지 않음."
    }
}
```

6개 파일은 하나의 트랜잭션이 아니다. 중간 실패 시 올라간 객체와 영수증을 보존하고 등록하지 않는다. 재실행의 412를 없애려고 객체를 지우거나 조건을 제거하지 않는다.

### 6.4 기존 키 보완

이미 올바른 전체 SHA-256이 있으면 재업로드하지 않는다. 기존 키를 읽는 서비스에 영향을 줄 수 있어 업로드 담당자와 키·시점·복구 책임을 먼저 맞춘다.

1. 현재 HEAD(`VersionId`·`ETag`·`ContentLength`·`ChecksumType`·Content-Type·Metadata)와 태그, 버킷 Versioning·암호화·객체 잠금·ACL 정책을 확인·보관
2. 승인된 manifest와 같은 로컬 원본을 6.2 도구로 확인. 크기·해시가 다르면 중단. 가중치·score_cuts 교체를 체크섬 보완에 섞지 않음
3. 파일별 `repair-put.json`으로 PUT. 신규 키의 `IfNoneMatch` 대신 **기존 HEAD의 `ETag`를 `IfMatch`**에(동시 변경 방지용이며 SHA-256의 대안 아님). Content-Type·Metadata 등 기존 속성 보존. HEAD 응답 전체를 PUT 입력으로 복사하지 않음(`LastModified`·`VersionId` 등은 PUT 인자가 아님)
4. 6.3과 같은 HEAD 대조 후 새 VersionId 기록. 같은 원본이면 모델 버전·등록·승인 scope를 바꾸거나 다시 활성화하지 않음
5. 문제가 생기면 보관한 이전 버전과 속성으로 복구

```powershell
$repairInput = (Resolve-Path '<검토한 repair-put.json>').Path
$artifactPath = (Resolve-Path '<해당 원본 파일>').Path
$repairJson = & aws s3api put-object --cli-input-json ("file://" + $repairInput) --body $artifactPath --region $modelRegion --profile $uploadProfile --output json --no-cli-pager
if ($LASTEXITCODE -ne 0) { throw '기존 객체 보완 실패. 후속 작업 중단.' }
```

### 6.5 실행 결과와 남은 검증 (2026-11-10)

- 서술 `m2-klue-narrative@3.0`·논술 `m2-klue-essay@3.1`의 12개 객체를 동일 원본으로 보완. 모두 `FULL_OBJECT` SHA-256과 manifest 일치, 기존 속성·이전 버전 보존. 키별 이전/새 VersionId는 [실행 증빙 JSON](evidence/issue493-s3-sha256-20261110.json)
- 버킷 상태: Versioning Enabled, BucketOwnerEnforced, AES256, 객체 잠금 없음
- CloudShell 운영자 자격 증명으로 `PreflightService.check`를 직접 실행해 두 모델 모두 `PASS / FILES_AND_METADATA_VERIFIED`(모델별 HEAD 6회·작은 JSON GET 3회). 배포 이미지·Pod 실행 결과가 아님
- EKS·RDS 재가동, IAM·버킷 정책 변경, 모델 등록·활성화는 하지 않음
- **남은 검증**(AWS 재가동 후): 실제 `app/scoring-service` Pod Identity로 읽기, 관리자 → core → scoring 경로의 사전 검사 PASS와 감사 기록

### 6.6 로컬 검증 방법

```powershell
python -m unittest discover -s scripts/tests -p test_prepare_model_upload.py -v
```

MinIO 통합 검증은 `127.0.0.1:58193`의 일회용 MinIO와 `MODEL_UPLOAD_LOCAL=true`가 있을 때만 실행된다(없으면 건너뜀).

```powershell
docker run --detach --rm --name issue493-upload-local --publish 127.0.0.1:58193:9000 --env MINIO_ROOT_USER=model-upload-local --env MINIO_ROOT_PASSWORD=model-upload-test-only quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z server /data
$env:MODEL_UPLOAD_LOCAL = 'true'
# backend/scoring-service 가상환경에서
python -m pytest tests/test_preflight.py tests/test_model_upload_local.py -q
Remove-Item Env:MODEL_UPLOAD_LOCAL
docker stop issue493-upload-local
```

MinIO의 체크섬 오류 코드는 `XAmzContentChecksumMismatch`로 AWS의 `BadDigest`와 이름이 다르다. 잘못된 SHA-256 PUT은 400·객체 미생성, 신규 키 중복 PUT과 오래된 `IfMatch`는 412.

## 7. M2 글 정리·b판 경계 (#549, 2026-11-12)

논술 3.1·서술 3.0에 c판 규칙과 앞+끝 토큰화를 적용한다. 논술은 정리 후 100자 미만, 서술은 10자 미만이면 추론하지 않는다. 서술 10~99자는 채점하며 짧은 답 안내를 전달한다. 원문·승인 학년·활성화 정책은 유지하고 8:2 혼합은 최종 미채택이다.

실제 모델·HTTP 검증, 조정된 체크리스트, 파일 해시, 적용·복귀 절차는 [#549 구현 보고서](issue-549-m2-guards.md)에 기록했다. b판 경계는 로컬 복사본에서 재로딩·복귀를 검증했으며 운영 S3 업로드·모델 활성화는 수행하지 않았다.
