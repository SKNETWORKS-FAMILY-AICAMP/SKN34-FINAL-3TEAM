# #367 모델 등록 API — 프론트 전달 문서

## 작업 범위와 연결 기준

백엔드 브랜치: `feature/367-model-registration-backend`. 기준 develop: `239fc8cc`.
#366 완료 여부와 무관하게 이 계약으로 목업을 만들 수 있다. #367의 프론트 구현·웹 타입·실제 두 파일 가져오기 테스트는 별도다. 전체 #367 완료나 운영 활성화를 의미하지 않는다.

- API: `POST /api/v1/admin/model-versions`, SERVICE_OPS 관리자 Bearer 인증
- 기존 등록 경로를 그대로 사용한다. JSON 업로드·일괄 등록 엔드포인트는 없다.
- 서버 계약 원본: [core OpenAPI](../../contracts/openapi/core-service.yaml)의 RegisterModelVersion, EvaluationEvidence, ModelRegistrationMetadata, ModelRegistrationArtifact
- 화면 변경 순서: #366 카드별 입력 분리 이후 #367 가져오기 화면을 연결하는 것을 권장한다. 백엔드는 기다릴 필요 없다.

## 파일을 읽고 요청을 만드는 순서

1. registration_1103.json 원본 바이트를 읽어 SHA-256을 계산한다. `file.arrayBuffer()` → `crypto.subtle.digest('SHA-256', buffer)` → 소문자 16진수 64자리. BOM·공백·개행을 포함한 원본 파일 그대로이며 파싱/재직렬화한 JSON으로 계산하지 않는다.
2. 파싱한 requests[]를 모델별 카드로 만든다. 최상위 설명(title/version/date/author/주의/<버킷>)은 POST 본문에 보내지 않는다. requests[]의 승인 관련 값이나 알 수 없는 필드는 가져오기 단계에서 거부한다.
3. 선택한 manifest도 원본 바이트로 해시한다. name/version/scope를 대조하고 해당 모델 files[]만 고른다. manifest가 없으면 manifestSha256 생략, artifactFiles는 []다.
4. 버킷을 치환하고 limitations를 확인한다. 항목에 evaluation.limitations가 있으면 빈 배열도 그 값을 유지한다. 없으면 registration 최상위 주의와 해당 모델 manifest 주의를 후보로 제시해 확인·수정한다.
5. 원본 항목과 최종 등록 값이 다른 필드 경로를 modifiedFields에 중복 없이 기록한다. 버킷 치환도 artifactUri 변경이다. limitations 후보를 새로 넣었으면 evaluation.limitations를 포함한다. 배열은 원소 인덱스가 아닌 배열 필드 경로 하나로 기록한다.
6. 운영자가 개별 등록을 누르면 requests[i]의 등록 필드에 아래 registration 메타데이터를 붙여 POST한다. 성공한 카드만 등록 완료로 표시한다. 실패한 카드 때문에 성공한 레코드를 다시 보내거나 덮어쓰지 않는다.

## 요청 예시

아래는 **합성 예시**다. a/b/c 반복 해시는 형식 설명용이며 실제 파일의 해시가 아니다. 실제 운영 모델을 다시 등록하지 않는다.

```json
{
  "kind": "MODEL",
  "name": "synthetic-model",
  "version": "1.0",
  "artifactUri": "s3://example-models/models/synthetic-model/1.0/",
  "evaluation": {
    "datasetId": "synthetic-eval",
    "datasetVersion": "1",
    "baselineVersion": "synthetic-baseline",
    "comparisonReport": "synthetic/comparison",
    "trainingEvaluationSeparation": "synthetic/split",
    "quoteAccuracy": "synthetic/quotes",
    "calculationAccuracy": "synthetic/calculations",
    "humanReview": "synthetic/review",
    "evaluatedScopes": [
      "judgment/grade-5/narrative"
    ],
    "limitations": [
      "연동 테스트용 합성 자료이며 품질 승인 근거가 아님"
    ]
  },
  "registration": {
    "source": "JSON_IMPORT",
    "jsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "manifestSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "modifiedFields": [
      "artifactUri",
      "evaluation.limitations"
    ],
    "artifactFiles": [
      {
        "file": "config.json",
        "bytes": 123,
        "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
      }
    ]
  }
}

```

수동 등록은 같은 필드에서 registration을 생략하면 된다. limitations도 생략 가능하며 []로 처리한다. 추가된 registration 정보는 평가 근거에 섞지 않고 등록 감사 detail에만 저장한다.

## 입력 규칙

