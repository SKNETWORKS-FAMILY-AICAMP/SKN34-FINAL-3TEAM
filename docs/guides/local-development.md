# 로컬 개발·설정 안내

이 문서의 명령은 저장소 루트 기준이다. 프로젝트 소개와 기능 흐름은 [README](../../README.md)를 참고한다. 기존 `.env`가 있으면 예제 파일로 덮어쓰지 않는다.

## 로컬 실행
```sh
cp .env.example .env        # 값 입력
docker compose up --build
```

| 대상 | 주소 |
|---|---|
| core-service (공개 API) | http://localhost:8080 |
| learning-service | http://localhost:8081 |
| ai-service | http://localhost:8000 |
| scoring-service | http://localhost:8001 |
| report-api | http://localhost:8002 |
| RabbitMQ 관리 화면 | http://localhost:15672 |
| MinIO API / 관리 화면 (선택 실행: `compose.minio.yaml` 사용) | http://localhost:9000 / http://localhost:9001 |

- 앱 포트 충돌(Windows 8000~8099 예약 등) 시 `.env`의 `CORE_HOST_PORT`·`LEARNING_HOST_PORT`·`AI_HOST_PORT`·`SCORING_HOST_PORT`·`REPORT_HOST_PORT`(MinIO는 `MINIO_HOST_PORT`·`MINIO_CONSOLE_HOST_PORT`)로 변경. PostgreSQL 5432, RabbitMQ 5672·15672, Redis 6379는 `compose.yaml`에 고정
- 웹: `frontend/web`에서 `npm ci` 후 `npm run dev` (`/api` → core-service 프록시)
- 개발 규칙: [프로젝트 문서 안내](../README.md)
- 로컬 Kubernetes: [kind 설정·설치](../../infrastructure/kind/README.md), [저장소·Secret 설정](../../infrastructure/gitops/charts/platform-data/README.md)

core 포트를 바꿨다면 웹 실행 터미널에도 같은 값을 설정한다. Vite의 API 프록시는 루트 `.env`의 `CORE_HOST_PORT`를 자동으로 적용하지 않는다. 예를 들어 `.env`에서 `CORE_HOST_PORT=18080`으로 바꿨다면 PowerShell에서 다음과 같이 실행한다.

```powershell
cd frontend/web
$env:CORE_HOST_PORT = '18080'
npm run dev
```

별도 주소가 필요하면 `CORE_PROXY_TARGET`으로 프록시 대상 URL을 지정한다.

### MinIO 선택 실행

기본 `docker compose up --build`에는 MinIO가 포함되지 않는다. 로컬 파일 저장소가 필요하면 `.env`에 `MINIO_ROOT_USER`(3자 이상)·`MINIO_ROOT_PASSWORD`(8자 이상)를 추가한다. 비밀번호에 `$` 또는 `#`가 있으면 작은따옴표로 감싼 리터럴을 사용한다.

```powershell
docker compose -f compose.yaml -f compose.minio.yaml up -d minio
docker compose -f compose.yaml -f compose.minio.yaml run --rm minio-init
docker compose -f compose.yaml -f compose.minio.yaml up -d --build
```

첫 명령은 전용 볼륨 소유권 준비 후 서버를 실행하고, 두 번째 명령은 서버 준비 상태를 기다려 `sagomungchi-local-missions`·`sagomungchi-local-reports`·`sagomungchi-local-models` 버킷을 만든다. 세 번째 명령은 report·scoring에도 MinIO 접속 설정을 반영해 전체 서비스를 실행한다. 같은 초기화 명령을 다시 실행해도 기존 버킷과 데이터를 유지한다. 두 파일은 같은 Compose 프로젝트 이름을 사용해야 하며 기본 프로젝트 이름은 `sagomungchi`다.

MinIO를 포함한 프로젝트를 중단할 때도 `docker compose -f compose.yaml -f compose.minio.yaml down`을 사용한다. 데이터를 보존하려면 `--volumes`를 붙이지 않는다. 기본 파일과 함께 실행하는 명령이므로 기존 PostgreSQL·RabbitMQ·내부 토큰·`AUTH_JWT_SECRET` 환경 변수도 필요하다(Compose가 전체 파일의 필수 변수를 먼저 확인).


### 인증 설정

`.env.example`을 참고해 개인 `.env`에 설정한다. 키·자격 증명은 Git에 넣지 않는다.

| 변수 | 용도·기본값 |
|---|---|
| `AUTH_JWT_SECRET` | access JWT 서명 키(base64 32바이트 이상 난수, 필수) |
| `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET` | Google OAuth. 없으면 로그인 시작이 503 |
| `AUTH_WEB_ORIGIN` | web origin(기본 `http://localhost:5173`, Vite `/api` 프록시) |
| `AUTH_COOKIE_SECURE` | 로컬 HTTP만 `false`, 배포 HTTPS는 `true` |
| `AUTH_NEW_ACCOUNT_DEMO` | 데모 전용 환경만 `true`. 새 Google 부모 계정을 `is_demo=true`로 저장해 운영 통계에서 제외(기본 `false`, 기존 계정은 변경 안 함) |
| `AUTH_ACCESS_TTL`·`AUTH_STUDENT_ACCESS_TTL`·`AUTH_REFRESH_TTL`·`AUTH_REAUTH_TTL` | 부모 access 15m, 학생 access 15m, refresh 7d(부모·관리자만), 재인증 토큰 5m |
| `REDIS_HOST`·`REDIS_PORT`·`REDIS_PASSWORD` | 알림 중계·학생 기기 페어링 |
| `STUDENT_DEVICE_TTL`·`STUDENT_DEVICE_ATTEMPT_LIMIT` | 기기 고정 만료 90d, 페어링 발급·등록 10분당 20회 |

