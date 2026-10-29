# #85 scoring 모델 레지스트리·S3 로딩

> 2026-10-29 사용자 제공 `m2_models_2.0.tar`로 실제 서술형·논술형 2.0 모델의 로컬 MinIO 로딩과 활성 버전 조회를 검증했다. 최신 결과는 아래 **실제 팀 2.0 모델 검증** 절을 참고한다. 2026-10-28 합성 모델 결과는 당시의 기록으로 보존한다.

목적: core가 승인한 버전만 scoring에 로딩하고, 실제 사용 버전과 준비 상태를 조회할 수 있게 한다. 최초 구현 기준은 develop `40a2501223defd69bcc55595643a6fecf81e9df3`이며, 2026-10-28 문서 정합성 PR #92가 병합된 `1f713607f9cec510edbe14730a82d5d0fbbd2745`를 작업 브랜치에 반영한 뒤 재검증했다.

## 이번 구현 기준

2026-10-28 사용자가 활성 모델이 없으면 준비 완료, 최초 로딩 실패는 준비 안 됨 상태로 재시도, 교체 실패는 기존 모델 유지로 결정했다. 기존 내부 httpx 클라이언트·Settings·readiness_checks·AMQP 수명 주기를 재사용한다. 모델 이름·버전은 core snapshot을 그대로 사용하며 임의의 활성 모델·승인 범위를 만들지 않는다.

API 변경은 [API 명세 4.3](../design/api-spec.md)에 먼저 기록했다. `/internal/versions`는 `{items:[{name,version,revision}]}`이며 실제 로딩된 버전만 표시한다. scope는 정확 일치로 제한하고, 최신 승인 범위가 줄어들면 교체 실패 시에도 범위를 확장하지 않는다.

## 최신 develop 문서 정합성 반영

- #92는 문서·OpenAPI·계약 검사를 정리했다. 이 업데이트에 scoring/core 런타임 소스, M2 학습 코드, Compose 변경은 없었으며 #85의 snapshot·revision·scopes 계약은 유지됐다.
- 변경 중인 #85 파일을 보관한 뒤 develop을 fast-forward 병합하고 복원했다. API 명세·클래스 다이어그램도 충돌 없이 병합됐다.
- 구현한 경로만 담는 [scoring OpenAPI](../../contracts/openapi/scoring-service.yaml)를 추가했다. 응답 DTO에서 생성한 스키마, 실제 라우터, 내부 인증 오류를 계약 테스트로 대조하고 계약 파일 변경도 scoring CI를 실행하도록 연결했다.
- API 명세와 클래스 다이어그램에 #85 구현 범위와 #86~88 후속 범위를 구분했다. 관리자 프론트 계약 불일치 #93 등 별도 이슈를 이번 구현에 포함하지 않았다. Docker 검증에서는 실제 core HTTP API를 직접 사용했다.

## 경계와 후속 작업

사용자 지시에 따라 개인 에픽 브랜치를 사용하지 않고 기존 이슈별 방식으로 진행한다. #85 작업은 `feature/scoring-model-registry`에 보존했으며 PR 대상은 `develop`이다. [상위 에픽 #84](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/84)는 #85~88 각각의 완료 조건을 확인한 뒤 종료한다. 실제 팀 모델을 기다리던 보류는 2026-10-29 사용자 제공 파일로 재개했다. 이번 검증 결과는 로컬에만 저장하며 PR·push·이슈 종료는 하지 않는다.

- #85: snapshot 조회·S3 다운로드·CPU 모델 로딩·revision 비교·scope 검사·readiness·버전 조회.
- #86: 큐 바인딩 → snapshot → 초기 이벤트 조정, 실제 활성화 이벤트·재연결. 롤백은 #85와 같은 S3/MinIO 재다운로드 방식으로 진행하기로 확정했다. #85의 다운로드 작업 디렉터리는 영속 롤백 캐시가 아니다.
- #87: 학년/입력 유형의 scope 매핑, 점수 API·사용량 발행, 입력 구성·점수 후처리. 현재 develop의 base/반올림 기준을 개선 모델 채택 결정으로 대체하지 않는다.
- #88: M1 모델 형식과 로더. 학습된 M1이 없는 상태에서 M2 로더를 M1에 대신 적용하지 않는다.
- 모델 파일 확보: 서술형·논술형 2.0 체크포인트·토크나이저·train_info.json·score_cuts.json을 받았다. 서술형 `with_keyword=True`, 논술형 `False`와 점수 경계값을 #87에서 입력·후처리에 반영해야 한다. 로컬 검증 URI를 운영 S3 경로나 서비스 채택 승인으로 간주하지 않는다.

