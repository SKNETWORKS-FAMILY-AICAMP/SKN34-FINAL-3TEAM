# SKN34-FINAL-3TEAM

## 로컬 실행
```
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
- 웹: `cd frontend/web && npm install && npm run dev` (`/api` → core-service 프록시)
- 개발 규칙: [docs/README.md](docs/README.md)
- 로컬 Kubernetes: [kind 설정·설치](infrastructure/kind/README.md), [저장소·Secret 설정](infrastructure/gitops/charts/platform-data/README.md)

### MinIO 선택 실행

기본 `docker compose up --build`에는 MinIO가 포함되지 않는다. 로컬 파일 저장소가 필요하면 `.env`에 `MINIO_ROOT_USER`(3자 이상)·`MINIO_ROOT_PASSWORD`(8자 이상)를 추가한다. 비밀번호에 `$` 또는 `#`가 있으면 작은따옴표로 감싼 리터럴을 사용한다.

```powershell
docker compose -f compose.yaml -f compose.minio.yaml up -d minio
docker compose -f compose.yaml -f compose.minio.yaml run --rm minio-init
```

첫 명령은 전용 볼륨 소유권 준비 후 서버를 실행하고, 두 번째 명령은 서버 준비 상태를 기다려 `sagomungchi-local-missions`·`sagomungchi-local-reports`·`sagomungchi-local-models` 버킷을 만든다. 같은 초기화 명령을 다시 실행해도 기존 버킷과 데이터를 유지한다. 두 파일은 같은 Compose 프로젝트 이름을 사용해야 하며 기본 프로젝트 이름은 `sagomungchi`다.

MinIO를 포함한 프로젝트를 중단할 때도 `docker compose -f compose.yaml -f compose.minio.yaml down`을 사용한다. 데이터를 보존하려면 `--volumes`를 붙이지 않는다. 기본 파일과 함께 실행하는 명령이므로 기존 PostgreSQL·RabbitMQ·내부 토큰·`AUTH_JWT_SECRET` 환경 변수도 필요하다(Compose가 전체 파일의 필수 변수를 먼저 확인).


### 인증 설정

`.env.example`을 참고해 개인 `.env`에 설정한다. 키·자격 증명은 Git에 넣지 않는다.

| 변수 | 용도·기본값 |
|---|---|
| `AUTH_JWT_SECRET` | access JWT 서명 키(base64 32바이트 이상 난수, 필수) |
| `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET` | Google OAuth. 없으면 로그인 시작이 503 |
| `AUTH_WEB_ORIGIN` | web origin(기본 `http://localhost:5173`, Vite `/api` 프록시) |
| `AUTH_COOKIE_SECURE` | 로컬 HTTP만 `false`, 배포 HTTPS는 `true` |
| `AUTH_ACCESS_TTL`·`AUTH_STUDENT_ACCESS_TTL`·`AUTH_REFRESH_TTL`·`AUTH_REAUTH_TTL` | 부모 access 15m, 학생 access 15m, refresh 7d(부모·관리자만), 재인증 토큰 5m |
| `REDIS_HOST`·`REDIS_PORT`·`REDIS_PASSWORD` | 알림 중계·학생 기기 페어링 |
| `STUDENT_DEVICE_TTL`·`STUDENT_DEVICE_ATTEMPT_LIMIT` | 기기 고정 만료 90d, 페어링 발급·등록 10분당 20회 |

- Google web client의 redirect URI로 `AUTH_WEB_ORIGIN` + `/api/v1/auth/google/callback`과 `/api/v1/auth/google/reauth/callback`을 등록한다
- 운영자가 검토된 TERMS·PRIVACY·GUARDIAN 동의 문서를 DB에 게시해야 온보딩(문서 확인 → 동의 저장 → 자녀 등록)이 진행된다(미게시는 503)
- 배포 시 위 비밀 값은 core에 Kubernetes Secret 참조로 주입한다(앱 Deployment는 아직 저장소에 없음)
- 인증·동의·재인증·학생 기기 결정은 [인증·계정 보고서](docs/report/auth-account.md)