- Google web client의 redirect URI로 `AUTH_WEB_ORIGIN` + `/api/v1/auth/google/callback`과 `/api/v1/auth/google/reauth/callback`을 등록한다
- core V25 마이그레이션이 TERMS·PRIVACY·GUARDIAN 1.0 동의 문서를 게시하므로 별도 등록 없이 온보딩(문서 확인 → 동의 저장 → 자녀 등록)이 진행된다. 문구 개정은 게시한 행을 고치지 않고 같은 종류에 새 `version` 행을 추가한다([동의 문서 출처와 시드](../report/auth-account.md#8-동의-문서-3종-출처와-시드-235)). 게시 문서가 없는 DB에서는 `GET /consent-documents`가 503 `CONSENT_DOCUMENTS_UNAVAILABLE`
- GitOps local은 core-service values의 `secretKeyRef`로 위 비밀 값을 주입한다. Secret 준비는 `infrastructure/kind/create-app-secrets.ps1`을 따른다.
- 인증·동의·재인증·학생 기기 결정은 [인증·계정 보고서](../report/auth-account.md)

### 판정 교차 확인·이관·content_3 설정

Compose는 루트 `.env`, GitOps local은 `infrastructure/gitops/environments/local/`의 해당 서비스 YAML `env` 값으로 설정한다. 아래 기본값은 기존 앱 설정과 같으며, 설정 전달 추가만으로 기능을 켜거나 모델을 승인하지 않는다.

| 서비스 | 변수 | 기본값·의미 |
|---|---|---|
| ai | `M2_CROSS_CHECK_ENABLED` | `false`면 M2를 호출하지 않음. `true`이고 입력·활성 모델 조건을 만족하면 교차 확인하고 불일치 판정을 보류 |
| ai | `M1_CHECK_ENABLED` | `false`. M1 입력이 있을 때만 검사(learning 입력 연동은 별도) |
| ai | `M2_NARRATIVE_LOW` / `M2_NARRATIVE_HIGH` | `2.0` / `4.0`. 서술형 불일치 경계 |
| ai | `M2_ESSAY_LOW` / `M2_ESSAY_HIGH` | `1.0` / `2.0`. 논술형 불일치 경계 |
| ai | `M1_MIN_CONFIDENCE` | `0.8`. M1 보류 경계 |
| ai | `JUDGE_DEADLINE` | `33.0`초. 판정 전체 시간 한도 |
| ai | `SCORING_TIMEOUT` | `10.0`초. 실제 호출은 남은 판정 시간과 이 값 중 작은 값 사용 |
| ai | `SCORING_RESERVE` | `3.0`초. 교차 확인 입력이 있을 때 확보하는 scoring 시간 |
| core | `APP_GUARDIAN_TRANSFER_ENABLED` | `false`. 신규 이관 활성화(core DB V26 적용 후). 웹 `VITE_GUARDIAN_TRANSFER_ENABLED`도 맞춰야 함 |
| web | `VITE_GUARDIAN_TRANSFER_ENABLED` | `false`. 신규 요청·수락 화면 노출 제어. 기존 요청 조회·취소·거절과 관리 경로는 유지. `frontend/web/vite.config.ts`가 루트 `.env`에서 읽으며 신규 이관은 core 플래그와 함께 변경 |
| scoring | `M2_CONTENT3_RULE_ENABLED` | `false`. 승인 범위 내 서술형 3.0·초5~6의 content_3만 보정 |

- Compose 적용: `.env` 수정 후 `docker compose up -d ai-service core-service scoring-service`. MinIO 등 추가 파일을 사용했다면 최초 실행과 같은 `-f` 조합을 유지한다. `restart`만으로는 변경된 환경 변수가 반영되지 않는다.
- GitOps 적용: 해당 local values의 `env` 항목을 수정하고 Git 반영·Argo CD sync로 Pod를 갱신한다. 루트 `.env`의 비밀이 아닌 플래그가 values로 자동 복사되지는 않는다. 웹 Vite 설정은 웹 실행/빌드 때 별도 적용한다.
- 시간값은 양수, `SCORING_RESERVE < JUDGE_DEADLINE < 35`초(learning 제한)를 유지한다. 경계값은 기존 임시값이며 품질 확인 없이 변경·활성화하지 않는다. M1 신뢰도는 0~1, M2 낮은 경계는 높은 경계보다 작게 설정한다.
- 복귀: 변경한 값과 플래그를 위 기본값으로 되돌려 같은 방식으로 재적용한다. 이미 저장한 판정은 소급 변경하지 않는다. 이관을 꺼도 기존 대기 요청의 조회·취소·거절 및 탈퇴·삭제 차단은 유지한다.
- 이관 로컬 체험은 `scripts/start_transfer_local.ps1`을 사용한다. scoring도 내부 전용으로 함께 실행한다. `M2_CROSS_CHECK_ENABLED=false`면 M2를 호출하지 않는다. 교차 확인을 켠 상태에서 scoring이 실패해도 ai는 `modelScores.skipped`에 `SCORING_UNAVAILABLE` 또는 `SCORING_REJECTED`를 남기고 LLM 판정을 이어간다(#305). 생략된 교차 확인은 나중에 자동으로 다시 수행하지 않는다.

근거와 검증 범위: [AI 교차 확인·장애 격리](../report/ai.md), [설정 전달 보완 보고서](../report/local-platform.md#13-교차-확인이관content_3-설정-전달-312).