## 검증

2026-10-28 로컬 구현·검증을 수행했다. 아래 결과는 #85 구현의 검증 기록이며, 에픽 전체 완료나 실제 팀 모델 검증 완료를 의미하지 않는다. AI Hub 데이터·학습 가중치를 저장소에 추가하지 않았다.

| 확인 항목 | 결과 |
|---|---|
| `uv run ruff check .` | 통과 |
| `uv run ruff format --check .` | 통과 |
| `uv run pytest -q` | Windows 전체 52개 통과. 대역 기반 경계 검사·CPU 텐서·실제 FastAPI 응답과 OpenAPI 계약 검사 포함 |
| Linux 컨테이너 테스트 | 최종 CPU 이미지에 테스트와 계약을 읽기 전용으로 연결하고 dev 의존성을 설치한 일회용 컨테이너에서 52개 통과. 운영 이미지에는 테스트·dev 의존성 미포함 |
| develop 문서·DB 계약 검사 | `backend/report-service/.venv/Scripts/python.exe -O -m unittest discover -s scripts/tests -v`: 46개 통과 |
| CPU 전용 의존성 | Windows·Linux 모두 `torch 2.14.1+cpu`, `torch.version.cuda is None` 확인. Linux는 실제 빌드한 이미지에서 실행 |
| Compose 설정 | 실사용 비밀 값 대신 검사 전용 값으로 compose.yaml + compose.minio.yaml `config --quiet` 통과 |
| 문서·공백 검사 | API 명세·클래스 다이어그램을 실제 #85 범위와 대조. `git diff --check` 통과. Mermaid 렌더링은 미실행 |
| Docker 이미지 빌드·실제 Compose 연동 | core·scoring 이미지 빌드 성공. 별도 Compose 프로젝트에서 PostgreSQL(core V1~V8), RabbitMQ, Redis, MinIO, core, scoring 실행·검증 |
| 활성 모델 없음·내부 인증 | core snapshot이 비어 있으면 models=UP·versions=[] 확인. 토큰 없는 내부 조회는 401 |
| 실제 core 모델 등록·활성화 | 격리된 테스트 관리자 권한으로 서술형·논술형 두 합성 체크포인트의 등록·승인 API 호출. core snapshot의 name/version/revision과 scoring 응답 일치 확인 |
| S3 로딩 실패·재시도 | MinIO의 검증용 파일이 없을 때 models=DOWN·readiness 503, liveness 200, versions=[] 확인. 파일 업로드 후 프로세스 재시작 없이 두 모델 로딩·readiness 200으로 복구 |
| core 접속 실패·재시도 | 검증용 core를 중지하고 scoring을 기동해 readiness 503·liveness 200 확인. core 재기동 후 scoring 자동 복구 확인 |
| 최종 scoring 로그 | 검증용 비밀 값의 노출과 미처리 예외 traceback이 없음을 확인. 로그 검사 시 비밀 값 자체는 출력하지 않음 |
| 실제 CPU 로딩·추론 | 작은 무작위 RoBERTa 두 모델을 실제 MinIO → Transformers로 로딩. 운영 이미지 UID 10001에서 승인 scope 내 조회·범위 밖 비활성, 스레드풀 추론의 유한한 1×9 원시 출력, 임시 다운로드 폴더 정리 후 사용 확인 |
| 실제 팀 M2 모델 검증 | 미실행. 서비스용 체크포인트·등록 version/artifactUri 전달 필요. 합성 모델 결과를 실제 학습 모델의 품질·속도 검증으로 간주하지 않음 |

