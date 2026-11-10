# 모델 산출물 SHA-256 업로드 절차 (#493)

결정일: 2026-11-10. 관련: #368 / PR #413, #212.

**이번 작업은 업로드 방식 결정·로컬 준비 도구·검증까지다. AWS 재가동, S3 조회·업로드, IAM 변경, 모델 등록·활성화는 실행하지 않았다.** AWS 실서비스 사전 검사 PASS는 후속 작업으로 남긴다.

## 1. 결정과 적용 범위

| 항목 | 결정 |
| --- | --- |
| 업로드 | 파일마다 `aws s3api put-object` 한 번. 전체 원본 바이트 SHA-256을 `--checksum-sha256`으로 명시 |
| 체크섬 표현 | manifest는 소문자 16진수 64자리, S3 요청은 **32바이트 해시의 Base64**. 16진수 문자열 자체를 Base64로 바꾸지 않음 |
| 자동 multipart | 이 절차에서 `aws s3 cp/sync` 및 SDK의 고수준 `upload_file`을 사용하지 않음 |
| 현재 두 모델 | 서술 `m2-klue-narrative@3.0`, 논술 `m2-klue-essay@3.1`도 체크섬 보완 대상으로 결정. 새 버전만 적용하면 현재 모델의 사전 검사 실패가 남음 |
| 기존 객체 실행 조건 | #212 S3 담당자와 대상·실행 시점·복구 방법을 조율한 뒤 동일 원본으로 보완. **조율·재업로드 미실행** |
| 유지할 계약 | ETag·사용자 metadata·CRC 계열·SHA-256 COMPOSITE를 대체 근거로 인정하지 않음. 가중치 다운로드로 사전 검사를 우회하지 않음 |
| 권한·활성화 | 업로드는 기존 업로드 담당 자격 증명 사용. scoring은 읽기 전용 유지. 사전 검사 PASS가 품질 승인이나 활성화를 뜻하지 않음 |

단일 PutObject는 전체 객체 체크섬을 기록한다. SHA-256 multipart 결과는 COMPOSITE여서 현재 검사 계약을 만족하지 못한다. `ChecksumType=FULL_OBJECT`만 있고 `ChecksumSHA256`이 없어도 불충분하다. [S3 체크섬 유형](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html)