| 필드 | 규칙 |
|---|---|
| artifactUri | MODEL이면 필수·공백 불가, 최대 2,048자. 경로 형식 경고·자리표시자 차단은 프론트 담당 |
| evaluation.limitations | 선택, 생략 시 [], 최대 100개, 항목마다 1~4,000자·공백/null 불가 |
| registration.source | MANUAL 또는 JSON_IMPORT. 생략 시 MANUAL |
| jsonSha256 | JSON_IMPORT이면 필수, registration 원본 파일 해시 |
| manifestSha256 | 선택 manifest 원본 파일 해시. artifactFiles가 있으면 필수 |
| modifiedFields | 최대 100개·중복 불가. 아래 필드 경로만 허용 |
| artifactFiles | 선택한 모델의 manifest files[], 최대 100개. 파일 경로 중복 불가 |
| artifactFiles[].file | 1~255자 상대 경로. 절대 경로·역슬래시·콜론·빈 경로 조각·.·.. 금지 |
| artifactFiles[].bytes | 파일 크기, 0 이상 정수 |
| artifactFiles[].sha256 | manifest의 해당 파일 SHA-256, 소문자 64자리 |

MANUAL에는 JSON/manifest 해시와 비어 있지 않은 modifiedFields·artifactFiles를 보내지 않는다.

modifiedFields 허용값:

```text
kind, name, version, refId, artifactUri,
evaluation.datasetId, evaluation.datasetVersion, evaluation.baselineVersion,
evaluation.comparisonReport, evaluation.trainingEvaluationSeparation,
evaluation.quoteAccuracy, evaluation.calculationAccuracy, evaluation.humanReview,
evaluation.evaluatedScopes, evaluation.limitations
```

기존 평가 근거 8개 문자열과 evaluatedScopes는 계속 필수다. RUBRIC만 refId를 필수로 받으며 다른 종류는 refId를 보내지 않는다. 알려지지 않은 모델 이름·scope 후보·버전 형식·모델 저장 경로 형태의 경고는 기존 #367 프론트 요구사항대로 구현한다. core는 새 scope를 임의로 차단하지 않는다.

## 성공 응답과 화면 연결

201 응답은 기존 ModelVersion이다. 목록 조회도 같은 객체를 반환한다.

```text
id, kind, name, version, refId, artifactUri,
evalResult: {
  evidence: { 기존 평가 필드, limitations: [...] },
  approval: null,
  activeScopes: [],
  revision: 0
},
status: REGISTERED,
approvedBy: null,
activatedAt: null,
createdAt
```

- 요청은 evaluation.limitations, 응답은 evalResult.evidence.limitations로 위치가 다르다.
- 구버전 DB 행에 limitations가 없어도 목록에서 []로 읽힌다. DB 마이그레이션·기존 평가 근거 덮어쓰기는 없다.
- registration 메타데이터는 ModelVersion 응답에 추가하지 않는다. 기존 MODEL_REGISTER 감사 detail에 source/jsonSha256/manifestSha256/modifiedFields/artifactFiles로 저장한다. 현재 감사 목록 API는 detail을 반환하지 않으므로 #366 감사 펼쳐보기에서 사용할 때는 해당 조회 응답 보강이 필요하다(이번 #367 등록 저장과 별도).
- 등록자·ID·시각·상태는 서버가 정한다. 등록으로 approval·ACTIVE·활성화 이벤트가 생성되지 않는다.
- 해시·파일 크기는 프론트가 신고한 출처 기록이다. 백엔드는 파일 원문을 받지 않으므로 실제 파일 해시 일치·S3 존재·로딩·품질 승인을 확인했다고 표시하면 안 된다. 사전 검사는 후속 범위다.

## 오류 표시

| HTTP·code | 프론트 처리 |
|---|---|
| 400 VALIDATION_FAILED | 잘못된 JSON/타입·알 수 없는 필드·승인 관련 필드. 폼 상단 오류, 원본/요청 구조 확인 |
| 401 / 403 | 기존 인증·SERVICE_OPS 권한 처리 |
| 409 MODEL_VERSION_CONFLICT | kind/name/version 중복. 해당 카드 이름·버전 입력에 안내. 기존 평가를 덮어쓰지 않음 |
| 422 MODEL_APPROVAL_REJECTED | MODEL 경로 누락, 불완전 평가/범위, 잘못된 limitations·감사 메타데이터. 폼 상단에 서버 메시지 |

공통 RFC 9457 형식은 바꾸지 않는다. title/detail/code/traceId 처리는 기존 API 클라이언트를 재사용한다. 서버가 필드별 errors 배열을 준다고 가정하지 않는다. UI의 상세 필드 오류는 브라우저 사전 검증에서 표시한다.

## 인계 후 공동 확인

- [ ] #366 화면 변경을 반영한 #367 프론트 및 웹 타입 연결
- [ ] 실제 11/03 registration·manifest를 로컬에서 가져오기 → 버킷 치환 → 개별 등록
- [ ] 성공/중복/부분 실패 카드 상태와 수정 표시 확인
- [ ] limitations 미리보기·목록·승인 확인 창 표시
- [ ] 프론트 lint/test/test:types/build·브라우저 테스트

운영의 기존 서술 3.0·논술 3.1은 재등록하거나 활성화하지 않는다. JSON 원본·실제 모델 파일은 이 변경에 포함하지 않는다.