Windows 샌드박스에서는 테스트 이벤트 루프의 socketpair 생성이 멈춰 같은 명령을 호스트에서 실행했다. 제품 코드에 우회 설정을 넣지 않았다. 합성 파일·검증용 자격 증명·실행 보조 스크립트는 gitignore 대상 `build/issue85/`에만 두었다. AI Hub 데이터와 실제 학습 가중치는 사용하지 않았다.

검증 종료 후 `sagomungchi-issue85-20261028` 프로젝트만 `compose down`으로 정리했다. 볼륨 삭제 옵션은 사용하지 않아 검증 데이터는 보존했고, 기존 프로젝트 컨테이너는 변경하지 않았다.

### Docker 복구와 실제 연동에서 수정한 오류

- 처음에는 Docker Desktop의 `sailor-ingest.sock`, 이어 `docker-secrets-engine/engine.sock` 접근 오류로 엔진이 시작되지 않았다. Docker 프로세스를 종료한 상태에서 해당 런타임 디렉터리를 백업하고 재생성해 엔진 응답을 복구했다. DB 볼륨·WSL 디스크 초기화나 삭제는 하지 않았다. 향후 재부팅에도 재발하지 않는다는 보장은 이번 검증 범위가 아니다.
- 복구 후 실제 MinIO 연동에서 boto3 S3 클라이언트가 `with client` 프로토콜을 지원하지 않는 `TypeError`를 발견했다. `contextlib.closing(client)`으로 정리하도록 수정하고 테스트 대역도 실제 SDK처럼 `close()`를 제공하도록 고쳤다. 최종 이미지에서 위 S3 실패·복구 검증을 다시 수행했다.
- 이미지에 약 987 MiB의 uv 다운로드 캐시가 중복 저장되는 것을 확인해 BuildKit cache mount로 분리했다. 최종 컨테이너에 `/root/.cache/uv`가 없음을 확인했다. `.dockerignore`에는 검증 파일·로컬 모델·`.env`를 추가했다.

### 이미지·메모리 실측과 한계

| 항목 | 2026-10-28 측정값 |
|---|---|
| 최종 이미지 | `sagomungchi/scoring-service:issue85-verify`, `sha256:198e17a18a052bfdc9577b169dd08daa9918c93b137e2613f5a80a1a10dc40e5` |
| Docker image inspect의 Size | 1,874,149,005 bytes (약 1.75 GiB). Docker가 보고한 값이며 레지스트리 전송량·고유 디스크 점유량과 동일하다고 간주하지 않음 |
| 이미지 내 Python 환경 | `du -sh /app/.venv`: 1.2G. uv 다운로드 캐시는 이미지에서 제외 |
| scoring 컨테이너 | 작은 합성 모델 두 개 로딩 후 `docker stats` 단일 표본: 389.2 MiB |
| 별도 CPU 추론 검증 프로세스 | 최대 RSS 407,908 KiB (약 398.3 MiB). 위 컨테이너 메모리 표본과 측정 대상이 다름 |

이 값은 작은 합성 모델의 연동 확인용이다. 실제 klue/roberta-base/개선 후보의 메모리, 처리 시간, 모델 교체 중 이전·신규 가중치 동시 보유 비용은 아직 측정하지 않았다. 이 값을 근거로 Kubernetes 자원 제한을 확정하지 않는다.

## 파일·실행 설정