단일 PUT 한도는 5GB다. 기존 두 가중치는 각각 442,524,276 / 442,539,656바이트여서 범위 안에 있다([이전 AWS HEAD 기록](ai.md#127-aws-읽기-전용-확인-2026-11-09)). 준비 도구는 보수적으로 5,000,000,000바이트까지만 허용한다. 이를 넘으면 업로드를 중단하고 별도 방식을 결정한다. 자동 multipart나 체크섬 검사 완화로 전환하지 않는다. [S3 업로드 크기 제한](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)

## 2. 로컬 준비 — AWS 접속 없음

Python 3.12와 담당자가 보관한 모델 원본 6개, 신뢰할 수 있는 기존 manifest가 필요하다. 해시를 현재 파일에서 새로 만들어 manifest를 덮어쓰면 원본 대조가 아니므로 그렇게 하지 않는다.

모델별로 [ModelPreflightRequest 계약](../../contracts/openapi/scoring-service.yaml)에 맞는 JSON 한 개를 준비한다. 등록 JSON 전체나 manifest 전체를 그대로 입력하는 형식이 아니다.

| 요청 필드 | 값의 출처 |
| --- | --- |
| `name`, `version` | 등록할 모델의 이름·버전 |
| `artifactUri` | 등록 요청과 동일한 `s3://<모델 버킷>/models/<모델 경로>/` |
| `files` | 해당 모델 manifest의 6개 `{file, bytes, sha256}` 항목. 관리자 사전 검사에 보내는 값과 동일 |

필수 파일은 `config.json`, `tokenizer.json`, `tokenizer_config.json`, `train_info.json`, `score_cuts.json`, `model.safetensors`다. 파일 바이트·모델 버전·score_cuts를 바꾸는 작업이 아니다.

저장소 루트에서 실행한다. 아래 경로는 사용자가 보관한 원본·검토한 요청 파일로 지정한다.

```powershell
$modelDir = (Resolve-Path '<모델 원본 폴더>').Path
$requestFile = (Resolve-Path '<사전 검사 요청 JSON>').Path
$modelBucket = 'sagomungchi-demo-347161580747-models'
$planFile = Join-Path $env:TEMP ('model-upload-' + [guid]::NewGuid() + '.json')

python scripts/prepare_model_upload.py --request $requestFile --model-dir $modelDir --expected-bucket $modelBucket --output $planFile
if ($LASTEXITCODE -ne 0) { throw '원본 대조 실패. 업로드하지 않음.' }
$uploadPlan = Get-Content -LiteralPath $planFile -Raw -Encoding UTF8 | ConvertFrom-Json
```

도구는 파일명 중복·누락, 대상 버킷·경로, 파일 크기, 원본 SHA-256을 모두 확인한 뒤 계획 JSON을 만든다. 1MiB씩 읽으므로 가중치 전체를 메모리에 올리지 않는다. 작은 JSON 3개의 사전 검사 한도(1MiB)도 적용한다. 기존 출력 파일을 덮어쓰지 않으며 네트워크 기능·AWS SDK 의존성이 없다. 계획 파일에는 로컬 원본 경로가 포함되므로 Git에 커밋하지 않는다.

계획은 업로드 또는 사전 검사 성공 결과가 아니다. 업로드 전 파일이 바뀌면 S3도 제공된 체크섬과 본문을 대조해 거부한다. 로컬 원본을 보관한 채 그대로 사용한다.

## 3. 신규 키 업로드 — 이후 AWS 작업 시 실행

**아래는 앞으로 승인된 AWS 작업에서 사용할 명령이며 이번 작업에서는 실행하지 않았다.** `--if-none-match '*'`를 지원하는 AWS CLI v2가 필요하다. 업로드 담당 프로필·계정·버킷·암호화 설정을 먼저 확인한다. API 인자와 본문 파일 경로 형식은 [PutObject CLI](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html)를 따른다.

이 명령은 **존재하지 않는 신규 키에만** 쓴다. 이미 존재하는 3.0/3.1 객체에는 412로 중단되는 것이 정상이다. 기존 객체 보완은 4절을 따른다. `--body`는 일반 파일 경로이며 `fileb://`를 붙이지 않는다.

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
    $receiptPath = Join-Path $receiptDir ($artifact.file + '.receipt.json')
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    if ($head.ContentLength -ne $artifact.bytes -or
        $head.ChecksumType -cne 'FULL_OBJECT' -or
        $head.ChecksumSHA256 -cne $artifact.checksumSHA256 -or
        $put.ChecksumSHA256 -cne $artifact.checksumSHA256) {
        throw "전체 SHA-256 확인 실패: $($artifact.file). 등록·활성화하지 않음."
    }
}
```

6개 파일은 하나의 트랜잭션이 아니다. 중간 실패 시 일부가 올라갈 수 있다. 성공한 객체와 영수증을 보존하고 등록하지 않는다. 재실행의 412를 없애려고 객체를 지우거나 조건을 제거하지 말고, 기존 객체는 4절 기준으로 확인한다. `BadDigest`, 403, 409, 412 및 HEAD 불일치는 원인을 확인한 뒤 다시 계획한다.

## 4. 기존 서술 3.0·논술 3.1 객체 보완

**결정: 기존 두 모델도 보완한다. 실행: #212 담당자 조율 전이므로 미실행.** 앞서 확인한 12개 파일에 전체 SHA-256을 기록하되, 실제 실행 시 이미 올바른 값이 있으면 재업로드하지 않는다.

1. 업로드 담당자와 모델별 6개 키·실행 시점·동시 업로드 중단·복구 책임을 맞춘다. 기존 키를 읽는 서비스에 영향을 줄 수 있으므로 독단적으로 덮어쓰지 않는다.
2. 현재 HEAD와 태그, 버킷 Versioning, 암호화·객체 잠금·소유권/ACL 정책을 확인·보관한다. `VersionId`, `ETag`, `ContentLength`, `ChecksumType`, `ChecksumSHA256`과 Content-Type·사용자 Metadata 등을 남긴다. 11/09 기록은 AES256이었지만 실행 시 다시 확인한다. Versioning이 없으면 검증된 원본과 메타데이터로 복구할 방안을 담당자와 먼저 확보한다. 이 절차 자체로 버킷 정책이나 Versioning을 바꾸지 않는다.
3. 승인된 기존 manifest와 동일한 로컬 원본을 2절 도구로 확인한다. 크기나 해시가 다르거나 원본을 확보하지 못하면 중단한다. 가중치·score_cuts 교체를 체크섬 보완으로 섞지 않는다. 기존 S3 ETag만으로 원본 동일성을 주장하지 않는다.
4. 파일별 `repair-put.json`을 검토하여 아래 명령에 사용한다. 신규 키의 `IfNoneMatch` 대신 **기존 HEAD의 `ETag`를 그대로 `IfMatch`**에 넣는다. ETag는 동시 변경 방지용일 뿐 SHA-256의 대안이 아니다. 현재 객체가 바뀌어 409/412가 나면 새 상태를 검토한다.

| `repair-put.json` 필드 | 설정 |
| --- | --- |
| `Bucket`, `Key`, `ExpectedBucketOwner` | 검토한 버킷·키·소유 계정 |
| `ChecksumAlgorithm`, `ChecksumSHA256` | `SHA256`, 준비 도구의 Base64 값 |
| `IfMatch` | 보관한 HEAD의 ETag(따옴표 포함 원값). `IfNoneMatch`와 함께 쓰지 않음 |
| `ContentType`, `Metadata` 및 나머지 속성 | 기존 값 보존. ContentEncoding·CacheControl·ContentDisposition·ContentLanguage·Expires·StorageClass·WebsiteRedirectLocation 등 존재하는 값 확인 |
| `Tagging`, 암호화·잠금·ACL 관련 인자 | HEAD만으로 태그·ACL을 알 수 없으므로 별도 조회 후 담당자가 보존 방법 확인. KMS·객체 잠금 등 특수 설정을 누락한 일반 명령으로 실행하지 않음 |

HEAD 응답 전체를 PUT 입력으로 복사하면 안 된다. `LastModified`, `VersionId` 등 PUT에서 받지 않는 필드가 있다. `repair-put.json`은 비밀 키를 담지 않는 API 인자 파일이며, JSON의 따옴표를 보존하도록 `--cli-input-json`을 사용한다.

```powershell
# 해당 파일의 속성·태그·복구 방법 조율이 끝난 이후에만 사용한다.
$repairInput = (Resolve-Path '<검토한 repair-put.json>').Path
$artifactPath = (Resolve-Path '<해당 원본 파일>').Path
$repairJson = & aws s3api put-object --cli-input-json ("file://" + $repairInput) --body $artifactPath --region $modelRegion --profile $uploadProfile --output json --no-cli-pager
if ($LASTEXITCODE -ne 0) { throw '기존 객체 보완 실패. 후속 작업 중단.' }
```

5. 각 파일에 대해 3절과 같은 HEAD 크기·`FULL_OBJECT`·전체 SHA-256 대조를 수행하고 PUT 응답·새 VersionId를 기록한다. 6개가 모두 확인된 모델만 사전 검사 대상으로 삼는다. 같은 원본이면 모델 버전·등록·평가·승인 scope를 변경하거나 다시 활성화하지 않는다.
6. 문제가 생기면 보관한 이전 버전/검증 원본과 속성으로 복구한다. 이전에 SHA-256이 없었던 상태로 돌아간 경우 사전 검사는 계속 실패하는 것이 정상이며 성공으로 표시하지 않는다. 복구 중 신규 객체를 무조건 삭제하지 않는다.

## 5. AWS 재가동 후 남은 실서비스 검증

업로드 담당자 HEAD 성공은 실제 scoring Pod 검증을 대체하지 못한다. [HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)는 `ChecksumMode=ENABLED`로 조회해야 하며, SSE-KMS를 쓰면 KMS 권한도 확인해야 한다. scoring에 업로드 권한을 추가하지 않는다.

- [ ] #212 담당자와 기존 객체 보완 시점·복구 방법 조율 및 필요 객체 재업로드
- [ ] AWS 재가동 후 실제 `app/scoring-service` Pod의 Pod Identity 자격 증명으로 읽기 확인
- [ ] 실제 관리자 → core → scoring 경로로 서술 3.0·논술 3.1 사전 검사 실행, 두 모델 모두 `PASS / FILES_AND_METADATA_VERIFIED`
- [ ] 6개 HEAD와 작은 JSON 3개 GET만 사용하는 계약 유지, tokenizer·가중치 본문 다운로드로 우회하지 않음
- [ ] 실제 실행 일시·배포 이미지/커밋·Pod·모델별 파일 검사 코드·감사 결과 기록. 인증 토큰·자격 증명은 기록하지 않음

현재 상태는 **AWS 실서비스 검증 미실행**이다. 로컬 테스트 결과는 아래에 별도로 기록하며, 위 체크박스는 실행 근거가 생기기 전까지 유지한다.

## 6. 로컬 검증

2026-11-10 로컬 실행 결과. 운영 모델 원본 대신 합성 파일과 일회용 MinIO를 사용했다. **AWS CLI를 통한 실제 S3 업로드·Pod Identity·네트워크 검증 결과가 아니다.**

| 검증 | 결과 |
| --- | --- |
| 준비 도구 단위/CLI 테스트 | 11개 통과. 원본 해시·크기 불일치, 누락/중복/위험 경로, 과대 파일, 기존 출력 덮어쓰기 거부 |
| 저장소 계약·스크립트 회귀 | 225개 실행, 224개 통과·기존 조건부 1개 제외(`learning #438 테마 초안 계약 미반영`). 위 도구 11개 포함 |
| scoring 기존 사전 검사 | 14개 통과. SHA-256 누락·COMPOSITE 거부 등 기존 계약 유지 |
| localhost MinIO 실제 연동 | 2개 통과(1,024바이트 / 442,539,656바이트 합성 가중치). 각 6개 단일 PUT → HEAD 전체 SHA-256·크기 일치 → 기존 사전 검사 PASS |
| MinIO 실패/경합 처리 | manifest 해시 변경 시 HASH_MISMATCH, 잘못된 SHA-256 PUT은 400 및 객체 미생성, 신규 키의 중복 PUT·오래된 IfMatch는 412, 일치하는 IfMatch는 성공 |
| 본문 읽기 범위 | 사전 검사 HEAD 6개, 작은 JSON 3개만 GET. tokenizer·가중치 GET 없음 |
| 정적 검사 | 변경 Python 파일 Ruff check·format, 문서 PowerShell 5개 블록 구문 검사, `git diff --check` 통과 |

MinIO의 체크섬 오류 코드는 `XAmzContentChecksumMismatch`였다. AWS 문서의 `BadDigest`와 오류 명칭이 같다고 기록하지 않는다. 실제 모델 로딩·추론·품질 평가는 이번 테스트 대상이 아니다.

준비 도구와 계약 검증은 저장소 루트에서 실행한다(Python 환경에 PyYAML·jsonschema 필요).

```powershell
python -m unittest discover -s scripts/tests -p test_prepare_model_upload.py -v
python -O -m unittest discover -s scripts/tests -v
```

MinIO 통합 검증은 scoring 개발 환경과 Docker가 있는 로컬 PC에서 명시적으로 실행한다. 테스트는 AWS 환경 변수를 사용하지 않고 `127.0.0.1:58193`과 테스트 전용 자격 증명에 고정되어 있다. 임의 이름의 테스트 버킷·객체만 생성·삭제하며, 일반 pytest/CI에서는 아래 환경 변수가 없으면 2개를 건너뛴다.

```powershell
docker run --detach --rm --name issue493-upload-local --publish 127.0.0.1:58193:9000 --env MINIO_ROOT_USER=model-upload-local --env MINIO_ROOT_PASSWORD=model-upload-test-only quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z server /data
if ($LASTEXITCODE -ne 0) { throw '일회용 MinIO 시작 실패. 기존 컨테이너를 제거하지 않음.' }
try {
    $minioReady = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:58193/minio/health/ready' -TimeoutSec 2 -ErrorAction Stop | Out-Null
            $minioReady = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $minioReady) { throw 'MinIO가 준비되지 않음' }
    $env:MODEL_UPLOAD_LOCAL = 'true'
    # backend/scoring-service에서 해당 가상환경 Python으로 실행
    Push-Location backend/scoring-service
    try {
        python -m pytest tests/test_preflight.py tests/test_model_upload_local.py -q
        if ($LASTEXITCODE -ne 0) { throw '로컬 통합 검증 실패' }
    } finally { Pop-Location }
} finally {
    Remove-Item Env:MODEL_UPLOAD_LOCAL -ErrorAction SilentlyContinue
    docker stop issue493-upload-local
}
```

테스트 후 일회용 컨테이너를 정리한다. 약 443MB 테스트는 로컬 디스크 공간이 추가로 필요하다. AWS 리소스를 시작하는 명령은 포함하지 않는다.
