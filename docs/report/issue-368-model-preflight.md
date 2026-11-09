# #368 모델 사전 검사

## 구현

최신 develop `17508815`(#409·#410 병합)를 반영한 `feature/368-model-preflight`에서 작업했다. 기존 #367 등록 API·평가 근거·활성화 흐름을 유지하고 읽기 전용 사전 검사 경로를 추가했다.

- scoring: `POST /internal/models/preflight`. 설정된 모델 버킷의 `models/` 경로만 허용한다. manifest의 여섯 파일을 중복 없이 받으며 존재·크기·SHA-256을 검사한다. `config.json`, `train_info.json`, `score_cuts.json`만 최대 1MiB씩 읽는다. 가중치와 tokenizer 본문은 받지 않는다.
- 메타데이터: 기존 `validate_metadata`로 학습 입력·항목·경계를 검사하고 config의 `num_labels` 또는 `id2label` 수와 regression 설정을 검사한다. 실제 가중치 shape·CPU 로딩·추론 확인은 이 검사의 범위가 아니다.
- core: SERVICE_OPS 관리자 `POST /api/v1/admin/models/preflight` → 기존 InternalRestClientFactory로 내부 토큰을 붙여 동기 중계한다. HTTP 20초, 재시도 없음. scoring은 15초 작업 예산·S3 연결/읽기 각각 1초·재시도 없음. 웹은 25초 후 요청을 중단한다.
- 감사: `MODEL_PREFLIGHT`의 `result=SUCCESS|FAILURE`, target_type=MODEL_VERSION, target_id=null(등록 전 검사). detail에 이름·버전·경로·manifest와 안전한 결과 코드만 저장한다. upstream 장애도 실패 이력으로 남기며 제공자 원문 오류·자격 증명은 반환하지 않는다. 기존 평가 JSONB에 결과를 섞지 않는다.
- web: JSON 미리보기 카드에서 manifest의 여섯 파일과 입력 검증을 통과해야 검사 버튼을 사용할 수 있다. 파일별 원인을 표시하고 입력이 바뀌면 이전 결과를 만료시킨다. 검사 성공으로 등록·승인·활성화하지 않는다.
- local·prod NetworkPolicy: core egress 8001 → scoring, scoring ingress에 core를 추가했다. 기존 ai 호출과 포트는 유지한다. Compose 및 local/prod core에 SCORING_URL을 추가했다.

## 체크섬과 AWS 확인 범위

[Amazon S3 HeadObject 계약](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)에 따라 `ChecksumMode=ENABLED`로 조회한다. 작은 JSON은 실제 바이트 SHA-256으로 대조한다. 나머지는 S3 전체 파일 SHA-256만 사용하고 ETag, 임의 사용자 metadata의 sha256, multipart COMPOSITE는 대체 근거로 인정하지 않는다. 전체 SHA-256이 없으면 `CHECKSUM_UNAVAILABLE`로 실패한다. 성공처럼 표시하거나 가중치 다운로드로 우회하지 않는다.

따라서 기존 AWS 객체가 multipart COMPOSITE이거나 SHA-256을 저장하지 않았다면 사전 검사가 실패할 수 있다. 객체를 임의로 다시 업로드하거나 운영 모델을 교체하지 않았다. 업로드 방식 보완이 필요하면 #212 담당자와 해당 객체 상태를 확인한 뒤 별도로 반영한다.

저장소의 `scoring-s3-read` IAM 정책은 s3:ListBucket·s3:GetObject를 허용한다. 사용 API는 HeadObject·GetObject이며 새 쓰기 권한은 필요 없다. JSON GET은 If-Match로 고정하여 GetObjectVersion 권한을 요구하지 않는다. SSE-KMS 객체의 checksum 조회에는 추가 KMS 권한이 필요할 수 있다. #212 문서의 Pod Identity·S3 Gateway 경로를 검토했고, 이번 작업에서 AWS 실제 IAM·객체 상태 조회 및 배포·정책 수정은 하지 않았다. NetworkPolicy YAML/JSON 검증은 실제 클러스터 통신 검증과 구분한다.

## 로컬 재현

새 일회용 MinIO 컨테이너만 사용한다. 아래 로그인 값은 테스트 전용이며 운영 자격 증명을 사용하지 않는다.

1. MinIO `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z`를 `127.0.0.1:58100:9000`으로 실행한다. MINIO_ROOT_USER=preflight-local, MINIO_ROOT_PASSWORD=preflight-local-test-only, 명령 `server /data`.
2. 저장소 루트에서 scoring Python 환경으로 `scripts/seed_model_preflight_local.py` 실행. localhost의 새 models 버킷에 합성 파일을 만든다. 이미 존재하는 버킷이면 덮어쓰지 않고 실패한다. 정상 prefix와 가중치가 없는 prefix를 만들고 output/issue368-request.json을 생성한다.
3. scoring 환경에서 INTERNAL_TOKEN=preflight-local-token, S3_ENDPOINT_URL=http://127.0.0.1:58100, S3_BUCKET=models, AWS_ACCESS_KEY_ID=preflight-local, AWS_SECRET_ACCESS_KEY=preflight-local-test-only를 지정한다. `python -m uvicorn tests.preflight_local_server:app --host 0.0.0.0 --port 58101`로 실행한다. 이 테스트 서버는 운영 라우터·인증을 쓰되 사전 검사와 무관한 AMQP/모델 로딩 시작만 생략한다.
4. JDK21·Docker 환경에서 core `test --tests '*ModelPreflightLocalIntegrationTest'` 실행. PREFLIGHT_LOCAL=true, PREFLIGHT_SCORING_URL=http://host.docker.internal:58101(Docker 밖이면 localhost), PREFLIGHT_REQUEST_FILE=<생성한 JSON의 테스트 환경 경로>. core 테스트 DB는 Testcontainers가 생성·삭제한다.
5. 결과는 정상 PASS, 모델 가중치 해시 불일치 FAIL/HASH_MISMATCH, 파일 누락 FAIL/FILE_MISSING. 감사 SUCCESS 1·FAILURE 2건, 등록 모델 0건을 검사한다. 종료 후 테스트 서버와 일회용 MinIO를 중지한다.

실제 모델 파일·등록 JSON·가중치와 운영 비밀 값은 커밋하지 않는다. 로컬 성공은 운영 품질 승인이나 활성화 승인이 아니다.


## 검증 결과 (2026-11-09)

- core: ModelPreflightHttpTest 4개 + 기존 ModelVersionHttpTest 12개, 합계 16개 및 bootJar 통과.
- 실제 local 연동: ModelPreflightLocalIntegrationTest 1개 통과. 실제 HTTP scoring·MinIO를 사용한 세 경우와 PostgreSQL 감사 저장 확인.
- scoring 전체 212개 통과 후 출력 수 모순 사례를 1개 추가하여 사전 검사 14개를 재검증했다. 총 213개 고유 테스트 검증. Ruff check·format 통과.
- web 단위 244개, 모델 브라우저 12개(데스크톱·태블릿·휴대폰), lint·test:types·build 통과. 새 사전 검사 테스트는 합성 HTTP 응답이며 실제 core/S3 검증과 구분한다.
- 저장소 계약 검증기 192개 통과. core/scoring 요청·응답 계약 일치, 양방향 local/prod NetworkPolicy, 기존 S3 읽기 정책 포함.
- AWS CLI와 kubectl의 현재 클러스터 연결이 없어 실제 Pod Identity 권한·객체 체크섬·운영 통신을 확인하지 않았다. AWS 미배포 상태이며 실제 실행 결과로 쓰지 않는다. GitHub CI도 별도 확인 대상이다.

## 이슈 원문 체크리스트 대응

### 해야 할 일
- [x] scoring `POST /internal/models/preflight`(가칭): name·version·artifactUri와 manifest `files[]`를 받아 6개 파일의 존재·크기·sha256 확인, 작은 JSON 3개(config.json·train_info.json·score_cuts.json)만 읽어 `validate_metadata`·출력 수 확인. 가중치는 받지 않음
- [x] core 관리자 API로 동기 중계(시간 제한 포함), core scoring 클라이언트 추가
- [x] 결과를 별도 감사 action(가칭 `MODEL_PREFLIGHT`, `result` SUCCESS·FAILURE)으로 기록. `evidence`에는 넣지 않음
- [x] NetworkPolicy: scoring ingress에 core 허용, core egress에 scoring 추가(`environments/local/scoring-service.yaml`·`core-service.yaml`, prod 구성도 확인)
- [ ] scoring S3 읽기 권한이 사전 검사 경로에 충분한지 #212 AWS 설정과 조율
- [x] web: 미리보기 카드에 "사전 검사" 버튼과 결과 표시(manifest 필요)
- [x] api-spec·OpenAPI 반영

AWS 항목은 저장소 IAM 정책과 #212 문서 검토까지 완료했다. 실제 권한·객체 checksum 상태 확인 및 필요한 경우 담당자 조율을 남겼으므로 전체 체크하지 않는다. AWS 자격 증명이나 운영 버킷을 임의로 변경하지 않는다.

### 완료 조건
- [x] scoring·core 테스트, web 테스트 통과
- [x] local 환경에서 정상 파일·해시 불일치·파일 누락 세 경우 결과 확인
- [x] AWS 반영 여부와 결과는 실제 실행한 것만 기록

### 유지할 원칙
- [x] 사전 검사 통과는 "파일·형식 확인"으로만 표시. 품질 승인·활성화 가능 상태로 표시하지 않고 자동으로 다음 단계로 넘기지 않음