- `app/clients/core_client.py`: 기존 internal_client로 core snapshot 조회, 호출 자체의 중복 재시도 없음.
- `app/model_versions.py`: scoring 대상 필터·revision·scope 계약 검사.
- `app/model_registry.py`: 정확한 scope 검사, 낮은 revision 무시, 로딩 완료 후 교체, 실패 시 이전 모델 유지. `/internal/versions`가 보고하는 revision은 실제 로딩 모델 기준이다.
- `app/clients/model_artifacts.py`, `app/model_loader.py`: 설정된 모델 버킷의 S3 디렉터리만 읽고 경로 이탈을 차단. `save_pretrained`의 모델·토크나이저와 `train_info.json`을 로딩한다. 누락된 학습 가중치로 임의 초기화된 모델은 거부한다. 현재 로더는 9개 출력을 가진 M2 회귀 모델이며 M1은 별도 로더를 요구한다.
- `app/model_startup.py`, `app/bootstrap.py`: 기동 조회·로딩의 백그라운드 재시도, models readiness, 종료 시 태스크 정리. health 요청이 core/S3를 직접 호출하지 않는다.
- `S3_ENDPOINT_URL` 생략 시 AWS SDK 기본 endpoint·자격 증명 체인 사용. MinIO overlay는 endpoint와 로컬 자격 증명 환경 변수를 주입한다. `S3_BUCKET`, `S3_REGION`, `MODEL_CACHE_DIR`, `MODEL_RETRY_INTERVAL`로 설정한다.
- `MODEL_CACHE_DIR`는 일시 다운로드용 경로이며 롤백 캐시로 재사용하지 않는다. 기본 로컬 경로는 gitignore 대상 `local_data/scoring-models`, 컨테이너는 `/tmp/scoring-models`다. readOnlyRootFilesystem 배포 시 이 경로에 쓰기 가능한 임시 볼륨이 필요하다.

## 2026-10-28 당시 남았던 확인

1. 모델 담당자가 서비스에 사용할 체크포인트·토크나이저·train_info.json과 버전 번호를 전달한다. 이름은 기존 `m2-klue-narrative`·`m2-klue-essay`를 사용한다. 가중치를 GitHub에 올리지 않는다.
2. 실제 팀 체크포인트로 Compose + MinIO → core 승인·활성화 → scoring 로딩·버전 조회를 재확인하고 실제 모델의 메모리·처리 시간을 측정한다. 위 합성 모델 검증이 실제 서비스 모델의 승인·품질 검증을 대신하지 않는다.

위 두 항목은 2026-10-29 실제 팀 모델 검증으로 해소했다. 학년·입력 유형의 최종 scope 매핑은 #87, 실제 이벤트 소비·롤백·레플리카 동기화는 #86에서 검증한다. 모델 품질 승인·운영 배포 준비 완료를 의미하지 않는다.

## 실제 팀 2.0 모델 검증 (2026-10-29)

### 기준과 파일

- scoring: `feature/scoring-model-registry`의 `fdf0a4e` 소스로 새 CPU 이미지를 빌드했다. 별도 로컬 worktree `scoring-issue85`에서 작업하여 기존 `test/report-integration`의 #56 미커밋 변경은 유지했다.
- core: develop `c608f52`의 실제 소스를 Java 21로 다시 빌드했다. core 마이그레이션·관리자 등록/활성화·내부 snapshot API를 사용했다. core 대역은 사용하지 않았다.
- 파일: 사용자가 제공한 `m2_models_2.0.tar`, 886,579,200 bytes.
- SHA-256: `aa294abf122dfd123ec5de296234fef469ab3de7ee027cfbaae5a4a9c86eba2d`.
- 두 디렉터리 `models/m2-klue-narrative/2.0/`, `models/m2-klue-essay/2.0/`에 각각 `config.json`, `model.safetensors`, `tokenizer_config.json`, `tokenizer.json`, `train_info.json`, `score_cuts.json`이 있다.
- 각 가중치는 442,524,276 bytes이며 9개 출력을 가진 RoBERTa 회귀 모델이다. 두 모델 모두 `max_length=512`. 서술형 핵심어 사용 설정은 True, 논술형은 False다.

### 실행 범위

`scripts/verify_scoring_models.py`가 임의의 고유 이름으로 로컬 Compose 프로젝트를 만든다. PostgreSQL·RabbitMQ·Redis·core·MinIO·scoring을 실제 실행한다. 모델 파일을 저장소에 풀지 않고 tar의 지정된 일반 파일 12개만 로컬 MinIO로 전송하며 크기와 SHA-256 목록을 결과에 남긴다.

로컬 테스트 버킷은 `issue85-local-models`이며 URI는 다음과 같다. **운영 AWS 경로가 아니다.**

```text
s3://issue85-local-models/models/m2-klue-narrative/2.0/
s3://issue85-local-models/models/m2-klue-essay/2.0/
```

테스트용 관리자·평가 기록·승인 scope(`verification/m2-klue-narrative`, `verification/m2-klue-essay`)는 격리된 core DB에서만 생성했다. 실제 품질 평가를 수행했다는 표시나 운영 학년 승인으로 사용하지 않는다.

### 활성 버전 조회 결과

```json
{"items":[
  {"name":"m2-klue-essay","version":"2.0","revision":1},
  {"name":"m2-klue-narrative","version":"2.0","revision":1}
]}
```

- 활성 모델 없는 상태: readiness 200, versions 빈 목록. 내부 토큰 없는 버전 조회는 401.
- core에서 위 두 버전을 등록·활성화한 뒤 scoring 재시작: MinIO 파일이 없으면 models=DOWN/readiness 503, liveness 200, versions 빈 목록.
- 실제 파일 업로드 후: 추가 재시작 없이 재시도로 두 모델을 로딩하고 models=UP/readiness 200으로 복구. core snapshot의 이름·버전·revision과 `/internal/versions` 응답 일치.

### 실제 CPU 확인과 회귀 검사

| 항목 | 2026-10-29 결과 |
|---|---|
| 실제 모델 CPU 로딩·추론 | 별도 probe도 실제 core snapshot → MinIO → #85 로더를 사용. 두 모델 모두 유한한 `1×9` 원시 점수 출력 |
| 실행 환경 | 운영 이미지 UID 10001, `torch 2.14.1+cpu`, CUDA 없음. 이미지 lock의 Transformers 5.21.0으로 로딩 |
| 메타데이터 | 두 모델의 `max_length`, `with_keyword`, 9개 항목 `score_cuts` 확보. 별도 JSON과 train_info 안의 점수 경계값 일치 |
| 승인 범위 | core가 준 검증용 scope는 모델 반환, `unapproved/scope`는 비활성 |
| 임시 파일 정리 | 두 모델 로딩 후 다운로드 디렉터리가 비어 있어도 메모리 모델로 추론 성공 |
| 로딩 시간 | 별도 probe에서 두 모델 다운로드·로딩 합계 약 22.78초 |
| 추론 시간 | 합성 문장 1회: 논술형 약 1.47초, 서술형 약 4.76초. 반복 벤치마크나 #87의 35초 예산 보장 자료는 아님 |
| 메모리 | 두 모델 로딩 후 scoring 컨테이너 단일 표본 552.7 MiB. 별도 로딩·추론 probe 최대 RSS 1,172,360 KiB. 서로 다른 측정 대상 |
| 기존 자동 테스트 | 현재 #85 소스 기준 52 passed, 27.56초. Ruff check·format 30개 파일 통과 |
| 로그 | scoring 로그에서 이번 일회용 자격 증명 노출과 미처리 traceback 없음 |
| 정리 | 이번 검증 전용 프로젝트 컨테이너·임시 볼륨·네트워크 제거 확인. 이전 #56 변경과 원본 tar 보존 |

원시 출력의 실행 가능성을 확인한 것이며 최종 1~4/1~5 점수 변환·정확도·키워드 입력 계약을 검증한 것은 아니다. `scoring_model_probe.py`의 한국어 입력은 합성 smoke 입력이고, #87에서는 모델 학습 때의 정확한 입력 형식과 score_cuts 적용을 별도로 대조한다.

### 재현과 보관

최신 core `bootJar`와 #85 scoring 이미지를 먼저 빌드한다. report 개발용 Python에는 검증 runner의 boto3·httpx·PyYAML이 설치되어 있다.

```powershell
docker build -t local/scoring85-models:20261029 backend/scoring-service
# #85 작업 폴더에서 실행. core-root는 최신 develop의 별도 checkout이다.
& C:/Users/playdata2/Desktop/final/SKN34-FINAL-3TEAM/backend/report-service/.venv/Scripts/python.exe -X utf8 scripts/verify_scoring_models.py --archive C:/Users/playdata2/Desktop/m2_models_2.0.tar --core-root C:/Users/playdata2/Desktop/final/SKN34-FINAL-3TEAM --output C:/Users/playdata2/Desktop/final/tmp/issue85-real-models-20261029-final
```

runner는 모델 압축 파일과 결과 폴더가 Git checkout 내부이면 실행을 거부한다. 결과 폴더의 Compose 설정에는 일회용 로컬 자격 증명이 있으므로 Git에 추가하지 않는다. 종료 시 이번 테스트 프로젝트의 컨테이너·볼륨·네트워크만 정리한다. 원본 tar는 그대로 보존한다.

첫 검증에서 Docker 재시작 시 자동 할당한 호스트 포트가 바뀌어 이전 주소를 기다렸다. 재시작 후 `compose port`를 다시 조회하도록 검증 스크립트를 수정했다. 모델 로더나 제품 API 오류는 아니었다.

최종 결과는 저장소 밖 `C:/Users/playdata2/Desktop/final/tmp/issue85-real-models-20261029-final/results.json`에 있다. core snapshot·활성 버전·파일 크기/해시·CPU 출력·측정값을 기록했고, `probe.log`와 `services.log`를 함께 보관했다. 자동 테스트 결과는 같은 tmp 폴더의 `issue85-team-models-pytest-20261029.xml`이다.

**판정: #85에 남아 있던 실제 팀 모델 로딩·활성 버전 수동 검증 완료. 제품 로더 수정 없이 통과했으며 이번 변경은 재현 스크립트와 검증 문서다. PR·원격 push·GitHub 이슈 종료는 아직 하지 않았다.**

## #85 푸시 전 최신 통합 검증 (2026-10-29)

기존 #85 브랜치를 최신 develop과 통합하고 report·scoring MinIO 설정을 모두 보존해 충돌을 해결했다. #86 이벤트 수신·#87 채점 API는 포함하지 않았다. #87 미커밋 작업은 별도 기존 worktree에 보존했다.

- 전용 uv 가상환경·잠금 의존성 동기화, Ruff check·format 통과.
- scoring 전체 **52 passed**, 41.88초. 낮은 revision·scope 제한·실패 후 재시도·기존 모델 보존·대역 모델·OpenAPI·내부 인증 검사 포함.
- 공통 검사 **74 passed, 34 subtests passed**, 28.46초.
- 최신 core 실제 JAR와 새 `local/scoring85-release:20261029` 이미지 사용.
- 실제 팀 M2 2.0 두 모델: 빈 snapshot 준비 완료 → 파일 누락 시 readiness 503/liveness 200 → MinIO 업로드 후 같은 프로세스에서 자동 복구 → core/versions 일치 확인.
- CPU probe에서 두 모델 유한한 1×9 출력·승인 scope 밖 비활성·메타데이터·임시 다운로드 정리 후 추론 확인.
- scoring 로그에서 검증 자격 증명과 미처리 traceback 없음. 전용 Compose 자원 정리 완료.
- 모델·AI Hub 데이터는 Git에 추가하지 않았다. 증거는 저장소 밖 `tmp/issue85-release-real/results.json`·로그와 `tmp/issue85-release-tests.xml`에 보관한다.

GitHub PR CI·검토·병합은 이 로컬 검증과 별도다. M1 실제 가중치 로더와 M2 최종 채점 응답은 각각 #88·#87 범위이며 #85 완료로 함께 처리하지 않는다.

최종 통합 기준은 develop `48339a4`(#56 PR #148 포함)다. 마지막 추가 병합에서 core·scoring·공통 검사 소스 변경은 없었으며 충돌 없이 반영했다. 최종 diff·Ruff 검사를 통과했다. 이번에 추가한 커밋 메시지는 한국어이며 기존 원격 #85의 과거 커밋 이력은 재작성하지 않았다.

### #64 병합 후 재검증

develop `c364ed4`의 #64 리포트 서술 API를 반영했다. `docs/report/ai.md` 끝부분의 동시 추가 충돌은 5절(#64)·6절(#85)로 구분하여 해결했다. scoring 코드와 모델 로더 변경은 없다. scoring 52개, 공통 74개와 하위 검사 34개, report 서술 24개 테스트 및 Ruff·포맷·충돌 검사가 통과했다. 실제 모델 검증은 직전 동일 scoring 코드의 실행 결과를 유지한다.
